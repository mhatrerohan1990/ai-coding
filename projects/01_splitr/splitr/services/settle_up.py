import heapq

from ..models import Payment
from . import balances as balances_service


def simplify_debts(balances_cents):
    """Turn net balances into a short list of payments that settles everyone.

    Greedy matching: repeatedly have the member who owes the most pay the member
    owed the most, for the smaller of the two amounts. Each payment fully clears
    at least one of the two people, so at most ``n - 1`` payments are produced
    for ``n`` members (not always the absolute minimum, which is NP-hard to find).
    Ties are broken by the order of ``balances_cents`` so the result is
    deterministic. Works in integer cents to avoid float drift.

    Args:
        balances_cents: ``{user_id: net balance in cents}``; positive = owed
            money, negative = owes. They should sum to zero.

    Returns:
        A list of ``(from_user_id, to_user_id, cents)`` tuples. Applying them
        brings every balance to zero.
    """
    creditors, debtors = [], []  # heaps; negative keys so the largest pops first
    for order, (user_id, cents) in enumerate(balances_cents.items()):
        if cents > 0:
            creditors.append((-cents, order, user_id))
        elif cents < 0:
            debtors.append((cents, order, user_id))
    heapq.heapify(creditors)
    heapq.heapify(debtors)

    payments = []
    while creditors and debtors:
        neg_credit, credit_order, creditor = heapq.heappop(creditors)
        neg_debt, debt_order, debtor = heapq.heappop(debtors)
        credit, debt = -neg_credit, -neg_debt
        pay = min(credit, debt)
        payments.append((debtor, creditor, pay))
        if credit > pay:
            heapq.heappush(creditors, (-(credit - pay), credit_order, creditor))
        if debt > pay:
            heapq.heappush(debtors, (-(debt - pay), debt_order, debtor))
    return payments


def get_settle_up(group_id):
    """Suggest the payments that would settle a group's current balances.

    Read-only: nothing is recorded. Members record each payment they actually
    make as a settlement, after which this returns an empty list.

    Returns:
        A list of ``Payment`` objects (empty if the group is already settled).

    Raises:
        GroupNotFound: If the group does not exist.
    """
    balances = balances_service.get_balances(group_id)
    names = {b.user_id: b.name for b in balances}
    cents = {b.user_id: b.balance_cents for b in balances}
    return [
        Payment(debtor, names[debtor], creditor, names[creditor], amount)
        for debtor, creditor, amount in simplify_debts(cents)
    ]
