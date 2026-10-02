from flask import Blueprint, jsonify

from ..services import balances as balances_service
from ..services import groups as groups_service
from ._http import json_body

bp = Blueprint("groups", __name__)


@bp.post("/groups")
def create_group():
    """POST /groups: create a group from existing users.

    Body: ``{"name": str, "members": [<user_id>, ...]}``. Returns
    ``{"id": <group_id>}`` with 201, or 400 if name/members are missing,
    invalid, or reference unknown users.
    """
    data = json_body("name", "members")
    group = groups_service.create_group(data["name"], data["members"])
    return jsonify(id=group.id), 201


@bp.get("/groups/<int:group_id>/balances")
def balances(group_id):
    """GET /groups/<id>/balances: net balance per member.

    Returns ``{"balances": {user_id: {"name", "balance"}}}``; a positive balance
    means the member is owed money, negative means they owe.
    """
    result = balances_service.get_balances(group_id)
    return jsonify(
        balances={b.user_id: {"name": b.name, "balance": b.balance} for b in result}
    )
