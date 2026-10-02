"""User endpoints: create, fetch, update, and what changes (and does not) when a user does."""

import pytest

from .helpers import balances_by_name, count


def test_create_and_get_user(client):
    res = client.post("/users", json={"name": "dana", "email": "dana@example.com"})
    assert res.status_code == 201
    user_id = res.get_json()["id"]
    assert len(user_id) == 36  # uuid4 string
    got = client.get(f"/users/{user_id}")
    assert got.status_code == 200
    assert got.get_json() == {"id": user_id, "name": "dana", "email": "dana@example.com"}


def test_user_email_is_optional(client):
    res = client.post("/users", json={"name": "dana"})
    assert res.status_code == 201
    assert client.get(f"/users/{res.get_json()['id']}").get_json()["email"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": 5},
        {"name": "x", "email": 5},
        {"name": "x", "email": "no-at-sign"},
    ],
)
def test_create_user_validation(client, body):
    assert client.post("/users", json=body).status_code == 400
    assert count("users") == 0


def test_get_unknown_user_returns_404(client):
    assert client.get("/users/not-a-real-id").status_code == 404


def test_update_user_changes_email_and_name(client, ids):
    uid = ids["alice"]
    res = client.patch(f"/users/{uid}", json={"email": "new@example.com"})
    assert res.status_code == 200
    assert res.get_json() == {"id": uid, "name": "alice", "email": "new@example.com"}
    res = client.patch(f"/users/{uid}", json={"name": "alicia", "email": None})
    assert res.get_json() == {"id": uid, "name": "alicia", "email": None}


@pytest.mark.parametrize("body", [{}, {"unrelated": 1}, {"name": ""}, {"email": "bad"}])
def test_update_user_validation(client, ids, body):
    assert client.patch(f"/users/{ids['alice']}", json=body).status_code == 400
    assert client.get(f"/users/{ids['alice']}").get_json()["name"] == "alice"


def test_update_unknown_user_returns_404(client):
    assert client.patch("/users/nope", json={"name": "x"}).status_code == 404


def test_rename_and_email_change_apply_across_history(client, ids, group_id, monkeypatch):
    from splitr import notifier

    sent = []
    monkeypatch.setattr(notifier, "send_email", lambda to, s, b: sent.append(to))

    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    client.patch(f"/users/{ids['alice']}", json={"name": "alicia", "email": "new@example.com"})
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["bob"], "amount": 30})
    notifier.wait_for_pending(timeout=5)

    # History keeps pointing at the same person; only the label changed.
    assert balances_by_name(client, group_id) == {"alicia": 50, "bob": -10, "carol": -40}
    assert "new@example.com" in sent  # the second expense used the new address
