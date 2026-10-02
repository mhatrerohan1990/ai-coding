import logging
from dataclasses import asdict
from datetime import datetime

from .. import db, notifier, validation
from ..errors import ValidationError
from ..models import Expense, Share
from ..repositories import expenses as expenses_repo
from . import groups as groups_service

log = logging.getLogger(__name__)

SORTABLE_COLUMNS = expenses_repo.SORTABLE_COLUMNS
MAX_LIMIT = 100


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
    group. Steps: load members, compute shares, insert the expense and one share
    per participant in one transaction (all-or-nothing), commit, then queue
    email notifications for background delivery. Notification problems are
    logged and never affect the saved expense.

    Args:
        group_id: Group the expense belongs to.
        paid_by: User id of the member who paid.
        amount: Total amount paid.
        description: Free-text label (used in the email subject).
        split_among: User ids that share the cost; ``None`` or empty means the
            whole group. The caller's list is never mutated.

    Returns:
        ``(expense, shares)``: the saved ``Expense`` and ``{user_id: amount}``.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If the amount is not a positive number with at most 2
            decimals, the payer or a participant is not a group member, a
            participant is listed twice, or the description is not a string.
    """
    groups_service.require_group(group_id)
    members = groups_service.get_members(group_id)
    member_ids = {m.id for m in members}
    validation.validate_amount(amount)
    if not isinstance(paid_by, str) or paid_by not in member_ids:
        raise ValidationError("paid_by must be the user id of a group member")
    if description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string")
    if not split_among:
        split_among = [m.id for m in members]
    else:
        validation.validate_ids(split_among, "split_among")
        unknown = [u for u in split_among if u not in member_ids]
        if unknown:
            raise ValidationError("split_among has non-members: %s" % unknown)

    shares = split_evenly(amount, split_among)

    with db.transaction():  # expense + shares commit together or not at all
        expense = expenses_repo.insert(
            Expense(None, group_id, paid_by, amount, description, datetime.now().isoformat())
        )
        expenses_repo.insert_shares(
            [Share(expense.id, user_id, share) for user_id, share in shares.items()]
        )

    # Notify only after the data is durably committed. Emails are queued on a
    # background worker so the request does not wait on the mail provider, and
    # a queueing failure must never fail an expense that has already been saved.
    try:
        payer_name = next(m.name for m in members if m.id == paid_by)
        notifier.notify_expense_async(
            [asdict(m) for m in members], payer_name, amount, description, shares
        )
    except Exception:
        log.exception("expense %s saved but notification was not queued", expense.id)
    return expense, shares


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
        A list of ``Expense`` objects.

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
    groups_service.require_group(group_id)
    return expenses_repo.list_for_group(group_id, limit, (page - 1) * limit, sort)
