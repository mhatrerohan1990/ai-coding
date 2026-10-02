"""Plain helpers shared by the test modules (fixtures live in conftest.py)."""

NAMES = ["alice", "bob", "carol"]


def make_users(client, names):
    """Create users through the API; returns ``{name: user_id}``."""
    out = {}
    for n in names:
        res = client.post("/users", json={"name": n, "email": f"{n}@example.com"})
        assert res.status_code == 201
        out[n] = res.get_json()["id"]
    return out


def resolve(value, ids):
    """Replace user names (e.g. "alice") anywhere in a request body with their ids.

    Strings that are not a known name (like "ghost") are left alone, so they act
    as unknown ids.
    """
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, list):
        return [resolve(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, ids) for k, v in value.items()}
    return value


def balances_by_name(client, gid):
    res = client.get(f"/groups/{gid}/balances")
    assert res.status_code == 200
    return {b["name"]: b["balance"] for b in res.get_json()["balances"].values()}


def shares_by_name(shares, ids):
    by_id = {v: k for k, v in ids.items()}
    return {by_id[uid]: amount for uid, amount in shares.items()}


def count(table):
    from splitr.db import get_conn

    return get_conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def post_with_key(client, path, body, key="key-1"):
    return client.post(path, json=body, headers={"Idempotency-Key": key})


def sent_emails(monkeypatch):
    from splitr import notifier

    sent = []
    monkeypatch.setattr(notifier, "send_email", lambda to, s, b: sent.append(to))
    return sent
