"""Splitting an amount into whole cents without losing or inventing any."""

from .helpers import balances_by_name


def test_split_evenly_distributes_remainder_cents():
    from splitr.services.expenses import split_evenly

    shares = split_evenly(100, ["a", "b", "c"])
    assert shares == {"a": 33.34, "b": 33.33, "c": 33.33}
    assert round(sum(shares.values()), 2) == 100

    assert split_evenly(0.01, ["a", "b", "c"]) == {"a": 0.01, "b": 0.0, "c": 0.0}
    assert split_evenly(90, ["a", "b", "c"]) == {"a": 30, "b": 30, "c": 30}


def test_uneven_split_balances_net_to_zero(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 100})
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["bob"], "amount": 10})
    assert round(sum(balances_by_name(client, group_id).values()), 2) == 0
