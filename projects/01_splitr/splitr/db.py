import logging
import sqlite3
import threading
from contextlib import contextmanager

log = logging.getLogger(__name__)

_path = "splitr.db"
_local = threading.local()  # one connection (and transaction state) per thread
_schema_lock = threading.Lock()
_schema_ready = set()  # database paths whose schema has been created
BUSY_TIMEOUT_SECONDS = 10

SCHEMA_VERSION = 3
# Older versions whose tables are a subset of the current schema: opening one just
# adds the missing tables (CREATE TABLE IF NOT EXISTS) and bumps the version.
UPGRADABLE_FROM = (2,)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id),
    paid_by TEXT NOT NULL,
    amount REAL NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id, paid_by) REFERENCES group_members(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS shares (
    expense_id INTEGER NOT NULL REFERENCES expenses(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    amount REAL NOT NULL,
    PRIMARY KEY (expense_id, user_id)
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id),
    from_user_id TEXT NOT NULL,
    to_user_id TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (group_id, from_user_id) REFERENCES group_members(group_id, user_id),
    FOREIGN KEY (group_id, to_user_id) REFERENCES group_members(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    status INTEGER,
    body TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_group ON expenses(group_id);
CREATE INDEX IF NOT EXISTS idx_idempotency_created ON idempotency_keys(created_at);
CREATE INDEX IF NOT EXISTS idx_settlements_group ON settlements(group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);
"""


def _ensure_schema(path):
    """Create the tables (and switch to WAL) once per database path.

    The schema version is stored in ``PRAGMA user_version``. Versions listed in
    ``UPGRADABLE_FROM`` only lack newer tables and are upgraded in place; any
    other older layout is refused rather than silently mixed with the new one.

    Raises:
        RuntimeError: If ``path`` holds a database with an older schema.
    """
    with _schema_lock:
        if path in _schema_ready:
            return
        conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            has_tables = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'groups'"
            ).fetchone()
            if has_tables and version not in (SCHEMA_VERSION, *UPGRADABLE_FROM):
                raise RuntimeError(
                    "%s uses an old schema (version %s, need %s); "
                    "delete it to start fresh" % (path, version, SCHEMA_VERSION)
                )
            # WAL lets readers run alongside the single writer.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
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
    uses ``sqlite3.Row`` rows, enforces foreign keys (SQLite leaves them off by
    default), and waits up to ``BUSY_TIMEOUT_SECONDS`` for the write lock instead
    of failing immediately when another writer is active.

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
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn, _local.path = conn, _path
    return conn


def close_conn():
    """Close and forget the calling thread's connection, if it has one."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


@contextmanager
def transaction():
    """Run a block as one atomic unit: commit on success, roll back on any error.

    Services use this to group several repository writes (e.g. an expense and
    its shares) so they are saved together or not at all. It nests: an inner
    ``transaction()`` joins the outer one, and only the outermost block commits
    or rolls back, so a caller (e.g. the idempotency layer) can make a whole
    service call atomic with its own bookkeeping.

    Yields:
        The thread's ``sqlite3.Connection``.
    """
    conn = get_conn()
    if getattr(_local, "depth", 0) > 0:
        _local.depth += 1
        try:
            yield conn
        finally:
            _local.depth -= 1
        return

    _local.depth, _local.after_commit = 1, []
    try:
        with conn:
            yield conn
    except BaseException:
        _local.after_commit = []  # rolled back: the queued side effects must not happen
        raise
    finally:
        _local.depth = 0

    callbacks, _local.after_commit = _local.after_commit, []
    for callback in callbacks:
        try:
            callback()
        except Exception:
            log.exception("after-commit callback failed")


def after_commit(callback):
    """Run ``callback`` once the current transaction has committed.

    Inside ``transaction()`` the callback is held until the outermost block
    commits, and dropped if it rolls back (use it for side effects such as
    sending email). Outside any transaction it runs immediately.
    """
    if getattr(_local, "depth", 0) > 0:
        _local.after_commit.append(callback)
    else:
        callback()


@contextmanager
def read_snapshot():
    """Run several reads against one consistent snapshot of the database.

    Opens a read transaction and always ends it (nothing is written), so writes
    committed by other requests while the block runs are not seen half-way.

    Yields:
        The thread's ``sqlite3.Connection``.
    """
    conn = get_conn()
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.rollback()
