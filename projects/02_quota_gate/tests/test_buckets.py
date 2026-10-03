from concurrent.futures import ThreadPoolExecutor

from quota_gate.buckets import BucketStore

KEY = ("org_1", "p", "user_9")


def take(store, now, cost=1, capacity=10, rate=1.0, key=KEY):
    return store.take(key, capacity=capacity, refill_per_second=rate, cost=cost, now=now)


def test_new_bucket_starts_full():
    result = take(BucketStore(), now=1000.0, cost=1, capacity=10)

    assert result.allowed is True
    assert result.tokens == 9


def test_denied_take_does_not_consume_tokens():
    store = BucketStore()
    take(store, 1000.0, cost=3, capacity=3)

    denied = take(store, 1000.0, cost=1, capacity=3)

    assert denied.allowed is False
    assert denied.tokens == 0
    # still 0, not negative: a later refill of 1 token is enough for cost 1
    assert take(store, 1001.0, cost=1, capacity=3).allowed is True


def test_tokens_refill_continuously_and_cap_at_capacity():
    store = BucketStore()
    take(store, 1000.0, cost=10, capacity=10, rate=2.0)  # empty

    assert take(store, 1000.5, cost=1, capacity=10, rate=2.0).tokens == 0  # 1 refilled, 1 taken
    long_later = take(store, 9999.0, cost=1, capacity=10, rate=2.0)
    assert long_later.tokens == 9  # capped at 10, minus 1


def test_buckets_are_independent_per_key():
    store = BucketStore()
    take(store, 1000.0, cost=10, capacity=10)

    assert take(store, 1000.0, key=("org_1", "p", "user_1")).allowed is True
    assert take(store, 1000.0, key=("org_2", "p", "user_9")).allowed is True


def test_concurrent_takes_never_overspend():
    store = BucketStore()

    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda _: take(store, 1000.0, capacity=10, rate=0.0), range(200)))

    assert sum(r.allowed for r in results) == 10


def test_reset_policy_clears_every_subjects_bucket_for_that_policy_only():
    store = BucketStore()
    for key in [("org_1", "p", "user_1"), ("org_1", "p", "user_2"),
                ("org_1", "q", "user_1"), ("org_2", "p", "user_1")]:
        take(store, 1000.0, cost=10, capacity=10, rate=0.0, key=key)  # all empty

    store.reset_policy("org_1", "p")

    assert take(store, 1000.0, rate=0.0, key=("org_1", "p", "user_1")).allowed is True
    assert take(store, 1000.0, rate=0.0, key=("org_1", "p", "user_2")).allowed is True
    assert take(store, 1000.0, rate=0.0, key=("org_1", "q", "user_1")).allowed is False
    assert take(store, 1000.0, rate=0.0, key=("org_2", "p", "user_1")).allowed is False


def test_reset_policy_with_no_buckets_is_a_no_op():
    BucketStore().reset_policy("org_1", "nothing")


# --- take_all: several buckets, all-or-nothing ------------------------------


def entries(*specs):
    """specs: (policy_id, capacity, rate) -> take_all entries for subject user_9."""
    return [(("org_1", pid, "user_9"), cap, rate) for pid, cap, rate in specs]


def test_take_all_charges_every_bucket_when_all_can_afford_it():
    store = BucketStore()

    result = store.take_all(entries(("a", 10, 0.0), ("b", 5, 0.0)), cost=2, now=1000.0)

    assert result.allowed is True
    assert result.tokens == [8, 3]


def test_take_all_denial_charges_nothing():
    store = BucketStore()
    store.take_all(entries(("a", 10, 0.0), ("b", 1, 0.0)), cost=1, now=1000.0)  # b is empty

    denied = store.take_all(entries(("a", 10, 0.0), ("b", 1, 0.0)), cost=1, now=1000.0)

    assert denied.allowed is False
    assert denied.tokens == [9, 0]  # a was not charged a second time
    assert take(store, 1000.0, cost=9, capacity=10, rate=0.0, key=("org_1", "a", "user_9")).allowed


def test_take_all_with_one_entry_matches_take():
    store = BucketStore()

    result = store.take_all(entries(("a", 10, 0.0)), cost=3, now=1000.0)

    assert (result.allowed, result.tokens) == (True, [7])


def test_take_all_is_atomic_under_concurrency():
    store = BucketStore()
    spec = entries(("big", 10, 0.0), ("small", 5, 0.0))

    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda _: store.take_all(spec, cost=1, now=1000.0), range(200)))

    assert sum(r.allowed for r in results) == 5  # small allows exactly 5
    # big was charged exactly once per allowed request, never for a denied one
    left = take(store, 1000.0, cost=0, capacity=10, rate=0.0, key=("org_1", "big", "user_9"))
    assert left.tokens == 5
