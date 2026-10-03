import math
from dataclasses import dataclass
from typing import Optional

from quota_gate.errors import InvalidRequest, NotFound
from quota_gate.validation import parse_policy_body, validate_policy_id


class PolicyService:
    def __init__(self, repository, buckets):
        self._repo = repository
        self._buckets = buckets

    def put(self, tenant_id, policy_id, body):
        """Upsert. Returns (stored_policy, created)."""
        validate_policy_id(policy_id)
        policy = {"policy_id": policy_id, "tenant_id": tenant_id, **parse_policy_body(body)}
        created = self._repo.put(policy)
        # Decision (open question 3): a changed policy starts from a full bucket.
        self._buckets.reset_policy(tenant_id, policy_id)
        return policy, created

    def get(self, tenant_id, policy_id):
        policy = self._repo.get(tenant_id, policy_id)
        if policy is None:
            raise NotFound(f"policy '{policy_id}' not found")
        return policy

    def delete(self, tenant_id, policy_id):
        if not self._repo.delete(tenant_id, policy_id):
            raise NotFound(f"policy '{policy_id}' not found")
        self._buckets.reset_policy(tenant_id, policy_id)  # a re-created policy starts fresh

    def matching(self, tenant_id, subject, action):
        return self._repo.find_matching(tenant_id, subject, action)


@dataclass(frozen=True)
class CheckResult:
    allow: bool
    remaining: int
    reset_at: int
    matched_policies: list
    limit: Optional[int]
    retry_after: Optional[int] = None  # whole seconds; only set when denied


def specificity(policy):
    """Spec table: exact/exact 3, exact subject 2, exact action 1, */* 0."""
    match = policy["match"]
    return (match["subject"] != "*") * 2 + (match["action"] != "*")


class CheckService:
    def __init__(self, policies, clock, buckets):
        self._policies = policies
        self._clock = clock
        self._buckets = buckets

    def check(self, tenant_id, subject, action, cost=1):
        matching = self._policies.matching(tenant_id, subject, action)
        now = self._clock()
        if not matching:
            # Decision (open question 1): matching is strict. No policy means the
            # caller was never granted this action, so deny.
            return CheckResult(False, 0, math.ceil(now), [], None, retry_after=1)

        # Only the most specific policies apply; ties all apply (AND).
        top = max(specificity(p) for p in matching)
        applied = [p for p in matching if specificity(p) == top]
        rates = [p["limit"] / p["window_seconds"] for p in applied]

        # Decision (open question 4): a cost above a policy's burst can never succeed,
        # so waiting is pointless. That is a client error (400), not a rate limit (429).
        for p in applied:
            if cost > p["burst"]:
                raise InvalidRequest(
                    f"cost {cost} exceeds burst {p['burst']} of policy '{p['policy_id']}'"
                    " and can never be allowed"
                )

        # One bucket per (tenant, policy, subject): a "*" policy is not shared.
        taken = self._buckets.take_all(
            [
                ((tenant_id, p["policy_id"], subject), p["burst"], rate)
                for p, rate in zip(applied, rates)
            ],
            cost,
            now,
        )

        # The most constrained policy (fewest tokens left) speaks for the response.
        tightest = min(range(len(applied)), key=lambda i: taken.tokens[i])
        policy, tokens, rate = applied[tightest], taken.tokens[tightest], rates[tightest]

        retry_after = None
        if not taken.allowed:
            # Could succeed once every policy that said no has refilled enough.
            retry_after = max(
                1,
                max(
                    math.ceil((cost - t) / r)
                    for t, r in zip(taken.tokens, rates)
                    if t < cost
                ),
            )
        return CheckResult(
            allow=taken.allowed,
            remaining=math.floor(tokens),
            reset_at=math.ceil(now + (policy["burst"] - tokens) / rate),
            matched_policies=[p["policy_id"] for p in applied],
            limit=policy["limit"],
            retry_after=retry_after,
        )
