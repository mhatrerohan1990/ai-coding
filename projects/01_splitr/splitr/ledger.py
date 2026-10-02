import logging
import math
import uuid
from datetime import datetime

from . import notifier
from .db import get_conn

log = logging.getLogger(__name__)


SORTABLE_COLUMNS = ("id", "amount", "description", "created_at")
MAX_LIMIT = 100


class ValidationError(ValueError):
    """The request data is invalid; the API maps this to HTTP 400."""


class NotFound(LookupError):
    """A referenced resource does not exist; the API maps this to HTTP 404."""


class GroupNotFound(NotFound):
    """The group id does not exist."""


class UserNotFound(NotFound):
    """The user id does not exist."""


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


def _validate_user_fields(fields):
    """Validate the ``name`` and/or ``email`` entries present in ``fields``."""
    if "name" in fields and not _is_name(fields["name"]):
        raise ValidationError("name must be a non-empty string")
    if "email" in fields:
        email = fields["email"]
        if email is not None and not (isinstance(email, str) and "@" in email):
            raise ValidationError("email must be a string containing '@', or null")


def _validate_ids(value, field):
    """Require a non-empty list of unique strings (user ids)."""
    if not isinstance(value, list) or not value:
        raise ValidationError("%s must be a non-empty list of user ids" % field)
    if not all(isinstance(v, str) and v for v in value):
        raise ValidationError("%s must contain only user id strings" % field)
    if len(set(value)) != len(value):
        raise ValidationError("%s contains duplicates" % field)


def _validate_group_input(name, member_ids):
    """Require a named group and a non-empty list of unique user ids."""
    if not _is_name(name):
        raise ValidationError("name must be a non-empty string")
    _validate_ids(member_ids, "members")


def _require_users(user_ids):
    """Raise ``ValidationError`` if any of ``user_ids`` is not an existing user."""
    placeholders = ",".join("?" * len(user_ids))
    rows = get_conn().execute(
        "SELECT id FROM users WHERE id IN (%s)" % placeholders, user_ids
    ).fetchall()
    unknown = set(user_ids) - {r["id"] for r in rows}
    if unknown:
        raise ValidationError("unknown user ids: %s" % sorted(unknown))


def create_user(name, email=None):
    """Create a user with a fresh random UUID.

    Args:
        name: Display name (non-empty string).
        email: Optional address used for notifications; may change later.

    Returns:
        The new user's id (a UUID4 string).

    Raises:
        ValidationError: If the name or email is invalid.
    """
    fields = {"name": name, "email": email}
    _validate_user_fields(fields)
    user_id = str(uuid.uuid4())
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO users (id, name, email) VALUES (?, ?, ?)", (user_id, name, email)
        )
    return user_id


def get_user(user_id):
    """Fetch a user as ``{"id", "name", "email"}``.

    Raises:
        UserNotFound: If no such user exists.
    """
    row = get_conn().execute(
        "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise UserNotFound("user %s not found" % user_id)
    return dict(row)


def update_user(user_id, **fields):
    """Change a user's ``name`` and/or ``email``; other keys are ignored.

    Because everything else references the user's id, a rename or email change
    applies everywhere at once and history is untouched. ``email=None`` clears
    the address.

    Returns:
        The updated user dict.

    Raises:
        UserNotFound: If no such user exists.
        ValidationError: If nothing to update was given or a value is invalid.
    """
    updates = {k: fields[k] for k in ("name", "email") if k in fields}
    if not updates:
        raise ValidationError("provide name and/or email to update")
    get_user(user_id)
    _validate_user_fields(updates)
    assignments = ", ".join("%s = ?" % column for column in updates)  # fixed columns only
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE users SET %s WHERE id = ?" % assignments, (*updates.values(), user_id)
        )
    return get_user(user_id)


def create_group(name, member_ids):
    """Insert a group and link its members atomically.

    Runs in a single transaction: if any membership insert fails, the group row
    is rolled back too, so no partial group is left behind.

    Args:
        name: Group name.
        member_ids: List of existing user ids to add as members.

    Returns:
        The new group's integer id.

    Raises:
        ValidationError: If the name is invalid or the members are not a
            non-empty list of unique, existing user ids.
    """
    _validate_group_input(name, member_ids)
    _require_users(member_ids)
    conn = get_conn()
    with conn:  # commits on success, rolls back on any exception
        cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        group_id = cur.lastrowid
        for user_id in member_ids:
            conn.execute(
                "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                (group_id, user_id),
            )
    return group_id


def get_members(group_id):
    """Fetch the members of a group, in the order they were added.

    Returns:
        A list of ``{"id": ..., "name": ..., "email": ...}`` dicts (empty if the
        group has no members or does not exist).
    """
    rows = get_conn().execute(
        "SELECT u.id, u.name, u.email FROM group_members gm "
        "JOIN users u ON u.id = gm.user_id "
        "WHERE gm.group_id = ? ORDER BY gm.rowid",
        (group_id,),
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
        people: Sequence of user ids.

    Returns:
        A ``{user_id: share}`` dict whose values sum to ``amount``.
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
    commit, then queue email notifications for background delivery. Notification
    problems are logged and never affect the saved expense.

    Args:
        group_id: Group the expense belongs to.
        paid_by: User id of the member who paid.
        amount: Total amount paid.
        description: Free-text label (used in the email subject).
        split_among: User ids that share the cost; ``None`` or empty means the
            whole group. The caller's list is never mutated.

    Returns:
        ``(expense_id, shares)`` where ``shares`` is ``{user_id: amount}``.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If the amount is not a positive number with at most 2
            decimals, the payer or a participant is not a group member, a
            participant is listed twice, or the description is not a string.
    """
    _require_group(group_id)
    members = get_members(group_id)
    member_ids = {m["id"] for m in members}
    _validate_amount(amount)
    if not isinstance(paid_by, str) or paid_by not in member_ids:
        raise ValidationError("paid_by must be the user id of a group member")
    if description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string")
    if not split_among:
        split_among = [m["id"] for m in members]
    else:
        _validate_ids(split_among, "split_among")
        unknown = [u for u in split_among if u not in member_ids]
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
        for user_id, share in shares.items():
            conn.execute(
                "INSERT INTO shares (expense_id, user_id, amount) VALUES (?, ?, ?)",
                (expense_id, user_id, share),
            )

    # Notify only after the data is durably committed. Emails are queued on a
    # background worker so the request does not wait on the mail provider, and
    # a queueing failure must never fail an expense that has already been saved.
    try:
        payer_name = next(m["name"] for m in members if m["id"] == paid_by)
        notifier.notify_expense_async(members, payer_name, amount, description, shares)
    except Exception:
        log.exception("expense %s saved but notification was not queued", expense_id)
    return expense_id, shares


def list_expenses(group_id, page=1, limit=20, sort="created_at"):
    """Return a page of a group's expenses, ordered by ``sort`` descending.

    Ties are broken by ``id`` (also descending) so pages are stable and never
    repeat or skip rows.

    Args:
        group_id: Group to list.
        page: 1-based page number; the OFFSET is ``(page - 1) * limit``.
        limit: Page size, between 1 and ``MAX_LIMIT``.
        sort: Column to order by; must be one of ``SORTABLE_COLUMNS``.

    Returns:
        A list of dicts with id, paid_by (user id), amount, description,
        created_at.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If ``sort`` is not an allowed column, ``page`` is not
            an integer >= 1, or ``limit`` is not an integer in 1..``MAX_LIMIT``.
    """
    if sort not in SORTABLE_COLUMNS:
        raise ValidationError("sort must be one of: %s" % ", ".join(SORTABLE_COLUMNS))
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValidationError("page must be an integer >= 1")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValidationError("limit must be an integer between 1 and %d" % MAX_LIMIT)
    _require_group(group_id)
    offset = (page - 1) * limit
    # ``sort`` is checked against the allowlist above, so interpolating it is safe.
    rows = get_conn().execute(
        f"SELECT id, paid_by, amount, description, created_at FROM expenses "
        f"WHERE group_id = ? ORDER BY {sort} DESC, id DESC LIMIT ? OFFSET ?",
        (group_id, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def record_settlement(group_id, from_user, to_user, amount):
    """Record that ``from_user`` paid ``to_user`` ``amount``, and commit.

    Args:
        group_id: Group the settlement belongs to.
        from_user: User id of the member who paid.
        to_user: User id of the member who received the money.
        amount: Positive amount with at most 2 decimals.

    Returns:
        The new settlement's integer id.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If either party is not a member, they are the same
            person, or the amount is not a positive number with at most 2
            decimals.
    """
    _require_group(group_id)
    member_ids = {m["id"] for m in get_members(group_id)}
    for party in (from_user, to_user):
        if not isinstance(party, str) or party not in member_ids:
            raise ValidationError("from and to must be user ids of group members")
    if from_user == to_user:
        raise ValidationError("from and to must be different members")
    _validate_amount(amount)
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO settlements "
            "(group_id, from_user_id, to_user_id, amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, from_user, to_user, amount, datetime.now().isoformat()),
        )
    return cur.lastrowid


def balances(group_id):
    """Net balance per member. Positive = the group owes them money.

    Computed on the fly from three tables: each expense credits its payer with
    the full amount, each share debits the member who owes it, and each
    settlement debits the payer (``from``) and credits the receiver (``to``).
    All reads happen inside one read transaction, so the result is a consistent
    snapshot even while other requests are writing.

    Returns:
        ``{user_id: {"name": str, "balance": float}}`` with balances rounded to
        2 decimals.

    Raises:
        GroupNotFound: If the group does not exist.
    """
    _require_group(group_id)
    conn = get_conn()
    conn.execute("BEGIN")  # snapshot: one consistent view across the queries
    try:
        members = get_members(group_id)
        names = {m["id"]: m["name"] for m in members}
        bal = {m["id"]: 0.0 for m in members}

        for e in conn.execute(
            "SELECT paid_by, amount FROM expenses WHERE group_id = ?", (group_id,)
        ):
            bal[e["paid_by"]] = bal.get(e["paid_by"], 0.0) + e["amount"]

        for s in conn.execute(
            "SELECT s.user_id, s.amount FROM shares s "
            "JOIN expenses e ON e.id = s.expense_id WHERE e.group_id = ?",
            (group_id,),
        ):
            bal[s["user_id"]] = bal.get(s["user_id"], 0.0) - s["amount"]

        for st in conn.execute(
            "SELECT from_user_id, to_user_id, amount FROM settlements WHERE group_id = ?",
            (group_id,),
        ):
            bal[st["from_user_id"]] = bal.get(st["from_user_id"], 0.0) - st["amount"]
            bal[st["to_user_id"]] = bal.get(st["to_user_id"], 0.0) + st["amount"]
    finally:
        conn.rollback()  # read-only: just end the snapshot

    return {
        uid: {"name": names.get(uid), "balance": round(v, 2)} for uid, v in bal.items()
    }
