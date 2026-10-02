from .. import db
from ..models import Balance
from ..repositories import expenses as expenses_repo
from ..repositories import settlements as settlements_repo
from . import groups as groups_service


def get_balances(group_id):
    """Net balance per member. Positive = the group owes them money.

    Computed on the fly: each expense credits its payer with the full amount,
    each share debits the member who owes it, and each settlement debits the
    payer (``from``) and credits the receiver (``to``). All reads happen inside
    one read snapshot, so the result is consistent even while other requests
    are writing.

    Returns:
        A list of ``Balance`` objects (one per member), in integer cents.

    Raises:
        GroupNotFound: If the group does not exist.
    """
    groups_service.require_group(group_id)
    with db.read_snapshot():
        members = groups_service.get_members(group_id)
        names = {m.id: m.name for m in members}
        bal = {m.id: 0 for m in members}

        for user_id, cents in expenses_repo.paid_amounts(group_id):
            bal[user_id] = bal.get(user_id, 0) + cents
        for user_id, cents in expenses_repo.share_amounts(group_id):
            bal[user_id] = bal.get(user_id, 0) - cents
        for s in settlements_repo.list_for_group(group_id):
            bal[s.from_user_id] = bal.get(s.from_user_id, 0) + s.amount_cents
            bal[s.to_user_id] = bal.get(s.to_user_id, 0) - s.amount_cents

    return [Balance(uid, names.get(uid), cents) for uid, cents in bal.items()]
