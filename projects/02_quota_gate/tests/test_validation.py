import pytest

from conftest import bearer, mint_token

GOOD = {
    "match": {"subject": "*", "action": "users.export"},
    "limit": 100,
    "window_seconds": 60,
    "burst": 20,
}


def put(client, headers, body, policy_id="p", tenant="org_1"):
    return client.put(f"/v1/tenants/{tenant}/policies/{policy_id}", json=body, headers=headers)


def assert_invalid(res, mentions=None):
    assert res.status_code == 400
    error = res.get_json()["error"]
    assert error["code"] == "invalid_request"
    if mentions:
        assert mentions in error["message"]


# --- PUT: policy_id ---------------------------------------------------------


@pytest.mark.parametrize(
    "policy_id", ["Upper", "-leading-dash", "_leading", "has%20space", "a" * 65, "dot.ted", "a%0A"]
)
def test_invalid_policy_id_is_400(client, admin, policy_id):
    assert_invalid(put(client, admin, GOOD, policy_id=policy_id), "policy_id")


@pytest.mark.parametrize("policy_id", ["a", "0", "a" * 64, "export-cap", "x_1-y"])
def test_valid_policy_ids_are_accepted(client, admin, policy_id):
    assert put(client, admin, GOOD, policy_id=policy_id).status_code == 201


# --- PUT: numeric fields ----------------------------------------------------


@pytest.mark.parametrize("field", ["limit", "window_seconds", "burst"])
@pytest.mark.parametrize("bad", [0, -1, 1.5, 5.0, "10", None, True, [1], {"a": 1}])
def test_numeric_fields_must_be_integers_of_at_least_one(client, admin, field, bad):
    assert_invalid(put(client, admin, {**GOOD, field: bad}), field)


@pytest.mark.parametrize("field", ["limit", "window_seconds", "burst"])
def test_missing_numeric_field_is_400(client, admin, field):
    body = {k: v for k, v in GOOD.items() if k != field}
    assert_invalid(put(client, admin, body), field)


def test_window_seconds_upper_bound_is_one_day(client, admin):
    assert_invalid(put(client, admin, {**GOOD, "window_seconds": 86401}), "window_seconds")
    assert put(client, admin, {**GOOD, "window_seconds": 86400}).status_code == 201


def test_minimum_values_are_accepted(client, admin):
    body = {**GOOD, "limit": 1, "window_seconds": 1, "burst": 1}
    assert put(client, admin, body).status_code == 201


# --- PUT: match -------------------------------------------------------------


@pytest.mark.parametrize(
    "match",
    [
        None,
        "*",
        [],
        {},
        {"subject": "*"},
        {"action": "*"},
        {"subject": "", "action": "*"},
        {"subject": "*", "action": ""},
        {"subject": 1, "action": "*"},
        {"subject": "*", "action": None},
        {"subject": "*", "action": "a", "extra": 1},
    ],
)
def test_malformed_match_is_400(client, admin, match):
    assert_invalid(put(client, admin, {**GOOD, "match": match}), "match")


def test_missing_match_is_400(client, admin):
    body = {k: v for k, v in GOOD.items() if k != "match"}
    assert_invalid(put(client, admin, body), "match")


# --- PUT: body shape --------------------------------------------------------


def test_unknown_fields_are_rejected(client, admin):
    assert_invalid(put(client, admin, {**GOOD, "colour": "red"}), "colour")


def test_body_cannot_override_tenant_or_policy_id(client, admin):
    res = put(client, admin, {**GOOD, "tenant_id": "org_2", "policy_id": "other"})

    assert_invalid(res)
    # nothing was stored under any of the names
    assert client.get("/v1/tenants/org_1/policies/p", headers=admin).status_code == 404
    assert client.get("/v1/tenants/org_1/policies/other", headers=admin).status_code == 404


@pytest.mark.parametrize("body", [[], "text", 5, None])
def test_body_must_be_a_json_object(client, admin, body):
    assert_invalid(put(client, admin, body), "JSON object")


def test_malformed_json_is_400_not_500(client, admin):
    res = client.put(
        "/v1/tenants/org_1/policies/p",
        data="{not json",
        content_type="application/json",
        headers=admin,
    )
    assert_invalid(res, "JSON object")


def test_missing_body_is_400(client, admin):
    assert_invalid(client.put("/v1/tenants/org_1/policies/p", headers=admin), "JSON object")


def test_invalid_put_does_not_touch_an_existing_policy(client, admin):
    put(client, admin, GOOD)

    assert_invalid(put(client, admin, {**GOOD, "limit": 0}))

    stored = client.get("/v1/tenants/org_1/policies/p", headers=admin).get_json()
    assert stored["limit"] == 100


def test_stored_policy_contains_only_known_fields(client, admin):
    res = put(client, admin, GOOD)

    assert set(res.get_json()) == {
        "policy_id", "tenant_id", "match", "limit", "window_seconds", "burst"
    }


# --- ordering: authn/authz before validation --------------------------------


def test_invalid_body_without_token_is_401(client):
    res = client.put("/v1/tenants/org_1/policies/p", json={"limit": 0})
    assert res.status_code == 401


def test_invalid_body_for_another_tenant_is_403_not_400(client, admin):
    assert put(client, admin, {"limit": 0}, tenant="org_2").status_code == 403


# --- check: body validation -------------------------------------------------


def post_check(client, headers, body):
    return client.post("/v1/check", json=body, headers=headers)


CHECK = {"tenant_id": "org_1", "subject": "user_9", "action": "users.export"}


@pytest.mark.parametrize("field", ["tenant_id", "subject", "action"])
def test_check_missing_required_field_is_400(client, svc, field):
    body = {k: v for k, v in CHECK.items() if k != field}
    assert_invalid(post_check(client, svc, body), field)


@pytest.mark.parametrize("field", ["tenant_id", "subject", "action"])
@pytest.mark.parametrize("bad", ["", 7, None, ["x"], True])
def test_check_required_fields_must_be_non_empty_strings(client, svc, field, bad):
    assert_invalid(post_check(client, svc, {**CHECK, field: bad}), field)


@pytest.mark.parametrize("cost", [0, -1, 1.5, 2.0, "1", None, True, [1]])
def test_check_cost_must_be_an_integer_of_at_least_one(client, svc, cost):
    assert_invalid(post_check(client, svc, {**CHECK, "cost": cost}), "cost")


@pytest.mark.parametrize("body", [[], "text", 5, None])
def test_check_body_must_be_a_json_object(client, svc, body):
    assert_invalid(post_check(client, svc, body), "JSON object")


def test_check_malformed_json_is_400(client, svc):
    res = client.post("/v1/check", data="{oops", content_type="application/json", headers=svc)
    assert_invalid(res, "JSON object")


def test_check_ignores_unknown_fields(client, admin, svc):
    put(client, admin, GOOD)

    assert post_check(client, svc, {**CHECK, "trace_id": "abc"}).status_code == 200


def test_invalid_check_does_not_consume_quota(client, admin, svc):
    put(client, admin, {**GOOD, "burst": 1, "limit": 1, "window_seconds": 3600})
    assert_invalid(post_check(client, svc, {**CHECK, "cost": 0}))

    assert post_check(client, svc, CHECK).status_code == 200


def test_check_without_token_and_invalid_body_is_401(client):
    assert client.post("/v1/check", json={"cost": 0}).status_code == 401


def test_check_with_wrong_scope_and_invalid_body_is_403(client, admin):
    assert client.post("/v1/check", json={"cost": 0}, headers=admin).status_code == 403


def test_check_for_another_tenant_is_403_not_400(client, svc):
    res = post_check(client, svc, {**CHECK, "tenant_id": "org_2", "cost": 1})
    assert res.status_code == 403


# --- no matching policy (open question 1: deny) ----------------------------


def test_check_with_no_matching_policy_is_denied_and_says_so(client, svc):
    res = post_check(client, svc, CHECK)

    assert res.status_code == 429
    assert res.get_json() == {
        "allow": False,
        "remaining": 0,
        "reset_at": 1_727_740_000,  # nothing to wait for: there is no bucket
        "matched_policies": [],
    }
    assert res.headers["Retry-After"] == "1"
    # no policy means no limit to report
    assert "X-RateLimit-Limit" not in res.headers
    assert "X-RateLimit-Remaining" not in res.headers


def test_policy_for_a_different_action_does_not_apply(client, admin, svc):
    put(client, admin, {**GOOD, "match": {"subject": "*", "action": "api.read"}, "burst": 5})

    res = post_check(client, svc, CHECK)

    assert res.status_code == 429
    assert res.get_json()["matched_policies"] == []


def test_policy_for_a_different_subject_does_not_apply(client, admin, svc):
    put(client, admin, {**GOOD, "match": {"subject": "user_1", "action": "*"}})

    assert post_check(client, svc, CHECK).status_code == 429


def test_other_tenants_policies_do_not_grant_access(client, svc):
    org2_admin = bearer(mint_token(tid="org_2"))
    put(client, org2_admin, GOOD, tenant="org_2")

    assert post_check(client, svc, CHECK).status_code == 429


def test_wildcard_policy_grants_access(client, admin, svc):
    put(client, admin, {**GOOD, "match": {"subject": "*", "action": "*"}})

    assert post_check(client, svc, CHECK).status_code == 200


def test_deleting_the_only_policy_revokes_access(client, admin, svc):
    put(client, admin, GOOD)
    assert post_check(client, svc, CHECK).status_code == 200

    client.delete("/v1/tenants/org_1/policies/p", headers=admin)

    res = post_check(client, svc, CHECK)
    assert res.status_code == 429
    assert res.get_json()["matched_policies"] == []
