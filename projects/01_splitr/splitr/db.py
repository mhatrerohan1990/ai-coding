import sqlite3

_conn = None
_path = "splitr.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    group_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    paid_by TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shares (
    expense_id INTEGER NOT NULL,
    member TEXT NOT NULL,
    amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    from_member TEXT NOT NULL,
    to_member TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init(path):
    global _conn, _path
    _path = path
    _conn = None
    return get_conn()


def get_conn():
    global _conn
    if _conn is None:
        # Flask serves requests from multiple threads, so allow sharing.
        _conn = sqlite3.connect(_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn
