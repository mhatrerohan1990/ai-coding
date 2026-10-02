from typing import Optional

from ..db import get_conn
from ..models import IdempotencyRecord


def claim(key, fingerprint, created_at) -> bool:
    """Reserve ``key`` for this request.

    Returns:
        True if the key was free and is now reserved, False if it already exists.
        (``INSERT OR IGNORE`` waits for any concurrent writer, so two simultaneous
        requests with the same key cannot both win.)
    """
    cur = get_conn().execute(
        "INSERT OR IGNORE INTO idempotency_keys (key, fingerprint, created_at) "
        "VALUES (?, ?, ?)",
        (key, fingerprint, created_at),
    )
    return cur.rowcount == 1


def get(key) -> Optional[IdempotencyRecord]:
    """Return the record for ``key``, or ``None``."""
    row = get_conn().execute(
        "SELECT key, fingerprint, status, body, created_at FROM idempotency_keys "
        "WHERE key = ?",
        (key,),
    ).fetchone()
    return IdempotencyRecord(**dict(row)) if row else None


def save_response(key, status, body):
    """Attach the response (``status`` and JSON ``body`` text) to a claimed key."""
    get_conn().execute(
        "UPDATE idempotency_keys SET status = ?, body = ? WHERE key = ?",
        (status, body, key),
    )


def purge_before(created_at):
    """Delete keys created before the given ISO timestamp."""
    get_conn().execute("DELETE FROM idempotency_keys WHERE created_at < ?", (created_at,))
