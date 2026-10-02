from flask import Flask, jsonify, request

from . import db, ledger


def create_app(db_path="splitr.db"):
    app = Flask(__name__)
    db.init(db_path)

    @app.post("/groups")
    def create_group():
        data = request.get_json()
        if not data or "name" not in data or "members" not in data:
            return jsonify(error="name and members are required"), 400
        group_id = ledger.create_group(data["name"], data["members"])
        return jsonify(id=group_id), 201

    @app.post("/groups/<int:group_id>/expenses")
    def add_expense(group_id):
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
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
        sort = request.args.get("sort", "created_at")
        return jsonify(expenses=ledger.list_expenses(group_id, page, limit, sort))

    @app.get("/groups/<int:group_id>/balances")
    def balances(group_id):
        return jsonify(balances=ledger.balances(group_id))

    @app.post("/groups/<int:group_id>/settlements")
    def settle(group_id):
        data = request.get_json()
        if not data or not all(k in data for k in ("from", "to", "amount")):
            return jsonify(error="from, to and amount are required"), 400
        settlement_id = ledger.record_settlement(
            group_id, data["from"], data["to"], data["amount"]
        )
        return jsonify(id=settlement_id), 201

    return app
