"""Database schema: foreign keys and versioning."""

import sqlite3

import pytest

from splitr.app import create_app


def test_foreign_keys_are_enforced(client, group_id):
    from splitr.db import get_conn

    with pytest.raises(sqlite3.IntegrityError):
        get_conn().execute(
            "INSERT INTO expenses (group_id, paid_by, amount_cents, description, created_at) "
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


# Tables exactly as schema versions 2 and 3 created them: money in float REAL columns.
OLD_TABLES = """
CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT);
CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
CREATE TABLE group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    PRIMARY KEY (group_id, user_id));
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id),
    paid_by TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id, paid_by) REFERENCES group_members(group_id, user_id));
CREATE TABLE shares (
    expense_id INTEGER NOT NULL REFERENCES expenses(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    amount REAL NOT NULL,
    PRIMARY KEY (expense_id, user_id));
CREATE TABLE settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id),
    from_user_id TEXT NOT NULL,
    to_user_id TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id, from_user_id) REFERENCES group_members(group_id, user_id),
    FOREIGN KEY (group_id, to_user_id) REFERENCES group_members(group_id, user_id));
CREATE INDEX idx_expenses_group ON expenses(group_id);
CREATE INDEX idx_settlements_group ON settlements(group_id);
CREATE INDEX idx_group_members_user ON group_members(user_id);
"""
V3_TABLE = """
CREATE TABLE idempotency_keys (
    key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status INTEGER, body TEXT,
    created_at TEXT NOT NULL);
"""


def make_old_database(path, version, *, bad_row=False):
    """A database as an older release left it, holding float amounts."""
    conn = sqlite3.connect(path)
    conn.executescript(OLD_TABLES + (V3_TABLE if version == 3 else ""))
    conn.executemany(
        "INSERT INTO users VALUES (?, ?, ?)",
        [("alice", "alice", "a@x.com"), ("bob", "bob", "b@x.com"), ("carol", "carol", None)],
    )
    conn.execute("INSERT INTO groups (id, name) VALUES (1, 'trip')")
    conn.executemany("INSERT INTO group_members VALUES (1, ?)", [("alice",), ("bob",), ("carol",)])
    expenses = [
        (1, "alice", 100.0, "dinner"),
        (2, "bob", 19.99, "taxi"),
        (3, "alice", 0.1 + 0.2, "float noise"),  # 0.30000000000000004
    ]
    if bad_row:
        expenses.append((4, "alice", 0.0, "invalid under the new rules"))
    for expense_id, payer, amount, description in expenses:
        conn.execute(
            "INSERT INTO expenses VALUES (?, 1, ?, ?, ?, '2026-01-01T00:00:00')",
            (expense_id, payer, amount, description),
        )
    conn.executemany(
        "INSERT INTO shares VALUES (?, ?, ?)",
        [(1, "alice", 33.34), (1, "bob", 33.33), (1, "carol", 33.33),
         (2, "alice", 6.67), (2, "bob", 6.66), (2, "carol", 6.66),
         (3, "alice", 0.1), (3, "bob", 0.1), (3, "carol", 0.1)],
    )
    conn.execute("INSERT INTO settlements VALUES (1, 1, 'bob', 'alice', 5.5, '2026-01-02T00:00:00')")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("version", [2, 3])
def test_an_older_database_is_upgraded_to_integer_cents(tmp_path, version):
    from splitr import db

    path = tmp_path / "old.db"
    make_old_database(path, version)
    client = create_app(str(path)).test_client()  # opening it runs the migration

    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert [tuple(r) for r in conn.execute("SELECT id, amount_cents FROM expenses ORDER BY id")] == [
        (1, 10000), (2, 1999), (3, 30)
    ]
    assert [tuple(r) for r in conn.execute("SELECT expense_id, user_id, amount_cents FROM shares ORDER BY 1, 2")][:3] == [
        (1, "alice", 3334), (1, "bob", 3333), (1, "carol", 3333)
    ]
    assert conn.execute("SELECT amount_cents FROM settlements").fetchone()[0] == 550
    assert conn.execute("SELECT COUNT(*) FROM expenses WHERE typeof(amount_cents) != 'integer'").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []  # nothing orphaned
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert {"idempotency_keys", "expenses_new", "shares_new", "settlements_new"} & tables == {"idempotency_keys"}
    assert {"idx_expenses_group", "idx_settlements_group", "idx_group_members_user"} <= indexes

    # the data means the same thing through the API: 54.69 / -14.60 / -40.09
    balances = client.get("/groups/1/balances").get_json()["balances"]
    assert {b["name"]: b["balance"] for b in balances.values()} == {
        "alice": 54.69, "bob": -14.6, "carol": -40.09
    }
    assert client.get("/groups/1/settle-up").status_code == 200

    # and new writes carry on from the old ids
    new = client.post("/groups/1/expenses", json={"paid_by": "alice", "amount": 12.34})
    assert new.status_code == 201 and new.get_json()["id"] == 4


def test_a_failed_upgrade_leaves_the_old_database_untouched(tmp_path):
    path = tmp_path / "old.db"
    make_old_database(path, 3, bad_row=True)  # a 0.0 expense violates the new CHECK

    with pytest.raises(sqlite3.IntegrityError):
        create_app(str(path))

    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    columns = [r[1] for r in conn.execute("PRAGMA table_info(expenses)")]
    assert "amount" in columns and "amount_cents" not in columns
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%_new'").fetchone()[0] == 0
    conn.close()


def test_opening_an_up_to_date_database_changes_nothing(tmp_path):
    path = tmp_path / "current.db"
    make_old_database(path, 3)
    create_app(str(path))

    from splitr import db

    db._schema_ready.discard(str(path))
    create_app(str(path))  # second open: no migration, no error
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT amount_cents FROM expenses WHERE id = 1").fetchone()[0] == 10000
    conn.close()
