"""Database schema: foreign keys and versioning."""

import sqlite3

import pytest

from splitr.app import create_app


def test_foreign_keys_are_enforced(client, group_id):
    from splitr.db import get_conn

    with pytest.raises(sqlite3.IntegrityError):
        get_conn().execute(
            "INSERT INTO expenses (group_id, paid_by, amount, description, created_at) "
            "VALUES (?, 'not-a-member', 1, '', 'now')",
            (group_id,),
        )


def test_old_schema_database_is_refused(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT);")
    conn.close()
    with pytest.raises(RuntimeError, match="old schema"):
        create_app(str(path))


def test_a_version_2_database_is_upgraded_in_place(tmp_path):
    from splitr import db

    path = tmp_path / "v2.db"
    create_app(str(path))
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE idempotency_keys; PRAGMA user_version = 2;")
    conn.close()
    db._schema_ready.discard(str(path))

    create_app(str(path))  # opens the "old" file
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert "idempotency_keys" in tables
    assert version == db.SCHEMA_VERSION
