"""Splitting an amount into whole cents without losing or inventing any."""

from .helpers import balances_by_name


def test_split_evenly_distributes_remainder_cents():
    from splitr.services.expenses import split_evenly

    shares = split_evenly(10000, ["a", "b", "c"])  # 100.00 among three
    assert shares == {"a": 3334, "b": 3333, "c": 3333}
    assert sum(shares.values()) == 10000

    assert split_evenly(1, ["a", "b", "c"]) == {"a": 1, "b": 0, "c": 0}  # one cent
    assert split_evenly(9000, ["a", "b", "c"]) == {"a": 3000, "b": 3000, "c": 3000}


def test_uneven_split_balances_net_to_zero(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 100})
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["bob"], "amount": 10})
    assert round(sum(balances_by_name(client, group_id).values()), 2) == 0
