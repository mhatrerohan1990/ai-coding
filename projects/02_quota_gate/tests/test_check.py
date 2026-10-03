from concurrent.futures import ThreadPoolExecutor

from conftest import bearer, mint_token

NOW = 1_727_740_000


def put_policy(client, admin, policy_id, subject="*", action="*", limit=60, window=60, burst=20):
    body = {
        "match": {"subject": subject, "action": action},
        "limit": limit,
        "window_seconds": window,
        "burst": burst,
    }
    res = client.put(f"/v1/tenants/org_1/policies/{policy_id}", json=body, headers=admin)
    assert res.status_code == 201


def check(client, headers, **body):
    payload = {"tenant_id": "org_1", "subject": "user_9", "action": "users.export", **body}
    return client.post("/v1/check", json=payload, headers=headers)


def test_check_against_matching_policy_is_allowed(client, admin, svc):
    put_policy(client, admin, "export-cap", action="users.export", burst=20)

    res = check(client, svc)

    assert res.status_code == 200
    assert res.get_json() == {
        "allow": True,
        "remaining": 19,  # fresh bucket is full (burst=20), minus cost 1
        "reset_at": NOW + 1,  # refills 1 token/s (60 per 60s), so 1s to be full again
        "matched_policies": ["export-cap"],
    }


def test_cost_defaults_to_one_and_explicit_cost_is_charged(client, admin, svc):
    put_policy(client, admin, "p", burst=20, limit=60, window=60)

    res = check(client, svc, cost=5)

    body = res.get_json()
    assert body["remaining"] == 15
    assert body["reset_at"] == NOW + 5  # 5 tokens at 1 token/s


def test_rate_limit_headers_report_limit_and_remaining(client, admin, svc):
    put_policy(client, admin, "p", limit=100, window=60, burst=20)

    res = check(client, svc)

    assert res.headers["X-RateLimit-Limit"] == "100"
    assert res.headers["X-RateLimit-Remaining"] == "19"


def test_only_policies_matching_subject_and_action_are_used(client, admin, svc):
    put_policy(client, admin, "reads", action="api.read")
    put_policy(client, admin, "exports", action="users.export")
    put_policy(client, admin, "someone-else", subject="user_1")

    res = check(client, svc, subject="user_9", action="users.export")

    assert res.get_json()["matched_policies"] == ["exports"]


def test_exact_subject_match_is_used(client, admin, svc):
    put_policy(client, admin, "mine", subject="user_9", action="*")

    assert check(client, svc).get_json()["matched_policies"] == ["mine"]


# --- auth on the hot path ---------------------------------------------------


def test_check_requires_a_token(client):
    res = client.post("/v1/check", json={"tenant_id": "org_1", "subject": "u", "action": "a"})
    assert res.status_code == 401


def test_admin_scope_alone_cannot_check(client, admin):
    assert check(client, admin).status_code == 403


def test_service_token_cannot_check_another_tenant(client, svc):
    res = check(client, svc, tenant_id="org_2")

    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "forbidden"


def test_check_only_sees_policies_of_the_tokens_tenant(client, admin):
    put_policy(client, admin, "org1-policy", burst=7)
    org2_admin = bearer(mint_token(tid="org_2"))
    client.put(
        "/v1/tenants/org_2/policies/org2-policy",
        json={"match": {"subject": "*", "action": "*"}, "limit": 1, "window_seconds": 60, "burst": 1},
        headers=org2_admin,
    )
    org1_svc = bearer(mint_token(sub="svc", scp=["quota.check"]))

    res = check(client, org1_svc)

    assert res.get_json()["matched_policies"] == ["org1-policy"]


# --- stateful buckets -------------------------------------------------------


def test_successive_checks_decrement_remaining(client, admin, svc):
    put_policy(client, admin, "p", burst=20)

    remaining = [check(client, svc).get_json()["remaining"] for _ in range(3)]

    assert remaining == [19, 18, 17]


def test_check_over_the_limit_is_429_with_same_body_shape(client, admin, svc):
    put_policy(client, admin, "p", burst=2, limit=60, window=60)
    check(client, svc)
    check(client, svc)

    res = check(client, svc)

    assert res.status_code == 429
    assert res.get_json() == {
        "allow": False,
        "remaining": 0,
        "reset_at": NOW + 2,  # empty bucket, 1 token/s, 2 tokens to be full again
        "matched_policies": ["p"],
    }
    assert res.headers["X-RateLimit-Limit"] == "60"
    assert res.headers["X-RateLimit-Remaining"] == "0"
    assert res.headers["Retry-After"] == "1"


def test_retry_after_is_whole_seconds_until_the_request_could_succeed(client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=30, window=60)  # 0.5 token/s
    check(client, svc)

    assert check(client, svc).headers["Retry-After"] == "2"


def test_retry_after_is_at_least_one_second(client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=6000, window=60)  # 100 tokens/s
    check(client, svc)

    res = check(client, svc)

    assert res.status_code == 429
    assert res.headers["Retry-After"] == "1"


def test_denied_check_does_not_consume_quota(client, admin, svc, clock):
    put_policy(client, admin, "p", burst=1, limit=60, window=60)
    check(client, svc)
    for _ in range(5):
        assert check(client, svc).status_code == 429

    clock.now += 1  # exactly one token refilled; earlier denials must not have gone negative

    assert check(client, svc).status_code == 200


def test_quota_refills_after_the_window(client, admin, svc, clock):
    put_policy(client, admin, "p", burst=2, limit=60, window=60)
    check(client, svc)
    check(client, svc)
    assert check(client, svc).status_code == 429

    clock.now += 1
    res = check(client, svc)

    assert res.status_code == 200
    assert res.get_json()["remaining"] == 0


def test_partial_refill_reports_whole_tokens_only(client, admin, svc, clock):
    put_policy(client, admin, "p", burst=3, limit=30, window=60)  # 0.5 token/s
    check(client, svc)  # 2 left
    clock.now += 1  # +0.5 -> 2.5

    res = check(client, svc)  # 1.5 left

    assert res.get_json()["remaining"] == 1


def test_refill_never_exceeds_burst(client, admin, svc, clock):
    put_policy(client, admin, "p", burst=5, limit=60, window=60)
    check(client, svc, cost=5)
    clock.now += 100_000

    assert check(client, svc).get_json()["remaining"] == 4


def test_cost_larger_than_remaining_is_denied_without_consuming(client, admin, svc):
    put_policy(client, admin, "p", burst=5, limit=60, window=60)
    check(client, svc, cost=3)

    assert check(client, svc, cost=3).status_code == 429
    assert check(client, svc, cost=2).get_json()["remaining"] == 0


def test_each_subject_gets_its_own_bucket(client, admin, svc):
    put_policy(client, admin, "p", burst=1)
    assert check(client, svc, subject="user_9").status_code == 200
    assert check(client, svc, subject="user_9").status_code == 429

    assert check(client, svc, subject="user_1").status_code == 200


def test_each_tenant_gets_its_own_bucket_even_with_same_policy_id_and_subject(client, admin, svc):
    put_policy(client, admin, "p", burst=1)
    org2_admin = bearer(mint_token(tid="org_2"))
    client.put(
        "/v1/tenants/org_2/policies/p",
        json={"match": {"subject": "*", "action": "*"}, "limit": 60, "window_seconds": 60, "burst": 1},
        headers=org2_admin,
    )
    org2_svc = bearer(mint_token(tid="org_2", sub="svc_2", scp=["quota.check"]))
    check(client, svc)
    assert check(client, svc).status_code == 429

    assert check(client, org2_svc, tenant_id="org_2").status_code == 200


def test_concurrent_checks_never_both_take_the_last_token(app, client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)

    def hit(_):
        return check(app.test_client(), svc).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(hit, range(48)))

    assert statuses.count(200) == 1
    assert statuses.count(429) == 47


# --- replacing or deleting a policy resets its buckets (open question 3) ----


def put_action_policy(client, admin, policy_id, action, burst=2):
    put_policy(client, admin, policy_id, action=action, burst=burst, limit=1, window=3600)


def exhaust(client, svc, action="users.export", subject="user_9"):
    while check(client, svc, action=action, subject=subject).status_code == 200:
        pass


def test_replacing_a_policy_resets_its_bucket(client, admin, svc):
    put_policy(client, admin, "p", burst=2, limit=1, window=3600)
    exhaust(client, svc)

    res = client.put(
        "/v1/tenants/org_1/policies/p",
        json={"match": {"subject": "*", "action": "*"}, "limit": 1, "window_seconds": 3600, "burst": 2},
        headers=admin,
    )
    assert res.status_code == 200

    after = check(client, svc)
    assert after.status_code == 200
    assert after.get_json()["remaining"] == 1  # a full bucket of 2, minus this check


def test_replacement_bucket_is_full_at_the_new_burst(client, admin, svc):
    put_policy(client, admin, "p", burst=2, limit=1, window=3600)
    exhaust(client, svc)

    put_policy_replace(client, admin, "p", burst=5)

    assert check(client, svc).get_json()["remaining"] == 4


def test_replacing_with_a_smaller_burst_starts_at_the_smaller_burst(client, admin, svc):
    put_policy(client, admin, "p", burst=10, limit=1, window=3600)
    check(client, svc)

    put_policy_replace(client, admin, "p", burst=3)

    assert check(client, svc).get_json()["remaining"] == 2


def test_replacing_resets_every_subjects_bucket(client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)
    exhaust(client, svc, subject="user_1")
    exhaust(client, svc, subject="user_2")

    put_policy_replace(client, admin, "p", burst=1)

    assert check(client, svc, subject="user_1").status_code == 200
    assert check(client, svc, subject="user_2").status_code == 200


def test_replacing_one_policy_leaves_other_policies_buckets_alone(client, admin, svc):
    put_action_policy(client, admin, "p", action="a1", burst=1)
    put_action_policy(client, admin, "q", action="a2", burst=1)
    exhaust(client, svc, action="a1")
    exhaust(client, svc, action="a2")

    put_policy_replace(client, admin, "p", burst=1, action="a1")

    assert check(client, svc, action="a1").status_code == 200  # p was reset
    assert check(client, svc, action="a2").status_code == 429  # q was not


def test_replacing_a_policy_does_not_reset_the_same_id_in_another_tenant(client, admin):
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)
    org2_admin = bearer(mint_token(tid="org_2"))
    org2_svc = bearer(mint_token(tid="org_2", sub="svc_2", scp=["quota.check"]))
    client.put(
        "/v1/tenants/org_2/policies/p",
        json={"match": {"subject": "*", "action": "*"}, "limit": 1, "window_seconds": 3600, "burst": 1},
        headers=org2_admin,
    )
    assert check(client, org2_svc, tenant_id="org_2").status_code == 200
    assert check(client, org2_svc, tenant_id="org_2").status_code == 429

    put_policy_replace(client, admin, "p", burst=1)  # org_1's p

    assert check(client, org2_svc, tenant_id="org_2").status_code == 429


def test_invalid_replacement_does_not_reset_the_bucket(client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)
    exhaust(client, svc)

    bad = client.put("/v1/tenants/org_1/policies/p", json={"limit": 0}, headers=admin)

    assert bad.status_code == 400
    assert check(client, svc).status_code == 429


def test_deleting_and_recreating_a_policy_starts_with_a_fresh_bucket(client, admin, svc):
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)
    exhaust(client, svc)

    client.delete("/v1/tenants/org_1/policies/p", headers=admin)
    put_policy(client, admin, "p", burst=1, limit=1, window=3600)

    assert check(client, svc).status_code == 200


def put_policy_replace(client, admin, policy_id, burst, action="*"):
    res = client.put(
        f"/v1/tenants/org_1/policies/{policy_id}",
        json={"match": {"subject": "*", "action": action}, "limit": 1, "window_seconds": 3600, "burst": burst},
        headers=admin,
    )
    assert res.status_code == 200


# --- idle buckets are evicted without changing behaviour ---------------------


def test_checks_for_many_abandoned_subjects_do_not_pile_up(tmp_path, clock):
    from quota_gate.app import create_app
    from quota_gate.buckets import BucketStore
    from conftest import ISSUER, SECRET

    store = BucketStore(sweep_interval=60.0)
    app = create_app(str(tmp_path / "evict.db"), SECRET, ISSUER, clock=clock, buckets=store)
    client = app.test_client()
    admin_headers = bearer(mint_token())
    svc_headers = bearer(mint_token(sub="svc_1", scp=["quota.check"]))
    put_policy(client, admin_headers, "p", limit=60, window=60, burst=3)  # 1 token/s

    for i in range(200):
        assert check(client, svc_headers, subject=f"user_{i}").status_code == 200
    assert len(store) == 200

    clock.now += 3600  # every bucket has long been full again
    assert check(client, svc_headers, subject="someone-new").status_code == 200

    assert len(store) == 1


def test_a_subject_whose_bucket_was_evicted_is_treated_as_fresh(tmp_path, clock):
    from quota_gate.app import create_app
    from quota_gate.buckets import BucketStore
    from conftest import ISSUER, SECRET

    store = BucketStore(sweep_interval=1.0)
    client = create_app(str(tmp_path / "e2.db"), SECRET, ISSUER, clock=clock, buckets=store).test_client()
    admin_headers = bearer(mint_token())
    svc_headers = bearer(mint_token(sub="svc_1", scp=["quota.check"]))
    put_policy(client, admin_headers, "p", limit=60, window=60, burst=3)
    for _ in range(3):
        check(client, svc_headers)
    assert check(client, svc_headers).status_code == 429

    clock.now += 10  # long enough to be full again, and for a sweep to run
    check(client, svc_headers, subject="other")  # triggers the sweep
    res = check(client, svc_headers)

    assert res.status_code == 200
    assert res.get_json()["remaining"] == 2
