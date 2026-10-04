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
    assert row["status"] == "ACTIVE"


def test_create_unknown_tenant_404(client):
    assert client.post("/tenants/nope/keys", json={"name": "x"}, headers=auth(tid="nope")).status_code == 404


def test_revoke(client):
    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    r = client.post(f"/tenants/t1/keys/{kid}/revoke")
    assert r.status_code == 204 and r.content == b""
    assert _row(kid)["status"] == "REVOKED"
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
    assert row["status"] == "REVOKED" and row["secret_hash"] == old_hash
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


def test_revoke_landing_during_rotate_wins(client, monkeypatch):
    """A revoke that lands after rotate's lookup but before its write must not be undone."""
    from app.services.admin_service import AdminService

    created = client.post("/tenants/t1/keys", json={"name": "x"}).json()
    kid = created["key_id"]
    old_hash = _row(kid)["secret_hash"]

    real = AdminService._require_key

    def lookup_then_revoke(self, tenant_id, key_id):
        row = real(self, tenant_id, key_id)
        self.db.execute("UPDATE keys SET status = 'REVOKED' WHERE key_id = ?", (key_id,))
        self.db.commit()
        return row

    monkeypatch.setattr(AdminService, "_require_key", lookup_then_revoke)
    assert client.post(f"/tenants/t1/keys/{kid}/rotate").status_code == 409
    row = _row(kid)
    assert row["status"] == "REVOKED" and row["secret_hash"] == old_hash


def test_concurrent_rotates_leave_exactly_one_valid_secret(client):
    import threading

    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    barrier, results = threading.Barrier(6), []

    def rotate():
        barrier.wait()
        r = client.post(f"/tenants/t1/keys/{kid}/rotate")
        results.append((r.status_code, r.json().get("secret")))

    threads = [threading.Thread(target=rotate) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert {code for code, _ in results} <= {200, 409}
    assert any(code == 200 for code, _ in results)
    live = [s for code, s in results if code == 200 and client.post("/keys/introspect", json={"secret": s}).json()["active"]]
    assert len(live) == 1


def _set_status(kid, status):
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("UPDATE keys SET status = ? WHERE key_id = ?", (status, kid))
    conn.commit()
    conn.close()


def test_rotate_while_rotating_is_409_and_changes_nothing(client):
    created = client.post("/tenants/t1/keys", json={"name": "x"}).json()
    kid = created["key_id"]
    _set_status(kid, "ROTATING")
    old_hash = _row(kid)["secret_hash"]
    assert client.post(f"/tenants/t1/keys/{kid}/rotate").status_code == 409
    row = _row(kid)
    assert row["status"] == "ROTATING" and row["secret_hash"] == old_hash


def test_introspect_is_inactive_while_rotating(client):
    created = client.post("/tenants/t1/keys", json={"name": "x"}).json()
    _set_status(created["key_id"], "ROTATING")
    assert client.post("/keys/introspect", json={"secret": created["secret"]}).json() == {"active": False}


def test_revoke_during_rotation_wins_and_no_secret_is_returned(client, monkeypatch):
    import app.services.admin_service as svc

    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    real_hash = svc._hash

    def revoke_then_hash(secret):  # runs after the ROTATING claim, before the final write
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("UPDATE keys SET status = 'REVOKED' WHERE key_id = ?", (kid,))
        conn.commit()
        conn.close()
        return real_hash(secret)

    monkeypatch.setattr(svc, "_hash", revoke_then_hash)
    r = client.post(f"/tenants/t1/keys/{kid}/rotate")
    assert r.status_code == 409 and "secret" not in r.json()
    assert _row(kid)["status"] == "REVOKED"


def test_revoke_while_rotating_is_allowed(client):
    kid = client.post("/tenants/t1/keys", json={"name": "x"}).json()["key_id"]
    _set_status(kid, "ROTATING")
    assert client.post(f"/tenants/t1/keys/{kid}/revoke").status_code == 204
    assert _row(kid)["status"] == "REVOKED"
