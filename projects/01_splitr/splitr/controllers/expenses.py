from flask import Blueprint, jsonify, request

from .. import money
from ..services import expenses as expenses_service
from ._http import idempotent, int_arg, json_body

bp = Blueprint("expenses", __name__)


@bp.post("/groups/<int:group_id>/expenses")
@idempotent
def add_expense(group_id):
    """POST /groups/<id>/expenses: log an expense and split it.

    Body: ``{"paid_by", "amount", "description"?, "split_among"?}`` where
    ``paid_by`` and ``split_among`` use user ids. Only those known keys are
    forwarded to the service. Returns
    ``{"id": <expense_id>, "shares": {user_id: amount}}`` with 201, 400 if the
    input is missing or invalid, or 404 if the group does not exist.
    """
    data = json_body("paid_by", "amount")
    payload = {
        k: data[k] for k in ("paid_by", "amount", "description", "split_among") if k in data
    }
    expense, shares = expenses_service.add_expense(group_id, **payload)
    return {
        "id": expense.id,
        "shares": {user_id: money.to_amount(c) for user_id, c in shares.items()},
    }, 201


@bp.get("/groups/<int:group_id>/expenses")
def list_expenses(group_id):
    """GET /groups/<id>/expenses: paginated list of a group's expenses.

    Query params: ``page`` (default 1), ``limit`` (default 20, max 100) and
    ``sort`` (one of ``SORTABLE_COLUMNS``, default ``created_at``). Returns
    ``{"expenses": [...]}``; 400 for invalid params, 404 for an unknown group.
    """
    expenses = expenses_service.list_expenses(
        group_id,
        page=int_arg("page", 1),
        limit=int_arg("limit", 20),
        sort=request.args.get("sort", "created_at"),
    )
    return jsonify(
        expenses=[
            {
                "id": e.id,
                "paid_by": e.paid_by,
                "amount": money.to_amount(e.amount_cents),
                "description": e.description,
                "created_at": e.created_at,
            }
            for e in expenses
        ]
    )
