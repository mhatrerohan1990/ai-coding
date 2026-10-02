"""Recording settlements and how they move balances."""

from .helpers import balances_by_name


def test_record_settlement(client, ids, group_id):
    res = client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 30},
    )
    assert res.status_code == 201
    # bob handed alice 30 with nothing owed, so alice now owes bob.
    assert balances_by_name(client, group_id) == {"alice": -30, "bob": 30, "carol": 0}


def test_settlement_pays_down_what_is_owed(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}

    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 30},
    )
    assert balances_by_name(client, group_id) == {"alice": 30, "bob": 0, "carol": -30}

    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["carol"], "to": ids["alice"], "amount": 30},
    )
    assert balances_by_name(client, group_id) == {"alice": 0, "bob": 0, "carol": 0}


def test_partial_settlement_leaves_the_remainder(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 10},
    )
    assert balances_by_name(client, group_id) == {"alice": 50, "bob": -20, "carol": -30}
