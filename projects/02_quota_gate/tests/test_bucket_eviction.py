"""Idle buckets must not grow memory forever. Eviction is lossless: a bucket is only
dropped once it would be full again, which is exactly what a missing bucket looks like."""
from quota_gate.buckets import BucketStore


def key(i, policy="p"):
    return ("org_1", policy, f"user_{i}")


def take(store, now, k, cost=1, capacity=10, rate=1.0):
    return store.take(k, capacity=capacity, refill_per_second=rate, cost=cost, now=now)


def test_len_counts_buckets():
    store = BucketStore()
    assert len(store) == 0

    take(store, 1000.0, key(1))
    take(store, 1000.0, key(2))
    take(store, 1000.0, key(1))  # same bucket again

    assert len(store) == 2


def test_sweep_removes_buckets_once_they_would_be_full_again():
    store = BucketStore()
    take(store, 1000.0, key(1), cost=3)  # 7 of 10 left, 3s to full at 1 token/s

    assert store.sweep(1002.9) == 0
    assert len(store) == 1
    assert store.sweep(1003.0) == 1
    assert len(store) == 0


def test_sweep_keeps_buckets_that_are_still_recovering():
    store = BucketStore()
    take(store, 1000.0, key(1), cost=1)   # full again at 1001
    take(store, 1000.0, key(2), cost=10)  # empty, full again at 1010

    assert store.sweep(1005.0) == 1

    assert len(store) == 1
    assert take(store, 1005.0, key(2), cost=6).allowed is False  # only 5 refilled: state kept


def test_evicted_bucket_behaves_exactly_like_one_that_was_kept():
    kept, swept = BucketStore(), BucketStore()
    for store in (kept, swept):
        take(store, 1000.0, key(1), cost=4)  # 6 left, full at 1004
    swept.sweep(1010.0)
    assert len(swept) == 0

    a = take(kept, 1010.0, key(1), cost=3)
    b = take(swept, 1010.0, key(1), cost=3)

    assert (a.allowed, a.tokens) == (b.allowed, b.tokens) == (True, 7)


def test_buckets_that_never_refill_are_never_evicted():
    store = BucketStore()
    take(store, 1000.0, key(1), cost=5, rate=0.0)

    assert store.sweep(10**12) == 0
    assert take(store, 10**12, key(1), cost=6, rate=0.0).allowed is False


def test_sweeping_happens_automatically_after_the_interval():
    store = BucketStore(sweep_interval=60.0)
    for i in range(100):
        take(store, 1000.0, key(i))  # all full again by 1001

    take(store, 1100.0, key("new"))  # >= 60s since the last sweep

    assert len(store) == 1


def test_sweeping_is_lazy_not_on_every_take():
    store = BucketStore(sweep_interval=60.0)
    for i in range(100):
        take(store, 1000.0, key(i))

    take(store, 1030.0, key("new"))  # only 30s since the last sweep

    assert len(store) == 101


def test_abandoned_subjects_do_not_accumulate_over_time():
    store = BucketStore(sweep_interval=60.0)
    peak = 0
    for minute in range(120):  # two hours, 50 brand-new subjects every minute, never seen again
        now = 1000.0 + minute * 60
        for i in range(50):
            take(store, now, key(f"{minute}-{i}"))
        peak = max(peak, len(store))

    assert peak <= 100  # never more than ~2 minutes' worth, not 6000
    assert len(store) <= 100


# --- hard cap ---------------------------------------------------------------


def test_cap_bounds_the_bucket_count_even_when_nothing_is_idle():
    store = BucketStore(max_buckets=5, sweep_interval=10**9)

    for i in range(50):
        take(store, 1000.0, key(i), cost=10, rate=0.0001, capacity=10)  # all drained
        assert len(store) <= 5


def test_cap_evicts_the_buckets_closest_to_full_first():
    store = BucketStore(max_buckets=5, sweep_interval=10**9)
    for i in range(10):
        take(store, 1000.0, key(i), cost=i + 1)  # key(9) is the most drained

    # the most drained survive, so their state is intact
    assert take(store, 1000.0, key(9), cost=1).allowed is False
    assert take(store, 1000.0, key(8), cost=3).allowed is False
    # the least drained were evicted and start over as full buckets
    assert take(store, 1000.0, key(0), cost=10).allowed is True


def test_cap_prefers_dropping_idle_buckets_to_live_ones():
    store = BucketStore(max_buckets=3, sweep_interval=10**9)
    take(store, 1000.0, key("drained"), cost=10, rate=0.001)  # empty, ~10000s to full
    take(store, 1000.0, key("idle0"), cost=1, rate=1.0)  # full again at 1001
    take(store, 1000.0, key("idle1"), cost=1, rate=1.0)
    assert len(store) == 3

    # a 4th bucket at 1100 busts the cap; the two idle ones are full by now
    take(store, 1100.0, key("newcomer"), cost=1, rate=1.0)

    assert len(store) == 2  # only the idle ones went
    assert take(store, 1100.0, key("drained"), cost=1, rate=0.001).allowed is False


def test_reset_policy_keeps_the_count_consistent():
    store = BucketStore()
    for i in range(3):
        take(store, 1000.0, key(i, policy="p"))
    take(store, 1000.0, key(0, policy="q"))

    store.reset_policy("org_1", "p")

    assert len(store) == 1


def test_take_all_buckets_are_counted_and_swept_too():
    store = BucketStore()
    store.take_all([(key(1, "a"), 10, 1.0), (key(1, "b"), 10, 1.0)], cost=1, now=1000.0)
    assert len(store) == 2

    assert store.sweep(1001.0) == 2
    assert len(store) == 0
