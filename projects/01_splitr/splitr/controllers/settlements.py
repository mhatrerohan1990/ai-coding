from flask import Blueprint, jsonify

from ..services import settlements as settlements_service
from ._http import json_body

bp = Blueprint("settlements", __name__)


@bp.post("/groups/<int:group_id>/settlements")
def settle(group_id):
    """POST /groups/<id>/settlements: record that one member paid another.

    Body: ``{"from": <user_id>, "to": <user_id>, "amount": number}``. Returns
    ``{"id": <settlement_id>}`` with 201, 400 if a field is missing or invalid,
    or 404 if the group does not exist.
    """
    data = json_body("from", "to", "amount")
    settlement = settlements_service.record_settlement(
        group_id, data["from"], data["to"], data["amount"]
    )
    return jsonify(id=settlement.id), 201
