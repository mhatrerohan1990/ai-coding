"""Settle-up: the pure debt-simplification function and the endpoint."""

from .helpers import balances_by_name, count


def apply_payments(balances_cents, payments):
    """Apply (from, to, cents) payments to a copy of the balances."""
    after = dict(balances_cents)
    for debtor, creditor, cents in payments:
        after[debtor] += cents
        after[creditor] -= cents
    return after


def test_simplify_debts_single_debtor_single_creditor():
    from splitr.services.settle_up import simplify_debts

    assert simplify_debts({"alice": 6000, "bob": 0, "carol": -6000}) == [("carol", "alice", 6000)]


def test_simplify_debts_matches_largest_with_largest():
    from splitr.services.settle_up import simplify_debts

    # alice +40, bob +10, carol -30, dave -20
    payments = simplify_debts({"alice": 4000, "bob": 1000, "carol": -3000, "dave": -2000})
    assert payments == [
        ("carol", "alice", 3000),
        ("dave", "alice", 1000),
        ("dave", "bob", 1000),
    ]


def test_simplify_debts_nothing_to_do():
    from splitr.services.settle_up import simplify_debts

    assert simplify_debts({}) == []
    assert simplify_debts({"a": 0, "b": 0}) == []


def test_simplify_debts_is_deterministic():
    from splitr.services.settle_up import simplify_debts

    balances = {"a": 500, "b": 500, "c": -500, "d": -500}
    assert simplify_debts(balances) == simplify_debts(dict(balances))


def test_simplify_debts_settles_everyone_with_at_most_n_minus_1_payments():
    import random

    from splitr.services.settle_up import simplify_debts

    rng = random.Random(1234)
    for _ in range(300):
        n = rng.randint(2, 9)
        cents = [rng.randint(-50000, 50000) for _ in range(n - 1)]
        cents.append(-sum(cents))  # balances always net to zero
        balances = {f"u{i}": c for i, c in enumerate(cents)}

        payments = simplify_debts(balances)

        assert all(amount > 0 for _, _, amount in payments)
        assert all(d != c for d, c, _ in payments)
        assert len(payments) <= n - 1
        assert set(apply_payments(balances, payments).values()) <= {0}


def test_settle_up_endpoint_collapses_the_chain(client, ids, group_id):
    # alice pays 90 for all; bob pays 60 split with carol only:
    # alice +60, bob 0 (owed 30 by carol, owes 30 to alice), carol -60.
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["bob"], "amount": 60, "split_among": [ids["bob"], ids["carol"]]},
    )
    res = client.get(f"/groups/{group_id}/settle-up")
    assert res.status_code == 200
    assert res.get_json() == {
        "payments": [
            {
                "from": ids["carol"],
                "from_name": "carol",
                "to": ids["alice"],
                "to_name": "alice",
                "amount": 60,
            }
        ]
    }


def test_settle_up_splits_one_debtor_across_creditors(client, ids, group_id):
    # alice pays 90, bob pays 60, both split three ways: alice +40, bob +10, carol -50.
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["bob"], "amount": 60})
    payments = client.get(f"/groups/{group_id}/settle-up").get_json()["payments"]
    assert [(p["from_name"], p["to_name"], p["amount"]) for p in payments] == [
        ("carol", "alice", 40),
        ("carol", "bob", 10),
    ]


def test_settle_up_is_empty_for_a_fresh_or_settled_group(client, ids, group_id):
    assert client.get(f"/groups/{group_id}/settle-up").get_json() == {"payments": []}

    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    for p in client.get(f"/groups/{group_id}/settle-up").get_json()["payments"]:
        # Each suggestion can be posted back as a settlement unchanged.
        body = {"from": p["from"], "to": p["to"], "amount": p["amount"]}
        assert client.post(f"/groups/{group_id}/settlements", json=body).status_code == 201

    assert client.get(f"/groups/{group_id}/settle-up").get_json() == {"payments": []}
    assert set(balances_by_name(client, group_id).values()) == {0}


def test_settle_up_handles_uneven_cents(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 100})
    payments = client.get(f"/groups/{group_id}/settle-up").get_json()["payments"]
    # alice paid 100 and owes 33.34 herself; the other two owe 33.33 each.
    assert sorted((p["from_name"], p["amount"]) for p in payments) == [
        ("bob", 33.33),
        ("carol", 33.33),
    ]
    assert round(sum(p["amount"] for p in payments), 2) == 66.66


def test_settle_up_is_read_only(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    before = balances_by_name(client, group_id)
    client.get(f"/groups/{group_id}/settle-up")
    assert count("settlements") == 0
    assert balances_by_name(client, group_id) == before


def test_settle_up_unknown_group_returns_404(client):
    assert client.get("/groups/999/settle-up").status_code == 404
