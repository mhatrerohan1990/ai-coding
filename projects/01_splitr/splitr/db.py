import sqlite3
import threading

_path = "splitr.db"
_local = threading.local()  # one connection (and transaction state) per thread
_schema_lock = threading.Lock()
_schema_ready = set()  # database paths whose schema has been created
BUSY_TIMEOUT_SECONDS = 10

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


def _ensure_schema(path):
    """Create the tables (and switch to WAL) once per database path."""
    with _schema_lock:
        if path in _schema_ready:
            return
        conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            # WAL lets readers run alongside the single writer.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()
        _schema_ready.add(path)


def init(path):
    """Point the module at a database file and (re)open this thread's connection.

    Creates the schema if needed and drops this thread's cached connection, so
    each call (e.g. one per test via ``create_app``) starts from a fresh
    connection to ``path``.

    Args:
        path: Filesystem path of the SQLite database file.

    Returns:
        This thread's ``sqlite3.Connection``.
    """
    global _path
    _path = path
    close_conn()
    return get_conn()


def get_conn():
    """Return the calling thread's SQLite connection, creating it on first use.

    Every thread gets its own connection, because a connection owns the open
    transaction: sharing one across Flask's request threads would let one
    request commit or roll back another's half-finished writes. A connection
    uses ``sqlite3.Row`` rows and waits up to ``BUSY_TIMEOUT_SECONDS`` for the
    write lock instead of failing immediately when another writer is active.

    Returns:
        The thread-local ``sqlite3.Connection``.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None and _local.path != _path:
        close_conn()
        conn = None
    if conn is None:
        _ensure_schema(_path)
        conn = sqlite3.connect(_path, timeout=BUSY_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        _local.conn, _local.path = conn, _path
    return conn


def close_conn():
    """Close and forget the calling thread's connection, if it has one."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
