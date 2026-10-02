"""Multi-step writes are all-or-nothing."""

from .helpers import count


def test_create_group_is_atomic(client, ids, monkeypatch):
    from splitr.services import users as users_service

    # Skip the up-front user check so an unknown member fails mid-transaction
    # (foreign key), after the group row has been inserted.
    monkeypatch.setattr(users_service, "require_users", lambda user_ids: None)
    res = client.post(
        "/groups", json={"name": "bad", "members": [ids["alice"], "no-such-user"]}
    )
    assert res.status_code == 500
    assert count("groups") == 0
    assert count("group_members") == 0


def test_add_expense_is_atomic(client, ids, group_id, monkeypatch):
    from splitr.services import expenses as expense_service

    # The second share can't be bound by sqlite, so it fails mid-transaction.
    monkeypatch.setattr(
        expense_service,
        "split_evenly",
        lambda amount, people: {ids["alice"]: 10, ids["bob"]: object()},
    )
    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 20}
    )
    assert res.status_code == 500
    assert count("expenses") == 0
    assert count("shares") == 0
