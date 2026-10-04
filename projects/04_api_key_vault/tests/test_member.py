from tests.test_admin import client  # noqa: F401


def _create(client, tenant="t1", name="x"):
    return client.post(f"/tenants/{tenant}/keys", json={"name": name}).json()


def test_introspect_active(client):
    k = _create(client, name="billing-worker")
    r = client.post("/keys/introspect", json={"secret": k["secret"]})
    assert r.status_code == 200
    assert r.json() == {"active": True, "tenant_id": "t1", "key_id": k["key_id"], "name": "billing-worker"}


def test_introspect_revoked(client):
    k = _create(client)
    client.post(f"/tenants/t1/keys/{k['key_id']}/revoke")
    assert client.post("/keys/introspect", json={"secret": k["secret"]}).json() == {"active": False}


def test_introspect_rotated_old_secret_inactive_new_active(client):
    k = _create(client)
    new = client.post(f"/tenants/t1/keys/{k['key_id']}/rotate").json()
    assert client.post("/keys/introspect", json={"secret": k["secret"]}).json() == {"active": False}
    assert client.post("/keys/introspect", json={"secret": new["secret"]}).json()["active"] is True


def test_introspect_garbage_and_wrong_secret(client):
    k = _create(client)
    for bad in ["", "nodot", "gk_live_zzzz.abc", k["prefix"] + ".wrong", k["prefix"] + "."]:
        r = client.post("/keys/introspect", json={"secret": bad})
        assert r.status_code == 200 and r.json() == {"active": False}


def test_list_keys_scoped_to_tenant(client):
    a = _create(client, "t1", "a")
    _create(client, "t2", "b")
    r = client.get("/tenants/t1/keys")
    assert r.json() == [{"key_id": a["key_id"], "name": "a", "prefix": a["prefix"], "revoked": False}]
    assert client.get("/tenants/nope/keys").status_code == 404
