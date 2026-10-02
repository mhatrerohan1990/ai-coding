import logging
from dataclasses import asdict

from .. import clock, db, money, notifier, validation
from ..errors import ValidationError
from ..models import Expense, Share
from ..repositories import expenses as expenses_repo
from . import groups as groups_service

log = logging.getLogger(__name__)

SORTABLE_COLUMNS = expenses_repo.SORTABLE_COLUMNS
MAX_LIMIT = 100


def split_evenly(total_cents, people):
    """Divide ``total_cents`` between ``people`` without losing or inventing a cent.

    Every person gets ``total_cents // n`` and the leftover cents (fewer than
    ``n``) are handed out one each to the first people in the sequence, so the
    shares always sum exactly to the total (e.g. 10000 among 3 -> 3334, 3333, 3333).

    Args:
        total_cents: Total to split, in cents.
        people: Sequence of user ids.

    Returns:
        A ``{user_id: share_in_cents}`` dict whose values sum to ``total_cents``.
    """
    base, remainder = divmod(total_cents, len(people))
    return {p: base + (1 if i < remainder else 0) for i, p in enumerate(people)}


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
        amount: Total amount paid, a number with at most 2 decimals (see
            ``money.parse_amount``); it is converted to integer cents at once.
        description: Free-text label (used in the email subject).
        split_among: User ids that share the cost; ``None`` or empty means the
            whole group. The caller's list is never mutated.

    Returns:
        ``(expense, shares)``: the saved ``Expense`` and ``{user_id: cents}``.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If the amount is not a positive number with at most 2
            decimals, the payer or a participant is not a group member, a
            participant is listed twice, or the description is not a string.
    """
    groups_service.require_group(group_id)
    members = groups_service.get_members(group_id)
    member_ids = {m.id for m in members}
    amount_cents = money.parse_amount(amount)
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

    shares = split_evenly(amount_cents, split_among)

    with db.transaction():  # expense + shares commit together or not at all
        expense = expenses_repo.insert(
            Expense(None, group_id, paid_by, amount_cents, description, clock.utc_now_iso())
        )
        expenses_repo.insert_shares(
            [Share(expense.id, user_id, cents) for user_id, cents in shares.items()]
        )

    # Notify only after the data is durably committed (after the *outermost*
    # transaction, which may belong to the idempotency layer), so a rolled-back
    # or replayed request never sends email. Emails are queued on a background
    # worker, and a failure here must never fail an expense that is already saved.
    def notify():
        try:
            payer_name = next(m.name for m in members if m.id == paid_by)
            notifier.notify_expense_async(
                [asdict(m) for m in members],
                payer_name,
                money.to_amount(amount_cents),
                description,
                {user_id: money.to_amount(c) for user_id, c in shares.items()},
            )
        except Exception:
            log.exception("expense %s saved but notification was not queued", expense.id)

    db.after_commit(notify)
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
