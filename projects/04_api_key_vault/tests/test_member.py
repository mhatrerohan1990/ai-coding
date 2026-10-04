from tests.conftest import auth


def _create(client, tenant="t1", name="x"):
    return client.post(f"/tenants/{tenant}/keys", json={"name": name}, headers=auth(tid=tenant)).json()


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
    for bad in ["", "nodot", k["prefix"] + ".wrong", k["prefix"] + "."]:
        r = client.post("/keys/introspect", json={"secret": bad})
        assert r.status_code == 200 and r.json() == {"active": False}


def test_list_keys_scoped_to_tenant(client):
    a = _create(client, "t1", "a")
    _create(client, "t2", "b")
    r = client.get("/tenants/t1/keys")
    assert r.json() == [{"key_id": a["key_id"], "name": "a", "prefix": a["prefix"], "status": "ACTIVE"}]
    assert client.get("/tenants/nope/keys", headers=auth(tid="nope")).status_code == 404


def test_introspect_unknown_prefix_is_404_with_no_body(client):
    r = client.post("/keys/introspect", json={"secret": "gk_live_zzzz.abc"})
    assert r.status_code == 404 and r.content == b""


def test_lookups_use_indexes(client):
    import sqlite3

    import app.db as db

    conn = sqlite3.connect(db.DB_PATH)

    def plan(sql):
        return " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql))

    assert "USING INDEX idx_keys_tenant_id" in plan("SELECT * FROM keys WHERE tenant_id = 't1'")
    assert "USING INDEX sqlite_autoindex_keys" in plan("SELECT * FROM keys WHERE prefix = 'gk_live_aaaa'")
    assert "SCAN" not in plan("SELECT * FROM keys WHERE tenant_id = 't1'")
