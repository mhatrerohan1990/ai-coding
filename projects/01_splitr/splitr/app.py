from flask import Flask, jsonify, request

from . import db, ledger


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

    @app.post("/groups")
    def create_group():
        """POST /groups: create a group with its members.

        Body: ``{"name": str, "members": [{"name": str, "email": str}]}``.
        Returns ``{"id": <group_id>}`` with 201, or 400 if name/members missing.
        """
        data = request.get_json()
        if not data or "name" not in data or "members" not in data:
            return jsonify(error="name and members are required"), 400
        group_id = ledger.create_group(data["name"], data["members"])
        return jsonify(id=group_id), 201

    @app.post("/groups/<int:group_id>/expenses")
    def add_expense(group_id):
        """POST /groups/<id>/expenses: log an expense and split it.

        Body: ``{"paid_by", "amount", "description"?, "split_among"?}``.
        Only those known keys are forwarded to ``ledger.add_expense``. Returns
        ``{"id": <expense_id>, "shares": {member: amount}}`` with 201, or 400 if
        paid_by/amount are missing.
        """
        data = request.get_json()
        if not data or "paid_by" not in data or "amount" not in data:
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

        Query params: ``page`` (default 1), ``limit`` (default 20) and ``sort``
        (column name, default ``created_at``). Returns ``{"expenses": [...]}``.
        """
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
        sort = request.args.get("sort", "created_at")
        return jsonify(expenses=ledger.list_expenses(group_id, page, limit, sort))

    @app.get("/groups/<int:group_id>/balances")
    def balances(group_id):
        """GET /groups/<id>/balances: net balance per member.

        Returns ``{"balances": {name: amount}}``; positive means the member is
        owed money, negative means they owe.
        """
        return jsonify(balances=ledger.balances(group_id))

    @app.post("/groups/<int:group_id>/settlements")
    def settle(group_id):
        """POST /groups/<id>/settlements: record that one member paid another.

        Body: ``{"from": str, "to": str, "amount": number}``. Returns
        ``{"id": <settlement_id>}`` with 201, or 400 if any field is missing.
        """
        data = request.get_json()
        if not data or not all(k in data for k in ("from", "to", "amount")):
            return jsonify(error="from, to and amount are required"), 400
        settlement_id = ledger.record_settlement(
            group_id, data["from"], data["to"], data["amount"]
        )
        return jsonify(id=settlement_id), 201

    return app
