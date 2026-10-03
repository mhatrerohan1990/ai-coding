from conftest import bearer, mint_token

POLICY = {
    "match": {"subject": "*", "action": "users.export"},
    "limit": 100,
    "window_seconds": 60,
    "burst": 20,
}

URL = "/v1/tenants/org_1/policies/export-cap"


def test_put_creates_policy_and_returns_stored_policy(client, admin):
    res = client.put(URL, json=POLICY, headers=admin)

    assert res.status_code == 201
    assert res.get_json() == {
        "policy_id": "export-cap",
        "tenant_id": "org_1",
        **POLICY,
    }


def test_put_existing_policy_replaces_it_and_returns_200(client, admin):
    client.put(URL, json=POLICY, headers=admin)
    replacement = {**POLICY, "limit": 5, "burst": 2}

    res = client.put(URL, json=replacement, headers=admin)

    assert res.status_code == 200
    assert res.get_json() == {
        "policy_id": "export-cap",
        "tenant_id": "org_1",
        **replacement,
    }


def test_get_returns_the_stored_policy(client, admin):
    client.put(URL, json=POLICY, headers=admin)

    res = client.get(URL, headers=admin)

    assert res.status_code == 200
    assert res.get_json() == {
        "policy_id": "export-cap",
        "tenant_id": "org_1",
        **POLICY,
    }


def test_get_after_replace_returns_the_new_values(client, admin):
    client.put(URL, json=POLICY, headers=admin)
    client.put(URL, json={**POLICY, "limit": 5}, headers=admin)

    assert client.get(URL, headers=admin).get_json()["limit"] == 5


def test_delete_removes_policy_and_returns_204(client, admin):
    client.put(URL, json=POLICY, headers=admin)

    res = client.delete(URL, headers=admin)

    assert res.status_code == 204
    assert res.data == b""


def test_policies_are_keyed_by_tenant_and_policy_id(client, admin):
    org2 = bearer(mint_token(tid="org_2"))
    client.put("/v1/tenants/org_1/policies/p", json={**POLICY, "limit": 1}, headers=admin)
    client.put("/v1/tenants/org_2/policies/p", json={**POLICY, "limit": 2}, headers=org2)
    client.put("/v1/tenants/org_1/policies/q", json={**POLICY, "limit": 3}, headers=admin)

    assert client.get("/v1/tenants/org_1/policies/p", headers=admin).get_json()["limit"] == 1
    assert client.get("/v1/tenants/org_2/policies/p", headers=org2).get_json()["limit"] == 2
    assert client.get("/v1/tenants/org_1/policies/q", headers=admin).get_json()["limit"] == 3
