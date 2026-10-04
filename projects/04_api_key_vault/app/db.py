import os
import sqlite3

DB_PATH = os.environ.get("VAULT_DB", "vault.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keys (
    key_id      TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    prefix      TEXT NOT NULL UNIQUE,
    secret_hash TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()
