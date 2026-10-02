from dataclasses import replace

from ..db import get_conn
from ..models import Settlement


def insert(settlement) -> Settlement:
    """Save a settlement row and return it with its generated id."""
    cur = get_conn().execute(
        "INSERT INTO settlements (group_id, from_user_id, to_user_id, amount, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            settlement.group_id,
            settlement.from_user_id,
            settlement.to_user_id,
            settlement.amount,
            settlement.created_at,
        ),
    )
    return replace(settlement, id=cur.lastrowid)


def list_for_group(group_id):
    """Return every settlement recorded in the group."""
    rows = get_conn().execute(
        "SELECT id, group_id, from_user_id, to_user_id, amount, created_at "
        "FROM settlements WHERE group_id = ?",
        (group_id,),
    ).fetchall()
    return [Settlement(**dict(r)) for r in rows]
