"""Input validation across groups, expenses and settlements: 400s, 404s and bad bodies."""

import pytest

from .helpers import make_users, resolve, count


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "members": ["alice"]},
        {"name": "x", "members": []},
        {"name": "x", "members": "alice"},
        {"name": "x", "members": [{"name": "alice"}]},
        {"name": "x", "members": [5]},
        {"name": "x", "members": ["alice", "alice"]},
        {"name": "x", "members": ["ghost"]},
        {"name": "x", "members": ["alice", "ghost"]},
    ],
)
def test_create_group_validation(client, ids, body):
    assert client.post("/groups", json=resolve(body, ids)).status_code == 400
    assert count("groups") == 0


@pytest.mark.parametrize(
    "body",
    [
        {"paid_by": "alice", "amount": -50},
        {"paid_by": "alice", "amount": 0},
        {"paid_by": "alice", "amount": "abc"},
        {"paid_by": "alice", "amount": True},
        {"paid_by": "alice", "amount": 10.005},
        {"paid_by": "ghost", "amount": 10},
        {"paid_by": ["alice"], "amount": 10},
        {"paid_by": "alice", "amount": 10, "split_among": ["ghost"]},
        {"paid_by": "alice", "amount": 10, "split_among": ["bob", "bob"]},
        {"paid_by": "alice", "amount": 10, "split_among": "bob"},
        {"paid_by": "alice", "amount": 10, "split_among": [["bob"]]},
        {"paid_by": "alice", "amount": 10, "description": 5},
    ],
)
def test_add_expense_validation(client, ids, group_id, body):
    res = client.post(f"/groups/{group_id}/expenses", json=resolve(body, ids))
    assert res.status_code == 400
    assert count("expenses") == 0


def test_payer_must_belong_to_the_group(client, ids):
    outsider = make_users(client, ["dave"])["dave"]
    gid = client.post(
        "/groups", json={"name": "g", "members": [ids["alice"], ids["bob"]]}
    ).get_json()["id"]
    res = client.post(f"/groups/{gid}/expenses", json={"paid_by": outsider, "amount": 10})
    assert res.status_code == 400
    res = client.post(
        f"/groups/{gid}/expenses",
        json={"paid_by": ids["alice"], "amount": 10, "split_among": [outsider]},
    )
    assert res.status_code == 400


def test_missing_group_returns_404(client):
    expense = {"paid_by": "alice", "amount": 5}
    settlement = {"from": "alice", "to": "bob", "amount": 5}
    assert client.post("/groups/999/expenses", json=expense).status_code == 404
    assert client.post("/groups/999/settlements", json=settlement).status_code == 404
    assert client.get("/groups/999/expenses").status_code == 404
    assert client.get("/groups/999/balances").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"from": "alice", "to": "alice", "amount": 5},
        {"from": "alice", "to": "ghost", "amount": 5},
        {"from": "ghost", "to": "alice", "amount": 5},
        {"from": ["alice"], "to": "bob", "amount": 5},
        {"from": "bob", "to": "alice", "amount": -5},
        {"from": "bob", "to": "alice", "amount": 0},
        {"from": "bob", "to": "alice", "amount": "5"},
    ],
)
def test_settlement_validation(client, ids, group_id, body):
    res = client.post(f"/groups/{group_id}/settlements", json=resolve(body, ids))
    assert res.status_code == 400
    assert count("settlements") == 0


@pytest.mark.parametrize(
    "path", ["/users", "/groups", "/groups/1/expenses", "/groups/1/settlements"]
)
def test_non_object_json_body_returns_400(client, group_id, path):
    assert client.post(path, json=["not", "an", "object"]).status_code == 400
    assert client.post(path, json="name members").status_code == 400
