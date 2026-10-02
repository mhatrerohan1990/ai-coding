import sqlite3

import pytest

from splitr.app import create_app

NAMES = ["alice", "bob", "carol"]


@pytest.fixture(autouse=True)
def drain_notifications():
    """Emails are sent in the background; finish them so tests don't bleed into each other."""
    from splitr import notifier

    notifier.wait_for_pending(timeout=30)
    yield
    notifier.wait_for_pending(timeout=30)


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    return app.test_client()


def make_users(client, names):
    """Create users through the API; returns ``{name: user_id}``."""
    out = {}
    for n in names:
        res = client.post("/users", json={"name": n, "email": f"{n}@example.com"})
        assert res.status_code == 201
        out[n] = res.get_json()["id"]
    return out


@pytest.fixture
def ids(client):
    """``{"alice": <uuid>, "bob": <uuid>, "carol": <uuid>}``"""
    return make_users(client, NAMES)


@pytest.fixture
def group_id(client, ids):
    res = client.post("/groups", json={"name": "trip", "members": list(ids.values())})
    return res.get_json()["id"]


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


def _count(table):
    from splitr.db import get_conn

    return get_conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- users ---------------------------------------------------------------


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
    assert _count("users") == 0


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


def test_same_user_can_be_in_several_groups(client, ids):
    g1 = client.post("/groups", json={"name": "one", "members": [ids["alice"], ids["bob"]]})
    g2 = client.post("/groups", json={"name": "two", "members": [ids["alice"], ids["carol"]]})
    g1, g2 = g1.get_json()["id"], g2.get_json()["id"]

    client.post(f"/groups/{g1}/expenses", json={"paid_by": ids["alice"], "amount": 10})
    client.post(f"/groups/{g2}/expenses", json={"paid_by": ids["carol"], "amount": 20})

    assert balances_by_name(client, g1) == {"alice": 5, "bob": -5}
    assert balances_by_name(client, g2) == {"alice": -10, "carol": 10}


# --- groups ----------------------------------------------------------------


def test_create_group(client, ids):
    res = client.post("/groups", json={"name": "flat", "members": list(ids.values())})
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_create_group_requires_members(client):
    res = client.post("/groups", json={"name": "flat"})
    assert res.status_code == 400


# --- expenses and balances -------------------------------------------------


def test_expense_split_evenly(client, ids, group_id):
    res = client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 90, "description": "dinner"},
    )
    assert res.status_code == 201
    assert shares_by_name(res.get_json()["shares"], ids) == {"alice": 30, "bob": 30, "carol": 30}


def test_balances_after_expense(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 90, "description": "dinner"},
    )
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}


def test_balances_are_keyed_by_user_id(client, ids, group_id):
    res = client.get(f"/groups/{group_id}/balances")
    assert res.get_json()["balances"] == {
        ids[n]: {"name": n, "balance": 0} for n in NAMES
    }


def test_expense_split_among_subset(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 50, "split_among": [ids["alice"], ids["bob"]]},
    )
    assert balances_by_name(client, group_id) == {"alice": 25, "bob": -25, "carol": 0}


def test_expense_requires_amount(client, ids, group_id):
    res = client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"]})
    assert res.status_code == 400


def test_list_expenses(client, ids, group_id):
    client.post(
        f"/groups/{group_id}/expenses",
        json={"paid_by": ids["alice"], "amount": 30, "description": "taxi"},
    )
    res = client.get(f"/groups/{group_id}/expenses")
    assert res.status_code == 200
    expenses = res.get_json()["expenses"]
    assert [e["paid_by"] for e in expenses] == [ids["alice"]]


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


def test_record_settlement(client, ids, group_id):
    res = client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 30},
    )
    assert res.status_code == 201
    assert balances_by_name(client, group_id) == {"alice": 30, "bob": -30, "carol": 0}


# --- atomicity ---------------------------------------------------------------


def test_create_group_is_atomic(client, ids, monkeypatch):
    from splitr import ledger

    # Skip the up-front user check so an unknown member fails mid-transaction
    # (foreign key), after the group row has been inserted.
    monkeypatch.setattr(ledger, "_require_users", lambda user_ids: None)
    res = client.post(
        "/groups", json={"name": "bad", "members": [ids["alice"], "no-such-user"]}
    )
    assert res.status_code == 500
    assert _count("groups") == 0
    assert _count("group_members") == 0


def test_add_expense_is_atomic(client, ids, group_id, monkeypatch):
    from splitr import ledger

    # The second share can't be bound by sqlite, so it fails mid-transaction.
    monkeypatch.setattr(
        ledger,
        "split_evenly",
        lambda amount, people: {ids["alice"]: 10, ids["bob"]: object()},
    )
    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 20}
    )
    assert res.status_code == 500
    assert _count("expenses") == 0
    assert _count("shares") == 0


def test_failed_notification_does_not_lose_expense(client, ids, group_id, monkeypatch):
    from splitr import notifier

    def boom(*args, **kwargs):
        raise ValueError("smtp down")

    monkeypatch.setattr(notifier, "send_email", boom)
    res = client.post(
        f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90}
    )
    assert res.status_code == 201
    assert _count("expenses") == 1
    assert _count("shares") == 3


# --- splitting ---------------------------------------------------------------


def test_default_split_does_not_leak_between_groups(client):
    u = make_users(client, ["amy", "ann", "bea", "bob"])
    a = client.post(
        "/groups", json={"name": "A", "members": [u["amy"], u["ann"]]}
    ).get_json()["id"]
    b = client.post(
        "/groups", json={"name": "B", "members": [u["bob"], u["bea"]]}
    ).get_json()["id"]

    client.post(f"/groups/{a}/expenses", json={"paid_by": u["amy"], "amount": 10})
    res = client.post(f"/groups/{b}/expenses", json={"paid_by": u["bob"], "amount": 10})

    assert shares_by_name(res.get_json()["shares"], u) == {"bob": 5, "bea": 5}
    assert balances_by_name(client, a) == {"amy": 5, "ann": -5}
    assert balances_by_name(client, b) == {"bob": 5, "bea": -5}


def test_split_evenly_distributes_remainder_cents():
    from splitr.ledger import split_evenly

    shares = split_evenly(100, ["a", "b", "c"])
    assert shares == {"a": 33.34, "b": 33.33, "c": 33.33}
    assert round(sum(shares.values()), 2) == 100

    assert split_evenly(0.01, ["a", "b", "c"]) == {"a": 0.01, "b": 0.0, "c": 0.0}
    assert split_evenly(90, ["a", "b", "c"]) == {"a": 30, "b": 30, "c": 30}


def test_uneven_split_balances_net_to_zero(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 100})
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["bob"], "amount": 10})
    assert round(sum(balances_by_name(client, group_id).values()), 2) == 0


# --- validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "members": ["alice"]},
        {"name": "x", "members": []},
        {"name": "x", "members": "alice"},
        {"name": "x", "members": [{"name": "alice"}]},
        {"name": "x", "members": [5]},
        {"name": "x", "members": ["alice", "alice"]},
        {"name": "x", "members": ["ghost"]},
        {"name": "x", "members": ["alice", "ghost"]},
    ],
)
def test_create_group_validation(client, ids, body):
    assert client.post("/groups", json=resolve(body, ids)).status_code == 400
    assert _count("groups") == 0


@pytest.mark.parametrize(
    "body",
    [
        {"paid_by": "alice", "amount": -50},
        {"paid_by": "alice", "amount": 0},
        {"paid_by": "alice", "amount": "abc"},
        {"paid_by": "alice", "amount": True},
        {"paid_by": "alice", "amount": 10.005},
        {"paid_by": "ghost", "amount": 10},
        {"paid_by": ["alice"], "amount": 10},
        {"paid_by": "alice", "amount": 10, "split_among": ["ghost"]},
        {"paid_by": "alice", "amount": 10, "split_among": ["bob", "bob"]},
        {"paid_by": "alice", "amount": 10, "split_among": "bob"},
        {"paid_by": "alice", "amount": 10, "split_among": [["bob"]]},
        {"paid_by": "alice", "amount": 10, "description": 5},
    ],
)
def test_add_expense_validation(client, ids, group_id, body):
    res = client.post(f"/groups/{group_id}/expenses", json=resolve(body, ids))
    assert res.status_code == 400
    assert _count("expenses") == 0


def test_payer_must_belong_to_the_group(client, ids):
    outsider = make_users(client, ["dave"])["dave"]
    gid = client.post(
        "/groups", json={"name": "g", "members": [ids["alice"], ids["bob"]]}
    ).get_json()["id"]
    res = client.post(f"/groups/{gid}/expenses", json={"paid_by": outsider, "amount": 10})
    assert res.status_code == 400
    res = client.post(
        f"/groups/{gid}/expenses",
        json={"paid_by": ids["alice"], "amount": 10, "split_among": [outsider]},
    )
    assert res.status_code == 400


def test_missing_group_returns_404(client):
    expense = {"paid_by": "alice", "amount": 5}
    settlement = {"from": "alice", "to": "bob", "amount": 5}
    assert client.post("/groups/999/expenses", json=expense).status_code == 404
    assert client.post("/groups/999/settlements", json=settlement).status_code == 404
    assert client.get("/groups/999/expenses").status_code == 404
    assert client.get("/groups/999/balances").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"from": "alice", "to": "alice", "amount": 5},
        {"from": "alice", "to": "ghost", "amount": 5},
        {"from": "ghost", "to": "alice", "amount": 5},
        {"from": ["alice"], "to": "bob", "amount": 5},
        {"from": "bob", "to": "alice", "amount": -5},
        {"from": "bob", "to": "alice", "amount": 0},
        {"from": "bob", "to": "alice", "amount": "5"},
    ],
)
def test_settlement_validation(client, ids, group_id, body):
    res = client.post(f"/groups/{group_id}/settlements", json=resolve(body, ids))
    assert res.status_code == 400
    assert _count("settlements") == 0


@pytest.mark.parametrize(
    "path", ["/users", "/groups", "/groups/1/expenses", "/groups/1/settlements"]
)
def test_non_object_json_body_returns_400(client, group_id, path):
    assert client.post(path, json=["not", "an", "object"]).status_code == 400
    assert client.post(path, json="name members").status_code == 400


# --- listing -----------------------------------------------------------------


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


# --- schema -----------------------------------------------------------------


def test_foreign_keys_are_enforced(client, group_id):
    from splitr.db import get_conn

    with pytest.raises(sqlite3.IntegrityError):
        get_conn().execute(
            "INSERT INTO expenses (group_id, paid_by, amount, description, created_at) "
            "VALUES (?, 'not-a-member', 1, '', 'now')",
            (group_id,),
        )


def test_old_schema_database_is_refused(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT);")
    conn.close()
    with pytest.raises(RuntimeError, match="old schema"):
        create_app(str(path))


# --- concurrency ---------------------------------------------------------------


def test_threads_do_not_share_transactions(client, ids, group_id):
    """One request's rollback must not discard another request's pending writes."""
    import threading

    from splitr.db import get_conn

    a_inserted, b_rolled_back = threading.Event(), threading.Event()
    errors = []

    def writer_a():
        try:
            conn = get_conn()
            conn.execute(
                "INSERT INTO settlements "
                "(group_id, from_user_id, to_user_id, amount, created_at) "
                "VALUES (?, ?, ?, 5, 'now')",
                (group_id, ids["bob"], ids["alice"]),
            )
            a_inserted.set()
            assert b_rolled_back.wait(5)
            conn.commit()
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    def failing_b():
        try:
            assert a_inserted.wait(5)
            try:
                with get_conn():
                    raise RuntimeError("request B fails")
            except RuntimeError:
                pass
            b_rolled_back.set()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer_a), threading.Thread(target=failing_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert _count("settlements") == 1


def test_concurrent_requests_stay_consistent(tmp_path):
    """Parallel writers plus a reader: no errors, nothing lost, balances always net to 0."""
    import threading

    from splitr import ledger

    app = create_app(str(tmp_path / "concurrent.db"))
    user_ids = [ledger.create_user(n, f"{n}@example.com") for n in NAMES]
    gid = ledger.create_group("g", user_ids)
    writers, per_writer = 6, 8
    errors, sums = [], []
    done = threading.Event()

    def writer(n):
        try:
            for i in range(per_writer):
                payer = user_ids[(n + i) % 3]
                with app.app_context():
                    ledger.add_expense(gid, payer, 10 + i)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            while not done.is_set():
                with app.app_context():
                    balances = ledger.balances(gid)
                    sums.append(round(sum(b["balance"] for b in balances.values()), 2))
        except Exception as e:
            errors.append(e)

    r = threading.Thread(target=reader)
    ws = [threading.Thread(target=writer, args=(n,)) for n in range(writers)]
    r.start()
    for t in ws:
        t.start()
    for t in ws:
        t.join()
    done.set()
    r.join()

    assert not errors
    assert _count("expenses") == writers * per_writer
    assert _count("shares") == writers * per_writer * 3
    assert sums and all(s == 0 for s in sums)


# --- notifications -------------------------------------------------------------


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
    assert _count("expenses") == 1
