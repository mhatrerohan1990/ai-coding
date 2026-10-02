"""Listing expenses: pagination, sorting and query-parameter validation."""

import pytest


def test_list_expenses_pagination(client, ids, group_id):
    for i in range(5):
        client.post(
            f"/groups/{group_id}/expenses",
            json={"paid_by": ids["alice"], "amount": 30, "description": f"e{i}"},
        )

    def page(n):
        res = client.get(f"/groups/{group_id}/expenses?page={n}&limit=2")
        return [e["description"] for e in res.get_json()["expenses"]]

    # Pages are 1-based and newest first; page 1 must not skip any rows.
    assert page(1) == ["e4", "e3"]
    assert page(2) == ["e2", "e1"]
    assert page(3) == ["e0"]
    assert page(4) == []


def test_list_expenses_default_page_returns_first_rows(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 30, "description": "only"},
    )
    res = client.get(f"/groups/{group_id}/expenses")
    assert [e["description"] for e in res.get_json()["expenses"]] == ["only"]


@pytest.mark.parametrize(
    "query",
    [
        "sort=nonsense",
        "sort=paid_by",
        "sort=(SELECT%20name%20FROM%20groups)",
        "sort=id;DROP%20TABLE%20expenses",
        "page=abc",
        "page=0",
        "page=-1",
        "limit=abc",
        "limit=0",
        "limit=-1",
        "limit=101",
    ],
)
def test_list_expenses_rejects_bad_query(client, group_id, query):
    res = client.get(f"/groups/{group_id}/expenses?{query}")
    assert res.status_code == 400


def test_list_expenses_sort_injection_does_not_touch_tables(client, group_id):
    client.get(f"/groups/{group_id}/expenses?sort=id;DROP%20TABLE%20expenses")
    assert client.get(f"/groups/{group_id}/expenses").status_code == 200


def test_list_expenses_sorts_by_allowed_column(client, ids, group_id):
    for amount in (10, 30, 20):
        client.post(
            f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": amount}
        )
    res = client.get(f"/groups/{group_id}/expenses?sort=amount")
    assert [e["amount"] for e in res.get_json()["expenses"]] == [30, 20, 10]


def test_list_expenses_ties_paginate_without_repeats(client, ids, group_id):
    for _ in range(5):
        client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 10})
    seen = []
    for page in (1, 2, 3):
        res = client.get(f"/groups/{group_id}/expenses?sort=amount&page={page}&limit=2")
        seen += [e["id"] for e in res.get_json()["expenses"]]
    assert sorted(seen) == [1, 2, 3, 4, 5]
