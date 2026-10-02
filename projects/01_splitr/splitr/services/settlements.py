from datetime import datetime

from .. import db, validation
from ..errors import ValidationError
from ..models import Settlement
from ..repositories import settlements as settlements_repo
from . import groups as groups_service


def record_settlement(group_id, from_user, to_user, amount):
    """Record that ``from_user`` paid ``to_user`` ``amount``.

    Args:
        group_id: Group the settlement belongs to.
        from_user: User id of the member who paid.
        to_user: User id of the member who received the money.
        amount: Positive amount with at most 2 decimals.

    Returns:
        The saved ``Settlement``.

    Raises:
        GroupNotFound: If the group does not exist.
        ValidationError: If either party is not a member, they are the same
            person, or the amount is not a positive number with at most 2
            decimals.
    """
    groups_service.require_group(group_id)
    member_ids = {m.id for m in groups_service.get_members(group_id)}
    for party in (from_user, to_user):
        if not isinstance(party, str) or party not in member_ids:
            raise ValidationError("from and to must be user ids of group members")
    if from_user == to_user:
        raise ValidationError("from and to must be different members")
    validation.validate_amount(amount)
    with db.transaction():
        return settlements_repo.insert(
            Settlement(None, group_id, from_user, to_user, amount, datetime.now().isoformat())
        )
