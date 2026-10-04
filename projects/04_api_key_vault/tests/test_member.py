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
    assert r.json() == {
        "items": [{"key_id": a["key_id"], "name": "a", "prefix": a["prefix"], "status": "ACTIVE"}],
        "next_cursor": None,
    }
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

    assert "USING INDEX idx_keys_tenant_name" in plan("SELECT * FROM keys WHERE tenant_id = 't1'")
    assert "USING INDEX sqlite_autoindex_keys" in plan("SELECT * FROM keys WHERE prefix = 'gk_live_aaaa'")
    assert "SCAN" not in plan("SELECT * FROM keys WHERE tenant_id = 't1'")


def _make(client, n, prefix="k"):
    return [_create(client, name=f"{prefix}{i:03d}")["key_id"] for i in range(n)]


def test_list_default_limit_is_20_and_cursor_walks_all_pages(client):
    ids = _make(client, 45)
    r = client.get("/tenants/t1/keys").json()
    assert len(r["items"]) == 20 and r["next_cursor"]
    seen = [i["key_id"] for i in r["items"]]
    while r["next_cursor"]:
        r = client.get("/tenants/t1/keys", params={"cursor": r["next_cursor"]}).json()
        seen += [i["key_id"] for i in r["items"]]
    assert seen == ids  # ordered by name, no gaps, no repeats
    assert r["next_cursor"] is None


def test_list_exact_page_boundary_has_no_next_cursor(client):
    _make(client, 4)
    r = client.get("/tenants/t1/keys", params={"limit": 4}).json()
    assert len(r["items"]) == 4 and r["next_cursor"] is None
    r = client.get("/tenants/t1/keys", params={"limit": 3}).json()
    assert len(r["items"]) == 3 and r["next_cursor"]


def test_list_items_added_between_pages_are_not_skipped_or_repeated(client):
    ids = _make(client, 3)  # k000 k001 k002
    first = client.get("/tenants/t1/keys", params={"limit": 2}).json()  # k000 k001
    after = _make(client, 1, prefix="z")  # sorts after the cursor, so it must appear
    before = _make(client, 1, prefix="a")  # sorts before the cursor, so it is (correctly) not revisited
    rest = client.get("/tenants/t1/keys", params={"limit": 5, "cursor": first["next_cursor"]}).json()
    got = [i["key_id"] for i in first["items"] + rest["items"]]
    assert got == ids + after and before[0] not in got


def test_list_cursor_never_crosses_tenants(client):
    _make(client, 3)
    _create(client, "t2", "other")
    page = client.get("/tenants/t1/keys", params={"limit": 2}).json()
    t2 = client.get("/tenants/t2/keys", params={"cursor": page["next_cursor"]}, headers=auth(tid="t2")).json()
    assert [i["name"] for i in t2["items"]] == ["other"]


import pytest  # noqa: E402


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": -1}, {"limit": 51}, {"limit": "abc"}, {"limit": ""},
    {"cursor": "not-base64!!"}, {"cursor": "e30="}, {"cursor": ""},
])
def test_list_bad_limit_or_cursor_is_400(client, params):
    assert client.get("/tenants/t1/keys", params=params).status_code == 400


def test_list_limit_bounds_are_accepted(client):
    _make(client, 2)
    assert client.get("/tenants/t1/keys", params={"limit": 1}).status_code == 200
    assert client.get("/tenants/t1/keys", params={"limit": 50}).status_code == 200


def test_list_is_ordered_by_name_then_key_id(client):
    for n in ["bravo", "alpha", "charlie", "alpha"]:
        _create(client, name=n)
    items = client.get("/tenants/t1/keys").json()["items"]
    assert [i["name"] for i in items] == ["alpha", "alpha", "bravo", "charlie"]
    assert items[0]["key_id"] < items[1]["key_id"]
    page = client.get("/tenants/t1/keys", params={"limit": 1}).json()
    nxt = client.get("/tenants/t1/keys", params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert nxt["items"][0]["key_id"] == items[1]["key_id"]  # tie on name breaks on key_id
