"""Which policies apply to a check, and how several applied policies combine."""
import pytest

from conftest import bearer, mint_token
from quota_gate.services import specificity

NOW = 1_727_740_000
HOUR = 3600  # long window: refill is negligible unless a test moves the clock


def put(client, admin, policy_id, subject="*", action="*", limit=1, window=HOUR, burst=10):
    res = client.put(
        f"/v1/tenants/org_1/policies/{policy_id}",
        json={
            "match": {"subject": subject, "action": action},
            "limit": limit,
            "window_seconds": window,
            "burst": burst,
        },
        headers=admin,
    )
    assert res.status_code in (200, 201)


def check(client, svc, subject="user_9", action="users.export", **extra):
    body = {"tenant_id": "org_1", "subject": subject, "action": action, **extra}
    return client.post("/v1/check", json=body, headers=svc)


# --- specificity levels -----------------------------------------------------


@pytest.mark.parametrize(
    "subject, action, expected",
    [("u", "a", 3), ("u", "*", 2), ("*", "a", 1), ("*", "*", 0)],
)
def test_specificity_values_follow_the_spec_table(subject, action, expected):
    assert specificity({"match": {"subject": subject, "action": action}}) == expected


def test_only_the_most_specific_policy_applies_walking_down_the_levels(client, admin, svc):
    put(client, admin, "exact-exact", "user_9", "users.export")
    put(client, admin, "exact-any", "user_9", "*")
    put(client, admin, "any-exact", "*", "users.export")
    put(client, admin, "any-any", "*", "*")

    seen = []
    for policy_id in ["exact-exact", "exact-any", "any-exact", "any-any"]:
        seen.append(check(client, svc).get_json()["matched_policies"])
        client.delete(f"/v1/tenants/org_1/policies/{policy_id}", headers=admin)

    assert seen == [["exact-exact"], ["exact-any"], ["any-exact"], ["any-any"]]


def test_exact_subject_beats_exact_action(client, admin, svc):
    """Spec order (open question 5): who (2) outranks what (1)."""
    put(client, admin, "per-user", "user_9", "*", burst=1000)
    put(client, admin, "export-cap", "*", "users.export", burst=5)

    res = check(client, svc)

    assert res.get_json()["matched_policies"] == ["per-user"]
    assert res.get_json()["remaining"] == 999


def test_lower_specificity_policies_are_ignored_entirely(client, admin, svc):
    put(client, admin, "specific", "user_9", "users.export", burst=3)
    put(client, admin, "general", "*", "*", burst=1)

    # the general policy would deny the second check; it must play no part
    assert check(client, svc).status_code == 200
    assert check(client, svc).status_code == 200


def test_an_applied_policy_does_not_charge_the_ones_it_outranks(client, admin, svc):
    put(client, admin, "specific", "user_9", "users.export", burst=5)
    put(client, admin, "general", "*", "*", burst=4)
    check(client, svc)
    check(client, svc)

    client.delete("/v1/tenants/org_1/policies/specific", headers=admin)

    # general was never touched: its bucket is still full (4), minus this check
    assert check(client, svc).get_json()["remaining"] == 3


def test_specificity_is_decided_per_request(client, admin, svc):
    put(client, admin, "just-user-9", "user_9", "*", burst=2)
    put(client, admin, "everyone", "*", "*", burst=7)

    assert check(client, svc, subject="user_9").get_json()["matched_policies"] == ["just-user-9"]
    assert check(client, svc, subject="user_1").get_json()["matched_policies"] == ["everyone"]


# --- ties: every top-specificity policy applies (AND) -----------------------


def test_all_tied_policies_apply_and_are_listed(client, admin, svc):
    put(client, admin, "b", "*", "users.export")
    put(client, admin, "a", "*", "users.export")

    assert check(client, svc).get_json()["matched_policies"] == ["a", "b"]


def test_a_tie_is_allowed_only_if_every_policy_has_quota(client, admin, svc):
    put(client, admin, "roomy", "*", "users.export", burst=10)
    put(client, admin, "tight", "*", "users.export", burst=1)

    assert check(client, svc).status_code == 200
    res = check(client, svc)

    assert res.status_code == 429  # tight is empty although roomy has plenty
    assert res.get_json()["allow"] is False
    assert res.get_json()["matched_policies"] == ["roomy", "tight"]


def test_remaining_and_limit_come_from_the_most_constrained_policy(client, admin, svc):
    put(client, admin, "big", "*", "users.export", limit=100, burst=5)
    put(client, admin, "small", "*", "users.export", limit=7, burst=3)

    res = check(client, svc)

    assert res.get_json()["remaining"] == 2  # small: 3 - 1, big has 4
    assert res.headers["X-RateLimit-Limit"] == "7"
    assert res.headers["X-RateLimit-Remaining"] == "2"


def test_reset_at_is_that_of_the_most_constrained_policy(client, admin, svc):
    # both refill-able: big 1 token/s, small 0.5 token/s
    put(client, admin, "big", "*", "users.export", limit=60, window=60, burst=5)
    put(client, admin, "small", "*", "users.export", limit=30, window=60, burst=3)

    res = check(client, svc)

    # small is the most constrained (2 of 3 left): 1 token missing at 0.5/s = 2s.
    # big alone would say 1s.
    assert res.get_json()["reset_at"] == NOW + 2


def test_a_denial_by_one_policy_charges_none_of_them(client, admin, svc):
    put(client, admin, "roomy", "*", "users.export", burst=3)
    put(client, admin, "tight", "*", "users.export", burst=1)
    assert check(client, svc).status_code == 200  # roomy 2, tight 0
    assert check(client, svc).status_code == 429  # must NOT charge roomy
    assert check(client, svc).status_code == 429

    put(client, admin, "tight", "*", "users.export", burst=5)  # replace -> tight is full again

    # roomy had 2 left; one more check leaves 1. Had denials charged it, it would be 0.
    res = check(client, svc)
    assert res.status_code == 200
    assert res.get_json()["remaining"] == 1


def test_retry_after_waits_for_every_policy_that_denied(client, admin, svc):
    put(client, admin, "fast", "*", "users.export", limit=60, window=60, burst=1)  # 1/s
    put(client, admin, "slow", "*", "users.export", limit=30, window=60, burst=1)  # 0.5/s
    check(client, svc)

    res = check(client, svc)

    assert res.status_code == 429
    assert res.headers["Retry-After"] == "2"  # fast needs 1s, slow needs 2s


def test_retry_after_ignores_policies_that_would_have_allowed(client, admin, svc):
    put(client, admin, "roomy", "*", "users.export", limit=1, window=3600, burst=100)
    put(client, admin, "slow", "*", "users.export", limit=30, window=60, burst=1)  # 0.5/s
    check(client, svc)

    assert check(client, svc).headers["Retry-After"] == "2"


def test_denied_response_reports_the_most_constrained_policy(client, admin, svc):
    put(client, admin, "roomy", "*", "users.export", limit=100, burst=10)
    put(client, admin, "tight", "*", "users.export", limit=7, burst=1)
    check(client, svc)

    res = check(client, svc)

    assert res.get_json()["remaining"] == 0
    assert res.headers["X-RateLimit-Limit"] == "7"
    assert res.headers["X-RateLimit-Remaining"] == "0"


def test_each_tied_policy_keeps_a_bucket_per_subject(client, admin, svc):
    put(client, admin, "a", "*", "users.export", burst=1)
    put(client, admin, "b", "*", "users.export", burst=1)
    assert check(client, svc, subject="user_1").status_code == 200
    assert check(client, svc, subject="user_1").status_code == 429

    assert check(client, svc, subject="user_2").status_code == 200


def test_a_cost_is_charged_to_every_tied_policy(client, admin, svc):
    put(client, admin, "a", "*", "users.export", burst=10)
    put(client, admin, "b", "*", "users.export", burst=6)

    assert check(client, svc, cost=4).get_json()["remaining"] == 2  # b: 6 - 4
    put(client, admin, "b", "*", "users.export", burst=100)  # reset b only
    # a was charged 4 earlier: 10 - 4 = 6 left, so cost 7 must be denied by a alone
    assert check(client, svc, cost=7).status_code == 429


def test_other_tenants_policies_never_tie_with_ours(client, admin, svc):
    put(client, admin, "mine", "*", "users.export")
    org2_admin = bearer(mint_token(tid="org_2"))
    client.put(
        "/v1/tenants/org_2/policies/theirs",
        json={"match": {"subject": "*", "action": "users.export"}, "limit": 1,
              "window_seconds": HOUR, "burst": 1},
        headers=org2_admin,
    )

    assert check(client, svc).get_json()["matched_policies"] == ["mine"]
