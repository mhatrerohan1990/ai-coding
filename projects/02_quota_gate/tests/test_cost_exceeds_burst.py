"""Open question 4: a cost larger than a policy's burst can never succeed -> 400."""
HOUR = 3600


def put(client, admin, policy_id, subject="*", action="*", burst=5):
    res = client.put(
        f"/v1/tenants/org_1/policies/{policy_id}",
        json={"match": {"subject": subject, "action": action},
              "limit": 1, "window_seconds": HOUR, "burst": burst},
        headers=admin,
    )
    assert res.status_code in (200, 201)


def check(client, svc, subject="user_9", action="users.export", **extra):
    body = {"tenant_id": "org_1", "subject": subject, "action": action, **extra}
    return client.post("/v1/check", json=body, headers=svc)


def test_cost_above_burst_is_400_and_names_the_policy(client, admin, svc):
    put(client, admin, "export-cap", burst=5)

    res = check(client, svc, cost=6)

    assert res.status_code == 400
    error = res.get_json()["error"]
    assert error["code"] == "invalid_request"
    assert "export-cap" in error["message"]
    assert "cost 6" in error["message"] and "burst 5" in error["message"]


def test_400_is_not_a_rate_limit_so_it_has_no_retry_hint(client, admin, svc):
    put(client, admin, "p", burst=5)

    res = check(client, svc, cost=6)

    assert "Retry-After" not in res.headers
    assert "allow" not in res.get_json()


def test_cost_equal_to_burst_is_allowed_on_a_full_bucket(client, admin, svc):
    put(client, admin, "p", burst=5)

    res = check(client, svc, cost=5)

    assert res.status_code == 200
    assert res.get_json()["remaining"] == 0


def test_cost_within_burst_but_above_current_tokens_is_still_429(client, admin, svc):
    put(client, admin, "p", burst=5)
    check(client, svc, cost=3)  # 2 left

    res = check(client, svc, cost=4)  # fits the burst, just not right now

    assert res.status_code == 429
    assert res.get_json()["allow"] is False


def test_rejected_cost_consumes_nothing(client, admin, svc):
    put(client, admin, "p", burst=5)
    assert check(client, svc, cost=10).status_code == 400

    res = check(client, svc, cost=5)  # the full bucket is still there

    assert res.status_code == 200
    assert res.get_json()["remaining"] == 0


def test_any_tied_policy_with_too_small_a_burst_rejects_and_is_named(client, admin, svc):
    put(client, admin, "roomy", "*", "users.export", burst=10)
    put(client, admin, "tight", "*", "users.export", burst=3)

    res = check(client, svc, cost=5)

    assert res.status_code == 400
    assert "tight" in res.get_json()["error"]["message"]
    assert "roomy" not in res.get_json()["error"]["message"]


def test_outranked_policies_are_ignored_for_the_burst_rule(client, admin, svc):
    put(client, admin, "specific", "user_9", "users.export", burst=10)
    put(client, admin, "general", "*", "*", burst=2)

    assert check(client, svc, cost=5).status_code == 200


def test_no_matching_policy_is_still_a_denial_not_a_400(client, svc):
    res = check(client, svc, cost=1000)

    assert res.status_code == 429
    assert res.get_json()["matched_policies"] == []


def test_raising_the_burst_makes_the_same_cost_valid(client, admin, svc):
    put(client, admin, "p", burst=5)
    assert check(client, svc, cost=8).status_code == 400

    put(client, admin, "p", burst=8)

    assert check(client, svc, cost=8).status_code == 200
