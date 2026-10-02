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
    """Point the module at a database file and (re)open the connection.

    Resets the cached module-level connection, so each call (e.g. one per test
    via ``create_app``) starts from a fresh connection to ``path``.

    Args:
        path: Filesystem path of the SQLite database file.

    Returns:
        The new ``sqlite3.Connection``.
    """
    global _conn, _path
    _path = path
    _conn = None
    return get_conn()


def get_conn():
    """Return the shared SQLite connection, creating it on first use.

    On creation it opens ``_path`` with ``check_same_thread=False`` (Flask
    handles requests on several threads), sets ``sqlite3.Row`` as the row
    factory so rows can be read by column name, and runs ``SCHEMA`` to create
    any missing tables. One connection is shared process-wide.

    Returns:
        The shared ``sqlite3.Connection``.
    """
    global _conn
    if _conn is None:
        # Flask serves requests from multiple threads, so allow sharing.
        _conn = sqlite3.connect(_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn
