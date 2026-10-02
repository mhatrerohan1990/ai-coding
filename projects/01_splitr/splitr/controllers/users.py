from dataclasses import asdict

from flask import Blueprint, jsonify

from ..services import users as users_service
from ._http import idempotent, json_body

bp = Blueprint("users", __name__)


@bp.post("/users")
@idempotent
def create_user():
    """POST /users: create a user.

    Body: ``{"name": str, "email"?: str}``. Returns ``{"id": <uuid>}`` with 201,
    or 400 if the name is missing or a value is invalid.
    """
    data = json_body("name")
    user = users_service.create_user(data["name"], data.get("email"))
    return {"id": user.id}, 201


@bp.get("/users/<user_id>")
def get_user(user_id):
    """GET /users/<id>: return ``{"id", "name", "email"}``, or 404."""
    return jsonify(asdict(users_service.get_user(user_id)))


@bp.patch("/users/<user_id>")
def update_user(user_id):
    """PATCH /users/<id>: change the user's ``name`` and/or ``email``.

    Returns the updated user, 400 for invalid or empty updates, or 404 if the
    user does not exist. Group history is unaffected because everything
    references the user's id.
    """
    data = json_body()
    return jsonify(asdict(users_service.update_user(user_id, **data)))
