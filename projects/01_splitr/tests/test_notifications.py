"""Expense emails: sent in the background, failures isolated."""

from .helpers import count


def test_failed_notification_does_not_lose_expense(client, ids, group_id, monkeypatch):
    from splitr import notifier

    def boom(*args, **kwargs):
        raise ValueError("smtp down")

    monkeypatch.setattr(notifier, "send_email", boom)
    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90}
    )
    assert res.status_code == 201
    assert count("expenses") == 1
    assert count("shares") == 3


def test_expense_response_does_not_wait_for_emails(client, ids, group_id, monkeypatch):
    import threading

    from splitr import notifier

    release = threading.Event()
    sent = []

    def slow_send(to, subject, body):
        release.wait(2)  # a stuck mail provider
        sent.append(to)

    monkeypatch.setattr(notifier, "send_email", slow_send)

    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90}
    )
    assert res.status_code == 201
    assert sent == []  # response came back before any email was delivered

    release.set()
    assert notifier.wait_for_pending(timeout=5)
    assert sorted(sent) == ["alice@example.com", "bob@example.com", "carol@example.com"]


def test_one_bad_address_does_not_block_other_emails(client, monkeypatch):
    from splitr import notifier

    sent = []
    members = [
        {"id": "u1", "name": "alice", "email": "alice@example.com"},
        {"id": "u2", "name": "bob", "email": None},
        {"id": "u3", "name": "carol", "email": "carol@example.com"},
    ]

    def flaky(to, subject, body):
        if not to:
            raise ValueError("invalid recipient")
        sent.append(to)

    monkeypatch.setattr(notifier, "send_email", flaky)
    notifier.notify_expense(members, "alice", 30, "x", {"u1": 10, "u2": 10, "u3": 10})
    assert sent == ["alice@example.com", "carol@example.com"]


def test_queueing_failure_does_not_fail_the_expense(client, ids, group_id, monkeypatch):
    from splitr import notifier

    def broken(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(notifier, "notify_expense_async", broken)
    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90}
    )
    assert res.status_code == 201
    assert count("expenses") == 1
