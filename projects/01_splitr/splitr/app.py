from flask import Flask, jsonify, request

from . import db, ledger
from .ledger import NotFound, ValidationError


def create_app(db_path="splitr.db"):
    """Application factory: build the Flask app and register all routes.

    Initialises the module-level SQLite connection (see ``db.init``) pointing at
    ``db_path``, then defines the HTTP handlers as closures over the app.

    Args:
        db_path: Filesystem path of the SQLite database file.

    Returns:
        A configured ``Flask`` instance (used by ``run.py`` and the tests).
    """
    app = Flask(__name__)
    db.init(db_path)

    @app.teardown_appcontext
    def release_connection(exc):
        """Close this thread's database connection when the request ends."""
        db.close_conn()

    def _int_arg(name, default):
        """Read an integer query parameter, or raise ``ValidationError``."""
        raw = request.args.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ValidationError("%s must be an integer" % name)

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(NotFound)
    def handle_not_found(e):
        return jsonify(error=str(e)), 404

    @app.post("/users")
    def create_user():
        """POST /users: create a user.

        Body: ``{"name": str, "email"?: str}``. Returns ``{"id": <uuid>}`` with
        201, or 400 if the name is missing or a value is invalid.
        """
        data = request.get_json()
        if not isinstance(data, dict) or "name" not in data:
            return jsonify(error="name is required"), 400
        return jsonify(id=ledger.create_user(data["name"], data.get("email"))), 201

    @app.get("/users/<user_id>")
    def get_user(user_id):
        """GET /users/<id>: return ``{"id", "name", "email"}``, or 404."""
        return jsonify(ledger.get_user(user_id))

    @app.patch("/users/<user_id>")
    def update_user(user_id):
        """PATCH /users/<id>: change the user's ``name`` and/or ``email``.

        Returns the updated user, 400 for invalid or empty updates, or 404 if the
        user does not exist. Group history is unaffected because everything
        references the user's id.
        """
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify(error="a JSON object is required"), 400
        return jsonify(ledger.update_user(user_id, **data))

    @app.post("/groups")
    def create_group():
        """POST /groups: create a group from existing users.

        Body: ``{"name": str, "members": [<user_id>, ...]}``. Returns
        ``{"id": <group_id>}`` with 201, or 400 if name/members are missing,
        invalid, or reference unknown users.
        """
        data = request.get_json()
        if not isinstance(data, dict) or "name" not in data or "members" not in data:
            return jsonify(error="name and members are required"), 400
        group_id = ledger.create_group(data["name"], data["members"])
        return jsonify(id=group_id), 201

    @app.post("/groups/<int:group_id>/expenses")
    def add_expense(group_id):
        """POST /groups/<id>/expenses: log an expense and split it.

        Body: ``{"paid_by", "amount", "description"?, "split_among"?}`` where
        ``paid_by`` and ``split_among`` use user ids. Only those known keys are
        forwarded to ``ledger.add_expense``. Returns
        ``{"id": <expense_id>, "shares": {user_id: amount}}`` with 201, 400 if the
        input is missing or invalid, or 404 if the group does not exist.
        """
        data = request.get_json()
        if not isinstance(data, dict) or "paid_by" not in data or "amount" not in data:
            return jsonify(error="paid_by and amount are required"), 400
        payload = {
            k: data[k]
            for k in ("paid_by", "amount", "description", "split_among")
            if k in data
        }
        expense_id, shares = ledger.add_expense(group_id, **payload)
        return jsonify(id=expense_id, shares=shares), 201

    @app.get("/groups/<int:group_id>/expenses")
    def list_expenses(group_id):
        """GET /groups/<id>/expenses: paginated list of a group's expenses.

        Query params: ``page`` (default 1), ``limit`` (default 20, max 100) and
        ``sort`` (one of ``ledger.SORTABLE_COLUMNS``, default ``created_at``).
        Returns ``{"expenses": [...]}``; 400 for invalid params, 404 for an
        unknown group.
        """
        page = _int_arg("page", 1)
        limit = _int_arg("limit", 20)
        sort = request.args.get("sort", "created_at")
        return jsonify(expenses=ledger.list_expenses(group_id, page, limit, sort))

    @app.get("/groups/<int:group_id>/balances")
    def balances(group_id):
        """GET /groups/<id>/balances: net balance per member.

        Returns ``{"balances": {user_id: {"name", "balance"}}}``; a positive
        balance means the member is owed money, negative means they owe.
        """
        return jsonify(balances=ledger.balances(group_id))

    @app.post("/groups/<int:group_id>/settlements")
    def settle(group_id):
        """POST /groups/<id>/settlements: record that one member paid another.

        Body: ``{"from": <user_id>, "to": <user_id>, "amount": number}``.
        Returns ``{"id": <settlement_id>}`` with 201, 400 if a field is missing or
        invalid, or 404 if the group does not exist.
        """
        data = request.get_json()
        if not isinstance(data, dict) or not all(k in data for k in ("from", "to", "amount")):
            return jsonify(error="from, to and amount are required"), 400
        settlement_id = ledger.record_settlement(
            group_id, data["from"], data["to"], data["amount"]
        )
        return jsonify(id=settlement_id), 201

    return app
