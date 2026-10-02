"""Net balances per member."""

from .helpers import NAMES, balances_by_name


def test_balances_after_expense(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 90, "description": "dinner"},
    )
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}


def test_balances_are_keyed_by_user_id(client, ids, group_id):
    res = client.get(f"/groups/{group_id}/balances")
    assert res.get_json()["balances"] == {
        ids[n]: {"name": n, "balance": 0} for n in NAMES
    }
