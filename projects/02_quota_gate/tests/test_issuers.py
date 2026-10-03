"""Follow-up requirement: partner org_3 has its own IdP and secret.

Tokens from the partner issuer may act only on org_3. Tokens from our issuer may act on
any tenant except org_3. Tenant binding (token tid == tenant acted on) is unchanged.
"""
import pytest

from conftest import (
    ISSUER, PARTNER_ISSUER, PARTNER_SECRET, SECRET, bearer, mint_token, partner_token,
)
from quota_gate.app import create_app

POLICY = {
    "match": {"subject": "*", "action": "api.read"},
    "limit": 60,
    "window_seconds": 60,
    "burst": 5,
}


def policy_url(tenant, policy_id="p"):
    return f"/v1/tenants/{tenant}/policies/{policy_id}"


def check(client, headers, tenant, subject="u1", action="api.read"):
    body = {"tenant_id": tenant, "subject": subject, "action": action}
    return client.post("/v1/check", json=body, headers=headers)


def assert_error(res, status, code):
    assert res.status_code == status
    assert res.get_json()["error"]["code"] == code


partner_admin = lambda **kw: bearer(partner_token(scp=["quota.admin"], **kw))  # noqa: E731
partner_check = lambda **kw: bearer(partner_token(sub="partner_svc", scp=["quota.check"], **kw))  # noqa: E731


# --- the partner can act on org_3 -------------------------------------------


def test_partner_admin_can_manage_org3_policies(client):
    h = partner_admin()

    assert client.put(policy_url("org_3"), json=POLICY, headers=h).status_code == 201
    assert client.put(policy_url("org_3"), json=POLICY, headers=h).status_code == 200
    assert client.get(policy_url("org_3"), headers=h).get_json()["tenant_id"] == "org_3"
    assert client.delete(policy_url("org_3"), headers=h).status_code == 204


def test_partner_service_token_can_check_org3(client):
    client.put(policy_url("org_3"), json=POLICY, headers=partner_admin())

    res = check(client, partner_check(), "org_3")

    assert res.status_code == 200
    assert res.get_json()["matched_policies"] == ["p"]


def test_partner_tokens_keep_the_same_scope_split(client):
    client.put(policy_url("org_3"), json=POLICY, headers=partner_admin())

    assert_error(client.get(policy_url("org_3"), headers=partner_check()), 403, "forbidden")
    assert_error(check(client, partner_admin(), "org_3"), 403, "forbidden")


# --- the partner can act ONLY on org_3 --------------------------------------


@pytest.mark.parametrize("tenant", ["org_1", "org_2", "org_99"])
def test_partner_token_cannot_touch_other_tenants(client, tenant):
    h = partner_admin()  # tid=org_3

    assert_error(client.put(policy_url(tenant), json=POLICY, headers=h), 403, "forbidden")
    assert_error(client.get(policy_url(tenant), headers=h), 403, "forbidden")
    assert_error(client.delete(policy_url(tenant), headers=h), 403, "forbidden")
    assert_error(check(client, partner_check(), tenant), 403, "forbidden")


@pytest.mark.parametrize("tenant", ["org_1", "org_2", "org_99"])
def test_partner_token_claiming_another_tid_is_still_refused(client, tenant):
    """Valid signature, tid matches the path, but this issuer may only speak for org_3."""
    h = bearer(partner_token(tid=tenant, scp=["quota.admin", "quota.check"]))

    assert_error(client.put(policy_url(tenant), json=POLICY, headers=h), 403, "forbidden")
    assert_error(check(client, h, tenant), 403, "forbidden")
    # and nothing was written for that tenant
    own = bearer(mint_token(tid=tenant))
    assert_error(client.get(policy_url(tenant), headers=own), 404, "not_found")


# --- our issuer can act on anything EXCEPT org_3 ----------------------------


@pytest.mark.parametrize("tenant", ["org_1", "org_2", "org_99", "tenant-with-dash"])
def test_our_issuer_still_works_for_other_tenants(client, tenant):
    h = bearer(mint_token(tid=tenant))

    assert client.put(policy_url(tenant), json=POLICY, headers=h).status_code == 201
    assert client.get(policy_url(tenant), headers=h).status_code == 200


def test_our_issuer_cannot_act_on_org3_even_with_matching_tid(client):
    ours = bearer(mint_token(tid="org_3", scp=["quota.admin", "quota.check"]))

    assert_error(client.put(policy_url("org_3"), json=POLICY, headers=ours), 403, "forbidden")
    assert_error(client.get(policy_url("org_3"), headers=ours), 403, "forbidden")
    assert_error(client.delete(policy_url("org_3"), headers=ours), 403, "forbidden")
    assert_error(check(client, ours, "org_3"), 403, "forbidden")


def test_our_issuer_cannot_read_or_wipe_what_the_partner_created(client):
    client.put(policy_url("org_3"), json=POLICY, headers=partner_admin())
    ours = bearer(mint_token(tid="org_3"))

    assert_error(client.get(policy_url("org_3"), headers=ours), 403, "forbidden")
    assert_error(client.delete(policy_url("org_3"), headers=ours), 403, "forbidden")
    assert client.get(policy_url("org_3"), headers=partner_admin()).status_code == 200


def test_our_token_for_another_tenant_cannot_reach_org3(client):
    ours = bearer(mint_token(tid="org_1"))

    assert_error(client.put(policy_url("org_3"), json=POLICY, headers=ours), 403, "forbidden")
    assert_error(check(client, bearer(mint_token(tid="org_1", scp=["quota.check"])), "org_3"), 403, "forbidden")


def test_tenant_ids_are_matched_exactly(client):
    """'ORG_3' is simply a different tenant, not an alias of org_3."""
    ours = bearer(mint_token(tid="ORG_3"))

    assert client.put(policy_url("ORG_3"), json=POLICY, headers=ours).status_code == 201
    assert_error(client.get(policy_url("org_3"), headers=ours), 403, "forbidden")


# --- which key checks which token: no cross-signing -------------------------


def test_partner_issuer_signed_with_our_secret_is_rejected(client):
    forged = partner_token(secret=SECRET)

    assert_error(client.get(policy_url("org_3"), headers=bearer(forged)), 401, "invalid_token")


def test_our_issuer_signed_with_the_partner_secret_is_rejected(client):
    forged = mint_token(secret=PARTNER_SECRET, tid="org_1")

    assert_error(client.get(policy_url("org_1"), headers=bearer(forged)), 401, "invalid_token")


def test_org3_token_signed_with_our_secret_cannot_claim_the_partner_issuer(client):
    forged = mint_token(secret=SECRET, iss=PARTNER_ISSUER, tid="org_3")

    assert_error(client.put(policy_url("org_3"), json=POLICY, headers=bearer(forged)), 401, "invalid_token")


def raw_token(payload, secret=PARTNER_SECRET):
    """Sign an arbitrary payload, bypassing PyJWT's claim checks on encode (as an attacker would)."""
    import json
    from jwt.api_jws import encode

    return encode(json.dumps(payload).encode(), secret, algorithm="HS256")


@pytest.mark.parametrize(
    "iss",
    ["https://evil.example", PARTNER_ISSUER + "/", "https://PARTNER.example", "", 123, ["https://partner.example"], {"a": 1}, None],
)
def test_unknown_or_malformed_issuer_is_401_never_500(client, iss):
    import time
    payload = {"iss": iss, "aud": "api://quota-gate", "exp": int(time.time()) + 300,
               "sub": "x", "tid": "org_3", "scp": ["quota.admin"]}

    res = client.get(policy_url("org_3"), headers=bearer(raw_token(payload)))

    assert_error(res, 401, "invalid_token")


def test_token_that_is_not_a_jwt_payload_object_is_401(client):
    from jwt.api_jws import encode

    token = encode(b'["not", "an", "object"]', PARTNER_SECRET, algorithm="HS256")

    assert_error(client.get(policy_url("org_3"), headers=bearer(token)), 401, "invalid_token")


# --- everything else about partner tokens is validated the same way ---------


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "spa"},
        {"exp": 1},
        {"sub": ""},
        {"tid": ""},
        {"scp": "quota.admin"},
        {"tid": None},
        {"sub": None},
        {"scp": None},
        {"aud": None},
    ],
)
def test_partner_tokens_get_the_same_claim_validation(client, overrides):
    token = partner_token(**{"scp": ["quota.admin"], **overrides})

    assert_error(client.get(policy_url("org_3"), headers=bearer(token)), 401, "invalid_token")


def test_partner_audience_list_containing_ours_is_accepted(client):
    token = partner_token(scp=["quota.admin"], aud=["other", "api://quota-gate"])

    assert client.put(policy_url("org_3"), json=POLICY, headers=bearer(token)).status_code == 201


def test_partner_tokens_cannot_use_alg_none(client):
    import jwt, time
    claims = {"iss": PARTNER_ISSUER, "aud": "api://quota-gate", "exp": int(time.time()) + 300,
              "sub": "x", "tid": "org_3", "scp": ["quota.admin"]}
    token = jwt.encode(claims, key=None, algorithm="none")

    assert_error(client.get(policy_url("org_3"), headers=bearer(token)), 401, "invalid_token")


def test_tenant_headers_are_still_ignored_for_partner_tokens(client):
    headers = {**partner_admin(), "X-Tenant-Id": "org_3", "X-User": "root"}

    assert_error(client.put(policy_url("org_1"), json=POLICY, headers=headers), 403, "forbidden")


def test_authn_errors_still_win_over_authz_errors(client):
    assert_error(client.put(policy_url("org_3"), json={"bad": 1}), 401, "invalid_token")
    ours = bearer(mint_token(tid="org_3"))
    # valid token, forbidden tenant: 403 even though the body is invalid
    assert_error(client.put(policy_url("org_3"), json={"bad": 1}, headers=ours), 403, "forbidden")


# --- quota for org_3 is its own -------------------------------------------


def test_partner_quota_is_independent_of_other_tenants(client):
    client.put(policy_url("org_3"), json={**POLICY, "burst": 1}, headers=partner_admin())
    client.put(policy_url("org_1"), json={**POLICY, "burst": 1}, headers=bearer(mint_token()))
    org1_svc = bearer(mint_token(sub="svc", scp=["quota.check"]))

    assert check(client, partner_check(), "org_3").status_code == 200
    assert check(client, partner_check(), "org_3").status_code == 429
    assert check(client, org1_svc, "org_1").status_code == 200  # org_1 untouched


# --- configuration -----------------------------------------------------------


def test_without_a_partner_secret_partner_tokens_are_rejected(tmp_path, clock):
    """No default secret for the partner: a guessable default would let anyone forge org_3."""
    app = create_app(str(tmp_path / "x.db"), SECRET, ISSUER, clock=clock)  # no partner_secret
    client = app.test_client()

    assert_error(client.get(policy_url("org_3"), headers=partner_admin()), 401, "invalid_token")
    # our own issuer is unaffected
    assert client.get(policy_url("org_1"), headers=bearer(mint_token())).status_code == 404


def test_partner_issuer_is_configurable(tmp_path, clock):
    app = create_app(
        str(tmp_path / "y.db"), SECRET, ISSUER, clock=clock,
        partner_secret=PARTNER_SECRET, partner_issuer="https://other-partner.example",
    )
    client = app.test_client()

    assert client.put(policy_url("org_3"), json=POLICY,
                      headers=bearer(partner_token(iss="https://other-partner.example", scp=["quota.admin"]))
                      ).status_code == 201
    assert_error(client.get(policy_url("org_3"), headers=partner_admin()), 401, "invalid_token")


def test_healthz_is_still_open(client):
    assert client.get("/healthz").status_code == 200


@pytest.mark.parametrize("unset", [None, ""])
def test_unconfigured_partner_cannot_be_impersonated_with_a_guessable_secret(tmp_path, clock, unset):
    app = create_app(str(tmp_path / "z.db"), SECRET, ISSUER, clock=clock, partner_secret=unset)
    client = app.test_client()
    # an attacker tries the obvious defaults against the partner issuer / org_3
    for guess in ["dev-secret-change-me", "partner-secret", "", SECRET]:
        forged = mint_token(secret=guess or "x", iss=PARTNER_ISSUER, tid="org_3")
        assert_error(client.get(policy_url("org_3"), headers=bearer(forged)), 401, "invalid_token")


def test_our_issuer_is_barred_from_org3_even_when_the_partner_is_not_configured(tmp_path, clock):
    app = create_app(str(tmp_path / "w.db"), SECRET, ISSUER, clock=clock)  # no partner
    client = app.test_client()

    res = client.put(policy_url("org_3"), json=POLICY, headers=bearer(mint_token(tid="org_3")))

    assert_error(res, 403, "forbidden")


def test_partner_issuer_must_differ_from_ours(tmp_path, clock):
    with pytest.raises(ValueError):
        create_app(str(tmp_path / "v.db"), SECRET, ISSUER, clock=clock,
                   partner_secret=PARTNER_SECRET, partner_issuer=ISSUER)
