"""Timestamps are timezone-aware UTC."""

import pytest


@pytest.fixture
def india_timezone(monkeypatch):
    """Run the process in UTC+5:30 so naive local timestamps cannot look like UTC."""
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("tzset is not available on this platform")
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _assert_utc_now(text):
    from datetime import datetime, timedelta, timezone

    stamp = datetime.fromisoformat(text)
    assert stamp.tzinfo is not None, f"{text!r} has no timezone offset"
    assert stamp.utcoffset() == timedelta(0), f"{text!r} is not UTC"
    assert abs(datetime.now(timezone.utc) - stamp) < timedelta(seconds=30)


def test_expense_timestamps_are_timezone_aware_utc(client, ids, group_id, india_timezone):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 30})
    created = client.get(f"/groups/{group_id}/expenses").get_json()["expenses"][0]["created_at"]
    _assert_utc_now(created)
    assert created.endswith("+00:00")


def test_settlement_timestamps_are_timezone_aware_utc(client, ids, group_id, india_timezone):
    from splitr.db import get_conn

    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 5},
    )
    created = get_conn().execute("SELECT created_at FROM settlements").fetchone()[0]
    _assert_utc_now(created)


def test_timestamps_sort_chronologically(client, ids, group_id, monkeypatch):
    from splitr import clock

    times = iter(
        [
            "2026-03-08T06:59:59.000000+00:00",
            "2026-03-08T07:00:00.000000+00:00",  # a US daylight-saving jump happens here
            "2026-03-08T07:00:00.000001+00:00",
        ]
    )
    monkeypatch.setattr(clock, "utc_now_iso", lambda: next(times))
    for i in range(3):
        client.post(
            f"/groups/{group_id}/expenses",
            json={"paid_by": ids["alice"], "amount": 10, "description": f"e{i}"},
        )
    res = client.get(f"/groups/{group_id}/expenses?sort=created_at")
    assert [e["description"] for e in res.get_json()["expenses"]] == ["e2", "e1", "e0"]
