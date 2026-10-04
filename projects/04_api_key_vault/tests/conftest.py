import sqlite3
import time

import jwt
import pytest
from fastapi.testclient import TestClient

import app.db as db
from app.main import app

SECRET = "test-secret-at-least-32-bytes-long-0123456789"
ALL_SCOPES = "create revoke rotate introspect list"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


def token(tid="t1", role="admin", uid=None, scope=ALL_SCOPES, aud="api://keys", exp=None, secret=SECRET, drop=(), alg="HS256"):
    claims = {"sub": "u1", "tid": tid, "uid": uid or f"u-{role}-{tid}", "role": role, "scope": scope, "aud": aud,
              "exp": exp if exp is not None else int(time.time()) + 300}
    for k in drop:
        claims.pop(k)
    return jwt.encode(claims, secret, algorithm=alg)


def auth(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    conn = sqlite3.connect(db.DB_PATH)
    db.init_db(conn)
    conn.execute("INSERT INTO tenants VALUES ('t1', 'Tenant 1'), ('t2', 'Tenant 2')")
    for tid in ("t1", "t2", "nope"):  # "nope": a user whose tenant has no tenants row
        for role in ("admin", "member"):
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (f"u-{role}-{tid}", tid, f"{role} {tid}", role))
    conn.commit()
    conn.close()
    # default caller: admin of t1 with every scope
    return TestClient(app, headers=auth())
