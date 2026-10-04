import sqlite3

import app.db as db
from tests.conftest import auth


def _row(key_id):
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM keys WHERE key_id = ?", (key_id,)).fetchone()
    conn.close()
    return r


def test_create_returns_secret_and_stores_only_hash(client):
    r = client.post("/tenants/t1/keys", json={"name": "billing-worker"})
    assert r.status_code == 200
    body = r.json()
    assert body["prefix"].startswith("gk_live_")
    assert body["secret"].startswith(body["prefix"] + ".")
    row = _row(body["key_id"])
    assert body["secret"].split(".", 1)[1] not in row["secret_hash"]
    assert row["revoked"] == 0


def test_create_unknown_tenant_404(client):
    assert client.post("/tenants/nope/keys", json={"name": "x"}, headers=auth(tid="nope")).status_code == 404


def test_revoke(client):
    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    r = client.post(f"/tenants/t1/keys/{kid}/revoke")
    assert r.status_code == 204 and r.content == b""
    assert _row(kid)["revoked"] == 1
    # already revoked stays 204
    assert client.post(f"/tenants/t1/keys/{kid}/revoke").status_code == 204


def test_rotate_keeps_key_id_and_changes_secret(client):
    created = client.post("/tenants/t1/keys", json={"name": "x"}).json()
    old_hash = _row(created["key_id"])["secret_hash"]
    r = client.post(f"/tenants/t1/keys/{created['key_id']}/rotate")
    assert r.status_code == 200
    assert r.json()["key_id"] == created["key_id"]
    assert r.json()["secret"] != created["secret"]
    assert _row(created["key_id"])["secret_hash"] != old_hash


def test_cross_tenant_key_is_404(client):
    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    t2 = auth(tid="t2")
    assert client.post(f"/tenants/t2/keys/{kid}/revoke", headers=t2).status_code == 404
    assert client.post(f"/tenants/t2/keys/{kid}/rotate", headers=t2).status_code == 404


def test_rotate_revoked_is_409_and_stays_revoked(client):
    created = client.post("/tenants/t1/keys", json={"name": "x"}).json()
    kid = created["key_id"]
    client.post(f"/tenants/t1/keys/{kid}/revoke")
    old_hash = _row(kid)["secret_hash"]
    assert client.post(f"/tenants/t1/keys/{kid}/rotate").status_code == 409
    row = _row(kid)
    assert row["revoked"] == 1 and row["secret_hash"] == old_hash
    assert client.post("/keys/introspect", json={"secret": created["secret"]}).json() == {"active": False}


def test_create_records_creator_and_timestamp(client):
    from datetime import datetime

    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    row = _row(kid)
    assert row["created_by"] == "u-admin-t1"
    assert datetime.fromisoformat(row["created_at"]).tzinfo is not None
    # rotate and revoke leave the creation record alone
    client.post(f"/tenants/t1/keys/{kid}/rotate")
    assert (_row(kid)["created_by"], _row(kid)["created_at"]) == (row["created_by"], row["created_at"])
