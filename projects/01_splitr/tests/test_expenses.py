"""Recording expenses and who they are split between."""

from .helpers import make_users, balances_by_name, shares_by_name


def test_expense_split_evenly(client, ids, group_id):
    res = client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 90, "description": "dinner"},
    )
    assert res.status_code == 201
    assert shares_by_name(res.get_json()["shares"], ids) == {"alice": 30, "bob": 30, "carol": 30}


def test_expense_split_among_subset(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 50, "split_among": [ids["alice"], ids["bob"]]},
    )
    assert balances_by_name(client, group_id) == {"alice": 25, "bob": -25, "carol": 0}


def test_expense_requires_amount(client, ids, group_id):
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"]})
    assert res.status_code == 400


def test_list_expenses(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 30, "description": "taxi"},
    )
    res = client.get(f"/groups/{group_id}/expenses")
    assert res.status_code == 200
    expenses = res.get_json()["expenses"]
    assert [e["paid_by"] for e in expenses] == [ids["alice"]]


def test_default_split_does_not_leak_between_groups(client):
    u = make_users(client, ["amy", "ann", "bea", "bob"])
    a = client.post(
        "/groups", json={"name": "A", "members": [u["amy"], u["ann"]]}
    ).get_json()["id"]
    b = client.post(
        "/groups", json={"name": "B", "members": [u["bob"], u["bea"]]}
    ).get_json()["id"]

    client.post(f"/groups/{a}/expenses", json={"paid_by": u["amy"], "amount": 10})
    res = client.post(f"/groups/{b}/expenses", json={"paid_by": u["bob"], "amount": 10})

    assert shares_by_name(res.get_json()["shares"], u) == {"bob": 5, "bea": 5}
    assert balances_by_name(client, a) == {"amy": 5, "ann": -5}
    assert balances_by_name(client, b) == {"bob": 5, "bea": -5}
