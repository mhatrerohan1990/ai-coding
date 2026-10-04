import os
import sqlite3

DB_PATH = os.environ.get("VAULT_DB", "vault.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    uid       TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    name      TEXT NOT NULL,
    role      TEXT NOT NULL CHECK (role IN ('admin', 'member'))
);
CREATE TABLE IF NOT EXISTS keys (
    key_id      TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    prefix      TEXT NOT NULL UNIQUE,
    secret_hash TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ROTATING', 'REVOKED')),
    created_by  TEXT NOT NULL REFERENCES users(uid),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_keys_tenant_name ON keys(tenant_id, name, key_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # per-connection in SQLite
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()
