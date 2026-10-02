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
    # bob handed alice 30 with nothing owed, so alice now owes bob.
    assert balances_by_name(client, group_id) == {"alice": -30, "bob": 30, "carol": 0}


def test_settlement_pays_down_what_is_owed(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}

    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 30},
    )
    assert balances_by_name(client, group_id) == {"alice": 30, "bob": 0, "carol": -30}

    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["carol"], "to": ids["alice"], "amount": 30},
    )
    assert balances_by_name(client, group_id) == {"alice": 0, "bob": 0, "carol": 0}


def test_partial_settlement_leaves_the_remainder(client, ids, group_id):
    client.post(f"/groups/{group_id}/expenses", json={"paid_by": ids["alice"], "amount": 90})
    client.post(
        f"/groups/{group_id}/settlements",
        json={"from": ids["bob"], "to": ids["alice"], "amount": 10},
    )
    assert balances_by_name(client, group_id) == {"alice": 50, "bob": -20, "carol": -30}


# --- atomicity ---------------------------------------------------------------


def test_create_group_is_atomic(client, ids, monkeypatch):
    from splitr.services import users as users_service

    # Skip the up-front user check so an unknown member fails mid-transaction
    # (foreign key), after the group row has been inserted.
    monkeypatch.setattr(users_service, "require_users", lambda user_ids: None)
    res = client.post(
        "/groups", json={"name": "bad", "members": [ids["alice"], "no-such-user"]}
    )
    assert res.status_code == 500
    assert _count("groups") == 0
    assert _count("group_members") == 0


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
    from splitr.services.expenses import split_evenly

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

    from splitr.services import balances as balance_service
    from splitr.services import expenses as expense_service
    from splitr.services import groups as group_service
    from splitr.services import users as user_service

    app = create_app(str(tmp_path / "concurrent.db"))
    user_ids = [user_service.create_user(n, f"{n}@example.com").id for n in NAMES]
    gid = group_service.create_group("g", user_ids).id
    writers, per_writer = 6, 8
    errors, sums = [], []
    done = threading.Event()

    def writer(n):
        try:
            for i in range(per_writer):
                payer = user_ids[(n + i) % 3]
                with app.app_context():
                    expense_service.add_expense(gid, payer, 10 + i)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            while not done.is_set():
                with app.app_context():
                    balances = balance_service.get_balances(gid)
                    sums.append(round(sum(b.balance for b in balances), 2))
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


# --- settle-up ------------------------------------------------------------------


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
    assert _count("settlements") == 0
    assert balances_by_name(client, group_id) == before


def test_settle_up_unknown_group_returns_404(client):
    assert client.get("/groups/999/settle-up").status_code == 404


# --- timestamps ----------------------------------------------------------------


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


# --- idempotency ---------------------------------------------------------------


def post_with_key(client, path, body, key="key-1"):
    return client.post(path, json=body, headers={"Idempotency-Key": key})


def _sent_emails(monkeypatch):
    from splitr import notifier

    sent = []
    monkeypatch.setattr(notifier, "send_email", lambda to, s, b: sent.append(to))
    return sent


def test_repeating_an_expense_with_the_same_key_applies_it_once(client, ids, group_id, monkeypatch):
    from splitr import notifier

    sent = _sent_emails(monkeypatch)
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 90, "description": "dinner"}

    first = post_with_key(client, path, body)
    second = post_with_key(client, path, body)
    notifier.wait_for_pending(timeout=5)

    assert first.status_code == second.status_code == 201
    assert first.get_json() == second.get_json()  # same expense id and shares
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert _count("expenses") == 1
    assert _count("shares") == 3
    assert len(sent) == 3  # one email per member, not six
    assert balances_by_name(client, group_id) == {"alice": 60, "bob": -30, "carol": -30}


def test_retry_with_reordered_json_keys_is_still_a_replay(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    first = post_with_key(client, path, {"paid_by": ids["alice"], "amount": 30})
    second = post_with_key(client, path, {"amount": 30, "paid_by": ids["alice"]})
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.get_json() == second.get_json()
    assert _count("expenses") == 1


def test_without_a_key_a_retry_is_not_deduplicated(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 30}
    assert client.post(path, json=body).get_json()["id"] != client.post(path, json=body).get_json()["id"]
    assert _count("expenses") == 2


def test_a_different_key_is_a_new_request(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    body = {"paid_by": ids["alice"], "amount": 30}
    a = post_with_key(client, path, body, key="a")
    b = post_with_key(client, path, body, key="b")
    assert a.get_json()["id"] != b.get_json()["id"]
    assert _count("expenses") == 2


def test_reusing_a_key_for_a_different_request_is_a_conflict(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    post_with_key(client, path, {"paid_by": ids["alice"], "amount": 30})

    changed = post_with_key(client, path, {"paid_by": ids["alice"], "amount": 99})
    assert changed.status_code == 409
    assert "different request" in changed.get_json()["error"]

    other_endpoint = post_with_key(client, "/users", {"name": "dana"})
    assert other_endpoint.status_code == 409
    assert _count("expenses") == 1
    assert _count("users") == 3  # the fixture's three; dana was not created


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
        before = _count(table)
        first = post_with_key(client, path, body, key=f"key-{table}")
        second = post_with_key(client, path, body, key=f"key-{table}")
        assert first.status_code == second.status_code == 201
        assert first.get_json() == second.get_json()
        assert second.headers["Idempotent-Replayed"] == "true"
        assert _count(table) == before + 1


def test_a_failed_request_is_not_cached(client, ids, group_id):
    path = f"/groups/{group_id}/expenses"
    bad = post_with_key(client, path, {"paid_by": ids["alice"], "amount": -5})
    assert bad.status_code == 400
    assert _count("idempotency_keys") == 0  # the key was released

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
    assert _count("expenses") == 0
    assert _count("shares") == 0
    assert _count("idempotency_keys") == 0

    retry = post_with_key(client, path, body)  # same key, same body, now healthy
    assert retry.status_code == 201
    assert _count("expenses") == 1


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
    assert _count("expenses") == 1
    assert _count("shares") == 3


@pytest.mark.parametrize("key", ["", "  padded ", "x" * 256])
def test_bad_idempotency_keys_are_rejected(client, key):
    res = post_with_key(client, "/users", {"name": "dana"}, key=key)
    assert res.status_code == 400
    assert _count("users") == 0


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
    assert _count("expenses") == 2
    assert _count("idempotency_keys") == 1  # the stale row was purged, a fresh one stored


def test_after_commit_runs_only_after_the_outermost_commit(client):
    from splitr import db

    events = []
    with db.transaction() as conn:
        with db.transaction():  # nested: joins the outer transaction
            db.after_commit(lambda: events.append("callback"))
            conn.execute("INSERT INTO groups (name) VALUES ('nested')")
        assert events == []  # inner block ended, outer still open
        assert conn.in_transaction
    assert events == ["callback"]
    assert _count("groups") == 1

    db.after_commit(lambda: events.append("immediate"))  # no transaction open
    assert events == ["callback", "immediate"]


def test_after_commit_is_dropped_on_rollback(client):
    from splitr import db

    events = []
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            with db.transaction():
                conn.execute("INSERT INTO groups (name) VALUES ('doomed')")
                db.after_commit(lambda: events.append("should not run"))
            raise RuntimeError("outer fails after the inner block succeeded")
    assert events == []
    assert _count("groups") == 0  # the inner block's write was rolled back too


def test_a_failing_after_commit_callback_does_not_break_the_commit(client):
    from splitr import db

    def boom():
        raise RuntimeError("callback bug")

    with db.transaction() as conn:
        conn.execute("INSERT INTO groups (name) VALUES ('kept')")
        db.after_commit(boom)
    assert _count("groups") == 1


def test_a_version_2_database_is_upgraded_in_place(tmp_path):
    from splitr import db

    path = tmp_path / "v2.db"
    create_app(str(path))
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE idempotency_keys; PRAGMA user_version = 2;")
    conn.close()
    db._schema_ready.discard(str(path))

    create_app(str(path))  # opens the "old" file
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert "idempotency_keys" in tables
    assert version == db.SCHEMA_VERSION


# --- architecture ------------------------------------------------------------


def _imports(path):
    """Every module name imported (absolute or relative) by a source file."""
    import ast

    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            names.add(prefix)
            names.update(prefix.rstrip(".") + "." + a.name for a in node.names)
    return names


def _sources(layer):
    from pathlib import Path

    import splitr

    return sorted((Path(splitr.__file__).parent / layer).glob("*.py"))


def _violations(layer, forbidden):
    """Imports in ``layer`` whose module path contains a forbidden word."""
    bad = []
    for path in _sources(layer):
        for name in _imports(path):
            parts = [p for p in name.replace(".", " ").split() if p]
            if any(word in parts for word in forbidden):
                bad.append(f"{layer}/{path.name} imports {name}")
    return bad


def test_models_import_nothing_from_the_app():
    assert _violations("models", {"db", "repositories", "services", "controllers", "flask", "sqlite3"}) == []


def test_repositories_do_not_know_about_services_or_http():
    assert _violations("repositories", {"services", "controllers", "flask"}) == []


def test_services_have_no_http_and_no_sql():
    assert _violations("services", {"controllers", "flask", "sqlite3", "repositories_sql"}) == []
    # Services reach the database only through repositories and db.transaction.
    for path in _sources("services"):
        assert "execute(" not in path.read_text(), f"SQL found in services/{path.name}"


def test_controllers_only_talk_to_services():
    assert _violations("controllers", {"repositories", "db", "sqlite3", "notifier"}) == []
    for path in _sources("controllers"):
        assert "execute(" not in path.read_text(), f"SQL found in controllers/{path.name}"


def test_models_are_immutable_value_objects():
    import dataclasses

    from splitr.models import User

    user = User(id="u1", name="alice")
    assert user.email is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        user.name = "bob"


def test_repository_refuses_unlisted_sort_column(client, group_id):
    from splitr.repositories import expenses as expenses_repo

    with pytest.raises(ValueError):
        expenses_repo.list_for_group(group_id, 10, 0, "id; DROP TABLE expenses")


def test_services_return_models(client, ids, group_id):
    from splitr.models import Balance, Expense, Group, User
    from splitr.services import balances, expenses, groups, users

    assert isinstance(users.get_user(ids["alice"]), User)
    assert isinstance(groups.create_group("x", [ids["alice"]]), Group)
    expense, shares = expenses.add_expense(group_id, ids["alice"], 30)
    assert isinstance(expense, Expense) and expense.id is not None
    assert isinstance(expenses.list_expenses(group_id)[0], Expense)
    assert all(isinstance(b, Balance) for b in balances.get_balances(group_id))
