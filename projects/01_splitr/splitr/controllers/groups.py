from flask import Blueprint, jsonify

from .. import money
from ..services import balances as balances_service
from ..services import groups as groups_service
from ..services import settle_up as settle_up_service
from ._http import idempotent, json_body

bp = Blueprint("groups", __name__)


@bp.post("/groups")
@idempotent
def create_group():
    """POST /groups: create a group from existing users.

    Body: ``{"name": str, "members": [<user_id>, ...]}``. Returns
    ``{"id": <group_id>}`` with 201, or 400 if name/members are missing,
    invalid, or reference unknown users.
    """
    data = json_body("name", "members")
    group = groups_service.create_group(data["name"], data["members"])
    return {"id": group.id}, 201


@bp.get("/groups/<int:group_id>/balances")
def balances(group_id):
    """GET /groups/<id>/balances: net balance per member.

    Returns ``{"balances": {user_id: {"name", "balance"}}}``; a positive balance
    means the member is owed money, negative means they owe.
    """
    result = balances_service.get_balances(group_id)
    return jsonify(
        balances={
            b.user_id: {"name": b.name, "balance": money.to_amount(b.balance_cents)}
            for b in result
        }
    )


@bp.get("/groups/<int:group_id>/settle-up")
def settle_up(group_id):
    """GET /groups/<id>/settle-up: the fewest-payments plan that settles the group.

    Returns ``{"payments": [{"from", "from_name", "to", "to_name", "amount"}]}``.
    ``from``, ``to`` and ``amount`` match the ``POST /settlements`` body, so each
    payment can be recorded as-is once it has been made. Read-only; 404 if the
    group does not exist.
    """
    payments = settle_up_service.get_settle_up(group_id)
    return jsonify(
        payments=[
            {
                "from": p.from_user_id,
                "from_name": p.from_name,
                "to": p.to_user_id,
                "to_name": p.to_name,
                "amount": money.to_amount(p.amount_cents),
            }
            for p in payments
        ]
    )
