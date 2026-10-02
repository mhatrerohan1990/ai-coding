"""Idempotency-Key handling on POST endpoints."""

import pytest

from .helpers import balances_by_name, count, post_with_key, sent_emails


def test_repeating_an_expense_with_the_same_key_applies_it_once(client, ids, group_id, monkeypatch):
    from splitr import notifier

    sent = sent_emails(monkeypatch)
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 90, "description": "dinner"}

    first = post_with_key(client, path, body)
    second = post_with_key(client, path, body)
    notifier.wait_for_pending(timeout=5)

    assert first.status_code == second.status_code == 201
    assert first.get_json() == second.get_json()  # same expense id and shares
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert count("expenses") == 1
    assert count("shares") == 3
    assert len(sent) == 3  # one email per member, not six
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}


def test_retry_with_reordered_json_keys_is_still_a_replay(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    first = post_with_key(client, path, {"paid_by": ids["alice"], "amount": 30})
    second = post_with_key(client, path, {"amount": 30, "paid_by": ids["alice"]})
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.get_json() == second.get_json()
    assert count("expenses") == 1


def test_without_a_key_a_retry_is_not_deduplicated(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 30}
    assert client.post(path, json=body).get_json()["id"] != client.post(path, json=body).get_json()["id"]
    assert count("expenses") == 2


def test_a_different_key_is_a_new_request(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 30}
    a = post_with_key(client, path, body, key="a")
    b = post_with_key(client, path, body, key="b")
    assert a.get_json()["id"] != b.get_json()["id"]
    assert count("expenses") == 2


def test_reusing_a_key_for_a_different_request_is_a_conflict(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    post_with_key(client, path, {"paid_by": ids["alice"], "amount": 30})

    changed = post_with_key(client, path, {"paid_by": ids["alice"], "amount": 99})
    assert changed.status_code == 409
    assert "different request" in changed.get_json()["error"]

    other_endpoint = post_with_key(client, "/users", {"name": "dana"})
    assert other_endpoint.status_code == 409
    assert count("expenses") == 1
    assert count("users") == 3  # the fixture's three; dana was not created


def test_every_post_endpoint_is_idempotent(client, ids, group_id):
    for path, body, table in [
        ("/users", {"name": "dana"}, "users"),
        ("/groups", {"name": "g2", "members": [ids["alice"]]}, "groups"),
        (
            f"/groups/{group_id}/settlements",
            {"from": ids["bob"], "to": ids["alice"], "amount": 5},
            "settlements",
        ),
    ]:
        before = count(table)
        first = post_with_key(client, path, body, key=f"key-{table}")
        second = post_with_key(client, path, body, key=f"key-{table}")
        assert first.status_code == second.status_code == 201
        assert first.get_json() == second.get_json()
        assert second.headers["Idempotent-Replayed"] == "true"
        assert count(table) == before + 1


def test_a_failed_request_is_not_cached(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    bad = post_with_key(client, path, {"paid_by": ids["alice"], "amount": -5})
    assert bad.status_code == 400
    assert count("idempotency_keys") == 0  # the key was released

    good = post_with_key(client, path, {"paid_by": ids["alice"], "amount": 5})
    assert good.status_code == 201
    assert "Idempotent-Replayed" not in good.headers


def test_a_crash_midway_rolls_back_the_key_and_the_work(client, ids, group_id, monkeypatch):
    from splitr.services import expenses as expense_service

    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 20}
    with monkeypatch.context() as patched:
        patched.setattr(
            expense_service,
            "split_evenly",
            lambda amount, people: {ids["alice"]: 10, ids["bob"]: object()},
        )
        assert post_with_key(client, path, body).status_code == 500
    assert count("expenses") == 0
    assert count("shares") == 0
    assert count("idempotency_keys") == 0

    retry = post_with_key(client, path, body)  # same key, same body, now healthy
    assert retry.status_code == 201
    assert count("expenses") == 1


def test_simultaneous_duplicates_are_applied_once(client, ids, group_id):
    import threading

    app = client.application
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 40}
    workers = 8
    barrier = threading.Barrier(workers)
    results = []

    def send():
        thread_client = app.test_client()
        barrier.wait()
        results.append(post_with_key(thread_client, path, body, key="race"))

    threads = [threading.Thread(target=send) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert [r.status_code for r in results] == [201] * workers
    assert len({r.get_json()["id"] for r in results}) == 1
    assert sum("Idempotent-Replayed" in r.headers for r in results) == workers - 1
    assert count("expenses") == 1
    assert count("shares") == 3


@pytest.mark.parametrize("key", ["", "  padded ", "x" * 256])
def test_bad_idempotency_keys_are_rejected(client, key):
    res = post_with_key(client, "/users", {"name": "dana"}, key=key)
    assert res.status_code == 400
    assert count("users") == 0


def test_expired_keys_are_forgotten(client, ids, group_id):
    from splitr.db import get_conn

    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 30}
    post_with_key(client, path, body, key="old")
    with get_conn() as conn:  # age the key past its time-to-live
        conn.execute(
            "UPDATE idempotency_keys SET created_at = '2000-01-01T00:00:00.000000+00:00'"
        )

    again = post_with_key(client, path, body, key="old")
    assert again.status_code == 201
    assert "Idempotent-Replayed" not in again.headers
    assert count("expenses") == 2
    assert count("idempotency_keys") == 1  # the stale row was purged, a fresh one stored
