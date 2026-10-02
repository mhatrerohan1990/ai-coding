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


def test_record_settlement(client, group_id):
    res = client.post(
        f"/groups/{group_id}/settlements",
        json={"from": "bob", "to": "alice", "amount": 30},
    )
    assert res.status_code == 201
