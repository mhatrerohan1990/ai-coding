import time

import jwt
import pytest

from conftest import ISSUER, SECRET, bearer, mint_token

POLICY = {
    "match": {"subject": "*", "action": "api.read"},
    "limit": 10,
    "window_seconds": 60,
    "burst": 5,
}
ORG1 = "/v1/tenants/org_1/policies/p"
ORG2 = "/v1/tenants/org_2/policies/p"


def assert_error(res, status, code):
    assert res.status_code == status
    assert res.get_json()["error"]["code"] == code


# --- 401: the token itself is not acceptable -------------------------------


def test_missing_authorization_header_is_401(client):
    assert_error(client.get(ORG1), 401, "invalid_token")


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic abc", "abc", "Bearer a b"])
def test_malformed_authorization_header_is_401(client, header):
    res = client.get(ORG1, headers={"Authorization": header})
    assert_error(res, 401, "invalid_token")


def test_garbage_token_is_401(client):
    assert_error(client.get(ORG1, headers=bearer("not.a.jwt")), 401, "invalid_token")


def test_token_signed_with_other_secret_is_401(client):
    token = mint_token(secret="some-other-secret-some-other-secret-32b")
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


def test_alg_none_token_is_401(client):
    claims = {
        "iss": ISSUER, "aud": "api://quota-gate", "exp": int(time.time()) + 300,
        "sub": "x", "tid": "org_1", "scp": ["quota.admin"],
    }
    token = jwt.encode(claims, key=None, algorithm="none")
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


def test_expired_token_is_401(client):
    token = mint_token(exp=int(time.time()) - 10)
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


def test_wrong_issuer_is_401(client):
    token = mint_token(iss="https://evil.example.test")
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


def test_id_token_shaped_jwt_with_spa_audience_is_401(client):
    token = mint_token(aud="spa")
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


def test_audience_list_containing_ours_is_accepted(client):
    token = mint_token(aud=["other", "api://quota-gate"])
    res = client.put(ORG1, json=POLICY, headers=bearer(token))
    assert res.status_code == 201


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "sub", "tid", "scp"])
def test_missing_required_claim_is_401(client, claim):
    token = mint_token(**{claim: None})
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


@pytest.mark.parametrize(
    "overrides",
    [{"sub": ""}, {"tid": ""}, {"tid": 7}, {"scp": "quota.admin"}, {"scp": [1]}],
)
def test_malformed_claim_value_is_401(client, overrides):
    token = mint_token(**overrides)
    assert_error(client.get(ORG1, headers=bearer(token)), 401, "invalid_token")


# --- 403: valid token, not allowed ------------------------------------------


def test_check_scope_cannot_use_admin_endpoints(client):
    token = mint_token(scp=["quota.check"])
    assert_error(client.put(ORG1, json=POLICY, headers=bearer(token)), 403, "forbidden")


def test_token_for_org1_cannot_write_org2_policies(client, admin):
    res = client.put(ORG2, json=POLICY, headers=admin)

    assert_error(res, 403, "forbidden")
    # and nothing was written: org_2's own admin sees no policy
    org2_admin = bearer(mint_token(tid="org_2"))
    assert_error(client.get(ORG2, headers=org2_admin), 404, "not_found")


def test_token_for_org1_cannot_read_or_delete_org2_policies(client):
    org2_admin = bearer(mint_token(tid="org_2"))
    client.put(ORG2, json=POLICY, headers=org2_admin)
    org1_admin = bearer(mint_token(tid="org_1"))

    assert_error(client.get(ORG2, headers=org1_admin), 403, "forbidden")
    assert_error(client.delete(ORG2, headers=org1_admin), 403, "forbidden")
    assert client.get(ORG2, headers=org2_admin).status_code == 200


def test_tenant_headers_are_ignored_identity_comes_from_jwt(client, admin):
    headers = {**admin, "X-Tenant-Id": "org_2", "X-User": "root"}

    assert_error(client.put(ORG2, json=POLICY, headers=headers), 403, "forbidden")
    assert client.put(ORG1, json=POLICY, headers=headers).status_code == 201


def test_unauthenticated_request_gets_401_not_403_even_for_other_tenant(client):
    assert_error(client.put(ORG2, json=POLICY), 401, "invalid_token")


def test_healthz_needs_no_token(client):
    assert client.get("/healthz").status_code == 200
