from ..db import get_conn
from ..models import Group, User


def insert(name) -> Group:
    """Save a new group and return it with its generated id."""
    cur = get_conn().execute("INSERT INTO groups (name) VALUES (?)", (name,))
    return Group(id=cur.lastrowid, name=name)


def exists(group_id) -> bool:
    """True if a group with this id exists."""
    row = get_conn().execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone()
    return row is not None


def add_member(group_id, user_id):
    """Link an existing user to a group."""
    get_conn().execute(
        "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id)
    )


def members(group_id):
    """Return the group's members as ``User`` objects, in the order they were added."""
    rows = get_conn().execute(
        "SELECT u.id, u.name, u.email FROM group_members gm "
        "JOIN users u ON u.id = gm.user_id "
        "WHERE gm.group_id = ? ORDER BY gm.rowid",
        (group_id,),
    ).fetchall()
    return [User(**dict(r)) for r in rows]
