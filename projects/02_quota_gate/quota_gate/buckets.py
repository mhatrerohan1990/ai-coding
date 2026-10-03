import threading
from dataclasses import dataclass

DEFAULT_MAX_BUCKETS = 500_000
DEFAULT_SWEEP_INTERVAL = 60.0
CAP_TARGET_RATIO = 0.9  # when over the cap, evict down to this fraction of it


@dataclass(frozen=True)
class TakeResult:
    allowed: bool
    tokens: float  # tokens left in the bucket after this call (fractional)


@dataclass(frozen=True)
class TakeAllResult:
    allowed: bool
    tokens: list  # per entry, in order: tokens left (unchanged for every entry if denied)


class BucketStore:
    """In-memory token buckets, one per (tenant, policy, subject). Lost on restart.

    A bucket starts full, refills continuously at `refill_per_second` and never
    holds more than `capacity`. Refill + check + deduct happen under one lock, so
    two concurrent takes can never both spend the same token.

    Memory is bounded two ways. Each bucket remembers when it will be full again
    (`full_at`); a full bucket is indistinguishable from a missing one, so a periodic
    sweep drops it without changing any decision. If that is not enough (a flood of
    distinct subjects), `max_buckets` evicts the buckets closest to full first. Those
    are the ones where forgetting state gives away the least.
    """

    def __init__(self, max_buckets=DEFAULT_MAX_BUCKETS, sweep_interval=DEFAULT_SWEEP_INTERVAL):
        self._max_buckets = max_buckets
        self._sweep_interval = sweep_interval
        self._lock = threading.Lock()
        # (tenant_id, policy_id) -> {subject: (tokens, last_refill_time, full_at)}
        self._buckets = {}
        self._count = 0
        self._last_sweep = None

    def __len__(self):
        with self._lock:
            return self._count

    def take(self, key, capacity, refill_per_second, cost, now):
        """Take from one bucket. `key` is (tenant_id, policy_id, subject)."""
        result = self.take_all([(key, capacity, refill_per_second)], cost, now)
        return TakeResult(result.allowed, result.tokens[0])

    def take_all(self, entries, cost, now):
        """All-or-nothing across buckets.

        `entries` is a list of (key, capacity, refill_per_second). `cost` is charged
        to every bucket only if every one of them can afford it; otherwise none is.
        """
        with self._lock:
            self._sweep_if_due(now)
            current = []
            for key, capacity, rate in entries:
                group = self._buckets.get(key[:2], {})
                tokens, last, _full_at = group.get(key[2], (capacity, now, now))
                current.append(min(capacity, tokens + max(0.0, now - last) * rate))
            allowed = all(tokens >= cost for tokens in current)
            if allowed:
                current = [tokens - cost for tokens in current]
            for (key, capacity, rate), tokens in zip(entries, current):
                group = self._buckets.setdefault(key[:2], {})
                if key[2] not in group:
                    self._count += 1
                full_at = now + (capacity - tokens) / rate if rate > 0 else float("inf")
                group[key[2]] = (tokens, now, full_at)
            self._enforce_cap(now)
            return TakeAllResult(allowed, current)

    def sweep(self, now):
        """Drop every bucket that is full again. Returns how many were dropped."""
        with self._lock:
            return self._sweep(now)

    def reset_policy(self, tenant_id, policy_id):
        """Forget every subject's bucket for one policy; the next take starts full."""
        with self._lock:
            group = self._buckets.pop((tenant_id, policy_id), None)
            if group:
                self._count -= len(group)

    # -- internals; all called with the lock held ------------------------------

    def _sweep_if_due(self, now):
        if self._last_sweep is None:
            self._last_sweep = now
        elif now - self._last_sweep >= self._sweep_interval:
            self._sweep(now)

    def _sweep(self, now):
        self._last_sweep = now
        evicted = 0
        for policy_key in list(self._buckets):
            group = self._buckets[policy_key]
            for subject in [s for s, (_, _, full_at) in group.items() if full_at <= now]:
                del group[subject]
                evicted += 1
            if not group:
                del self._buckets[policy_key]
        self._count -= evicted
        return evicted

    def _enforce_cap(self, now):
        if self._count <= self._max_buckets:
            return
        self._sweep(now)  # idle buckets first: that costs nothing
        if self._count <= self._max_buckets:
            return
        target = int(self._max_buckets * CAP_TARGET_RATIO)
        by_full_at = sorted(
            (full_at, policy_key, subject)
            for policy_key, group in self._buckets.items()
            for subject, (_, _, full_at) in group.items()
        )
        for _full_at, policy_key, subject in by_full_at[: self._count - target]:
            del self._buckets[policy_key][subject]
            if not self._buckets[policy_key]:
                del self._buckets[policy_key]
        self._count = target
