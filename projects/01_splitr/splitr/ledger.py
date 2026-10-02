import logging
import math
from datetime import datetime

from . import notifier
from .db import get_conn

log = logging.getLogger(__name__)


class ValidationError(ValueError):
    """The request data is invalid; the API maps this to HTTP 400."""


class GroupNotFound(LookupError):
    """The group id does not exist; the API maps this to HTTP 404."""


def _is_name(value):
    return isinstance(value, str) and bool(value.strip())


def _require_group(group_id):
    """Raise ``GroupNotFound`` unless ``group_id`` exists."""
    row = get_conn().execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone()
    if row is None:
        raise GroupNotFound("group %s not found" % group_id)


def _validate_amount(amount):
    """Require a finite positive number with at most 2 decimal places."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValidationError("amount must be a number")
    if not math.isfinite(amount) or amount <= 0:
        raise ValidationError("amount must be greater than 0")
    if abs(amount * 100 - round(amount * 100)) > 1e-6:
        raise ValidationError("amount must have at most 2 decimal places")


def _validate_members(name, members):
    """Require a named group and a non-empty list of uniquely named members."""
    if not _is_name(name):
        raise ValidationError("name must be a non-empty string")
    if not isinstance(members, list) or not members:
        raise ValidationError("members must be a non-empty list")
    seen = set()
    for m in members:
        if not isinstance(m, dict) or not _is_name(m.get("name")):
            raise ValidationError("each member needs a non-empty name")
        if m.get("email") is not None and not isinstance(m["email"], str):
            raise ValidationError("member email must be a string")
        if m["name"] in seen:
            raise ValidationError("duplicate member name: %s" % m["name"])
        seen.add(m["name"])


def create_group(name, members):
    """Insert a group and its members atomically.

    Runs in a single transaction: if any member insert fails, the group row is
    rolled back too, so no partial group is left behind.

    Args:
        name: Group name.
        members: Iterable of dicts with a ``name`` and optional ``email``.

    Returns:
        The new group's integer id.

    Raises:
        ValidationError: If the name or members are invalid.
    """
    _validate_members(name, members)
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
    """Divide ``amount`` between ``people`` without losing or inventing cents.

    Works in integer cents: every person gets ``total_cents // n`` and the
    leftover cents (fewer than ``n``) are handed out one each to the first
    people in the sequence. Shares therefore always sum exactly to ``amount``
    (e.g. 100 among 3 -> 33.34, 33.33, 33.33).

    Args:
        amount: Total amount to split.
        people: Sequence of member names.

    Returns:
        A ``{name: share}`` dict whose values sum to ``amount``.
    """
    cents = round(amount * 100)
    base, remainder = divmod(cents, len(people))
    return {
        p: (base + (1 if i < remainder else 0)) / 100 for i, p in enumerate(people)
    }


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

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If the amount is not a positive number with at most 2
            decimals, the payer or a participant is not a group member, a
            participant is listed twice, or the description is not a string.
    """
    _require_group(group_id)
    members = get_members(group_id)
    names = {m["name"] for m in members}
    _validate_amount(amount)
    if paid_by not in names:
        raise ValidationError("paid_by must be a member of the group")
    if description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string")
    if not split_among:
        split_among = [m["name"] for m in members]
    else:
        if not isinstance(split_among, list):
            raise ValidationError("split_among must be a list of member names")
        if len(set(split_among)) != len(split_among):
            raise ValidationError("split_among contains duplicates")
        unknown = [n for n in split_among if n not in names]
        if unknown:
            raise ValidationError("split_among has non-members: %s" % unknown)

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

    Raises:
        GroupNotFound: If the group does not exist.
    """
    _require_group(group_id)
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

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If either party is not a member, they are the same
            person, or the amount is not a positive number with at most 2
            decimals.
    """
    _require_group(group_id)
    names = {m["name"] for m in get_members(group_id)}
    if from_member not in names or to_member not in names:
        raise ValidationError("from and to must be members of the group")
    if from_member == to_member:
        raise ValidationError("from and to must be different members")
    _validate_amount(amount)
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

    Raises:
        GroupNotFound: If the group does not exist.
    """
    _require_group(group_id)
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
