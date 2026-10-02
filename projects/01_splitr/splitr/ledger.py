import logging
from datetime import datetime

from . import notifier
from .db import get_conn

log = logging.getLogger(__name__)


def create_group(name, members):
    """Insert a group and its members atomically.

    Runs in a single transaction: if any member insert fails, the group row is
    rolled back too, so no partial group is left behind.

    Args:
        name: Group name.
        members: Iterable of dicts with a ``name`` and optional ``email``.

    Returns:
        The new group's integer id.
    """
    conn = get_conn()
    with conn:  # commits on success, rolls back on any exception
        cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        group_id = cur.lastrowid
        for m in members:
            conn.execute(
                "INSERT INTO members (group_id, name, email) VALUES (?, ?, ?)",
                (group_id, m["name"], m.get("email")),
            )
    return group_id


def get_members(group_id):
    """Fetch the members of a group.

    Returns:
        A list of ``{"name": ..., "email": ...}`` dicts (empty if the group has
        no members or does not exist).
    """
    rows = get_conn().execute(
        "SELECT name, email FROM members WHERE group_id = ?", (group_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def split_evenly(amount, people):
    """Divide ``amount`` equally between ``people``.

    Each share is ``amount / len(people)`` rounded to 2 decimal places.

    Args:
        amount: Total amount to split.
        people: Sequence of member names.

    Returns:
        A ``{name: share}`` dict.
    """
    share = round(amount / len(people), 2)
    return {p: share for p in people}


def add_expense(group_id, paid_by, amount, description="", split_among=None):
    """Record an expense, split it, and notify the participants.

    If ``split_among`` is empty the expense is split across every member of the
    group. Steps: load members, compute shares, insert the ``expenses`` row and
    one ``shares`` row per participant in one transaction (all-or-nothing),
    commit, then send email notifications. A notification failure is logged and
    does not affect the saved expense.

    Args:
        group_id: Group the expense belongs to.
        paid_by: Name of the member who paid.
        amount: Total amount paid.
        description: Free-text label (used in the email subject).
        split_among: Names that share the cost; ``None`` or empty means the
            whole group. The caller's list is never mutated.

    Returns:
        ``(expense_id, shares)`` where ``shares`` is ``{name: amount}``.
    """
    members = get_members(group_id)
    if not split_among:
        split_among = [m["name"] for m in members]

    shares = split_evenly(amount, split_among)

    conn = get_conn()
    with conn:  # expense + shares commit together or not at all
        cur = conn.execute(
            "INSERT INTO expenses (group_id, paid_by, amount, description, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, paid_by, amount, description, datetime.now().isoformat()),
        )
        expense_id = cur.lastrowid
        for member, share in shares.items():
            conn.execute(
                "INSERT INTO shares (expense_id, member, amount) VALUES (?, ?, ?)",
                (expense_id, member, share),
            )

    # Notify only after the data is durably committed, and never let an email
    # failure undo or fail an expense that has already been saved.
    try:
        notifier.notify_expense(members, paid_by, amount, description, shares)
    except Exception:
        log.exception("expense %s saved but notification failed", expense_id)
    return expense_id, shares


def list_expenses(group_id, page=1, limit=20, sort="created_at"):
    """Return a page of a group's expenses, ordered by ``sort`` descending.

    Args:
        group_id: Group to list.
        page: 1-based page number; the OFFSET is ``(page - 1) * limit``.
        limit: Page size.
        sort: Column name to order by (interpolated into the SQL).

    Returns:
        A list of dicts with id, paid_by, amount, description, created_at.
    """
    offset = (page - 1) * limit
    rows = get_conn().execute(
        f"SELECT id, paid_by, amount, description, created_at FROM expenses "
        f"WHERE group_id = ? ORDER BY {sort} DESC LIMIT ? OFFSET ?",
        (group_id, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def record_settlement(group_id, from_member, to_member, amount):
    """Record that ``from_member`` paid ``to_member`` ``amount``, and commit.

    Returns:
        The new settlement's integer id.
    """
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO settlements (group_id, from_member, to_member, amount, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, from_member, to_member, amount, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def balances(group_id):
    """Net balance per member. Positive = the group owes them money.

    Computed on the fly from three tables: each expense credits its payer with
    the full amount, each share debits the member who owes it, and each
    settlement debits the payer (``from``) and credits the receiver (``to``).
    Names not in the members table are added as they are encountered.

    Returns:
        A ``{name: balance}`` dict with values rounded to 2 decimals.
    """
    conn = get_conn()
    bal = {m["name"]: 0.0 for m in get_members(group_id)}

    for e in conn.execute(
        "SELECT paid_by, amount FROM expenses WHERE group_id = ?", (group_id,)
    ):
        bal[e["paid_by"]] = bal.get(e["paid_by"], 0.0) + e["amount"]

    for s in conn.execute(
        "SELECT s.member, s.amount FROM shares s "
        "JOIN expenses e ON e.id = s.expense_id WHERE e.group_id = ?",
        (group_id,),
    ):
        bal[s["member"]] = bal.get(s["member"], 0.0) - s["amount"]

    for st in conn.execute(
        "SELECT from_member, to_member, amount FROM settlements WHERE group_id = ?",
        (group_id,),
    ):
        bal[st["from_member"]] = bal.get(st["from_member"], 0.0) - st["amount"]
        bal[st["to_member"]] = bal.get(st["to_member"], 0.0) + st["amount"]

    return {name: round(v, 2) for name, v in bal.items()}
