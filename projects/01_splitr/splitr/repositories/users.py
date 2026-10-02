from typing import Optional

from ..db import get_conn
from ..models import User

UPDATABLE_COLUMNS = ("name", "email")


def insert(user):
    """Save a new ``User`` row."""
    get_conn().execute(
        "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
        (user.id, user.name, user.email),
    )


def get(user_id) -> Optional[User]:
    """Return the user with this id, or ``None``."""
    row = get_conn().execute(
        "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return User(**dict(row)) if row else None


def update(user_id, fields):
    """Set the given columns (``name`` and/or ``email``) on a user.

    Args:
        user_id: User to change.
        fields: ``{column: value}``; keys must be in ``UPDATABLE_COLUMNS``.

    Raises:
        ValueError: If a key is not an updatable column.
    """
    if not fields or not set(fields) <= set(UPDATABLE_COLUMNS):
        raise ValueError("can only update: %s" % ", ".join(UPDATABLE_COLUMNS))
    assignments = ", ".join("%s = ?" % column for column in fields)  # allowlisted names
    get_conn().execute(
        "UPDATE users SET %s WHERE id = ?" % assignments, (*fields.values(), user_id)
    )


def existing_ids(user_ids):
    """Return the subset of ``user_ids`` that exist, as a set."""
    placeholders = ",".join("?" * len(user_ids))
    rows = get_conn().execute(
        "SELECT id FROM users WHERE id IN (%s)" % placeholders, list(user_ids)
    ).fetchall()
    return {r["id"] for r in rows}
