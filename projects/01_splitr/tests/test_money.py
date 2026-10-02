"""Money is whole cents end to end: parsing, splitting, storage and exact totals."""

import random
import sqlite3

import pytest

from splitr import money
from splitr.errors import ValidationError

from .helpers import count


@pytest.mark.parametrize(
    "amount, cents",
    [
        (1, 100),
        (30, 3000),
        (33.34, 3334),
        (19.99, 1999),
        (0.01, 1),
        (0.1 + 0.2, 30),  # 0.30000000000000004 as a float
        (1.1 * 3, 330),  # 3.3000000000000003
        (money.MAX_AMOUNT, money.MAX_AMOUNT * 100),
    ],
)
def test_parse_amount_returns_exact_cents(amount, cents):
    result = money.parse_amount(amount)
    assert result == cents
    assert isinstance(result, int)


@pytest.mark.parametrize(
    "amount",
    [0, -1, -0.01, True, False, "5", None, [5], float("nan"), float("inf"), 1.005, 0.001,
     money.MAX_AMOUNT + 1, 1e30],
)
def test_parse_amount_rejects_bad_values(amount):
    with pytest.raises(ValidationError):
        money.parse_amount(amount)


def test_to_amount_round_trips_every_cent_value():
    assert money.to_amount(3334) == 33.34
    assert money.to_amount(6000) == 60.0
    for cents in range(1, 100_000, 7):
        assert money.parse_amount(money.to_amount(cents)) == cents


def test_split_evenly_is_exact_for_any_total_and_group_size():
    from splitr.services.expenses import split_evenly

    rng = random.Random(7)
    for _ in range(500):
        total = rng.randint(1, 10**9)
        people = [f"u{i}" for i in range(rng.randint(1, 12))]
        shares = split_evenly(total, people)
        assert all(isinstance(v, int) for v in shares.values())
        assert sum(shares.values()) == total  # not a cent lost or invented
        assert max(shares.values()) - min(shares.values()) <= 1  # as even as possible


def test_amounts_are_stored_as_integer_cents(client, ids, group_id):
    from splitr.db import get_conn

    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 19.99})
    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 6.5},
    )
    conn = get_conn()
    expense = conn.execute("SELECT amount_cents, typeof(amount_cents) FROM expenses").fetchone()
    shares = conn.execute("SELECT amount_cents, typeof(amount_cents) FROM shares").fetchall()
    settlement = conn.execute("SELECT amount_cents, typeof(amount_cents) FROM settlements").fetchone()
    assert tuple(expense) == (1999, "integer")
    assert sorted(tuple(r) for r in shares) == [(666, "integer"), (666, "integer"), (667, "integer")]
    assert tuple(settlement) == (650, "integer")


def test_api_still_speaks_decimal_amounts(client, ids, group_id):
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 19.99})
    assert sorted(res.get_json()["shares"].values()) == [6.66, 6.66, 6.67]
    listed = client.get(f"/groups/{group_id}/expenses").get_json()["expenses"]
    assert listed[0]["amount"] == 19.99


def test_many_small_amounts_add_up_exactly(client, ids, group_id, monkeypatch):
    """300 expenses of 0.10 split three ways: floats would drift, cents cannot."""
    from splitr import notifier
    from splitr.services import balances as balance_service
    from splitr.services import expenses as expense_service

    monkeypatch.setattr(notifier, "send_email", lambda *a: None)
    with client.application.app_context():
        for _ in range(300):
            expense_service.add_expense(group_id, ids["alice"], 0.10)
        balances = {b.name: b.balance_cents for b in balance_service.get_balances(group_id)}

    # each 10 cents splits 4 / 3 / 3 (the odd cent goes to the first member)
    assert balances == {"alice": 300 * (10 - 4), "bob": -300 * 3, "carol": -300 * 3}
    assert sum(balances.values()) == 0


def test_every_expense_equals_the_sum_of_its_shares(client, ids, group_id, monkeypatch):
    from splitr import notifier
    from splitr.db import get_conn

    monkeypatch.setattr(notifier, "send_email", lambda *a: None)
    rng = random.Random(3)
    names = list(ids)
    for _ in range(60):
        group = rng.sample(names, rng.randint(1, 3))
        client.post(
            f"/groups/{group_id}/expenses",
            json={
                "paid_by": ids[rng.choice(names)],
                "amount": rng.randint(1, 500000) / 100,
                "split_among": [ids[n] for n in group],
            },
        )
    mismatched = get_conn().execute(
        "SELECT COUNT(*) FROM expenses e WHERE e.amount_cents != "
        "(SELECT SUM(amount_cents) FROM shares WHERE expense_id = e.id)"
    ).fetchone()[0]
    assert count("expenses") == 60
    assert mismatched == 0


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO expenses (group_id, paid_by, amount_cents, created_at) VALUES ({g}, '{u}', 0, 'now')",
        "INSERT INTO expenses (group_id, paid_by, amount_cents, created_at) VALUES ({g}, '{u}', -5, 'now')",
        "INSERT INTO settlements (group_id, from_user_id, to_user_id, amount_cents, created_at) "
        "VALUES ({g}, '{u}', '{u2}', 0, 'now')",
    ],
)
def test_the_database_itself_rejects_non_positive_money(client, ids, group_id, sql):
    from splitr.db import get_conn

    statement = sql.format(g=group_id, u=ids["alice"], u2=ids["bob"])
    with pytest.raises(sqlite3.IntegrityError):
        get_conn().execute(statement)


def test_a_negative_share_is_rejected_by_the_database(client, ids, group_id):
    from splitr.db import get_conn

    expense = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 5}
    ).get_json()["id"]
    with pytest.raises(sqlite3.IntegrityError):
        get_conn().execute(
            "INSERT INTO shares (expense_id, user_id, amount_cents) VALUES (?, 'x', -1)", (expense,)
        )
