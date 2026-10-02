import pytest

from splitr.app import create_app

MEMBERS = [
    {"name": "alice", "email": "alice@example.com"},
    {"name": "bob", "email": "bob@example.com"},
    {"name": "carol", "email": "carol@example.com"},
]


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    return app.test_client()


@pytest.fixture
def group_id(client):
    res = client.post("/groups", json={"name": "trip", "members": MEMBERS})
    return res.get_json()["id"]


def test_create_group(client):
    res = client.post("/groups", json={"name": "flat", "members": MEMBERS})
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_create_group_requires_members(client):
    res = client.post("/groups", json={"name": "flat"})
    assert res.status_code == 400


def test_expense_split_evenly(client, group_id):
    res = client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": "alice", "amount": 90, "description": "dinner"},
    )
    assert res.status_code == 201
    assert res.get_json()["shares"] == {"alice": 30, "bob": 30, "carol": 30}


def test_balances_after_expense(client, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": "alice", "amount": 90, "description": "dinner"},
    )
    res = client.get(f"/groups/{group_id}/balances")
    assert res.status_code == 200
    assert res.get_json()["balances"] == {"alice": 60, "bob": -30, "carol": -30}


def test_expense_split_among_subset(client, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": "alice", "amount": 50, "split_among": ["alice", "bob"]},
    )
    res = client.get(f"/groups/{group_id}/balances")
    assert res.get_json()["balances"] == {"alice": 25, "bob": -25, "carol": 0}


def test_expense_requires_amount(client, group_id):
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": "alice"})
    assert res.status_code == 400


def test_list_expenses(client, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": "alice", "amount": 30, "description": "taxi"},
    )
    res = client.get(f"/groups/{group_id}/expenses")
    assert res.status_code == 200
    assert isinstance(res.get_json()["expenses"], list)


def test_list_expenses_pagination(client, group_id):
    for i in range(5):
        client.post(
            f"/groups/{group_id}/expenses",
            json={"paid_by": "alice", "amount": 30, "description": f"e{i}"},
        )

    def page(n):
        res = client.get(f"/groups/{group_id}/expenses?page={n}&limit=2")
        return [e["description"] for e in res.get_json()["expenses"]]

    # Pages are 1-based and newest first; page 1 must not skip any rows.
    assert page(1) == ["e4", "e3"]
    assert page(2) == ["e2", "e1"]
    assert page(3) == ["e0"]
    assert page(4) == []


def test_list_expenses_default_page_returns_first_rows(client, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": "alice", "amount": 30, "description": "only"},
    )
    res = client.get(f"/groups/{group_id}/expenses")
    assert [e["description"] for e in res.get_json()["expenses"]] == ["only"]


def test_record_settlement(client, group_id):
    res = client.post(
        f"/groups/{group_id}/settlements",
        json={"from": "bob", "to": "alice", "amount": 30},
    )
    assert res.status_code == 201


def _count(table):
    from splitr.db import get_conn

    return get_conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_create_group_is_atomic(client):
    # Second member has no "name": the insert fails after the group row exists.
    res = client.post(
        "/groups",
        json={"name": "bad", "members": [{"name": "alice"}, {"email": "x@y.com"}]},
    )
    assert res.status_code == 500
    assert _count("groups") == 0
    assert _count("members") == 0


def test_add_expense_is_atomic(client, group_id, monkeypatch):
    from splitr import ledger

    # The second share can't be bound by sqlite, so it fails mid-transaction.
    monkeypatch.setattr(
        ledger, "split_evenly", lambda amount, people: {"alice": 10, "bob": object()}
    )
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": "alice", "amount": 20})
    assert res.status_code == 500
    assert _count("expenses") == 0
    assert _count("shares") == 0


def test_failed_notification_does_not_lose_expense(client, group_id, monkeypatch):
    from splitr import notifier

    def boom(*args, **kwargs):
        raise ValueError("smtp down")

    monkeypatch.setattr(notifier, "send_email", boom)
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": "alice", "amount": 90})
    assert res.status_code == 201
    assert _count("expenses") == 1
    assert _count("shares") == 3
