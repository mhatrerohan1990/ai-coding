"""Parallel requests: isolated transactions and consistent reads."""

from splitr.app import create_app

from .helpers import NAMES, count


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
                "(group_id, from_user_id, to_user_id, amount_cents, created_at) "
                "VALUES (?, ?, ?, 500, 'now')",
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
    assert count("settlements") == 1


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
                    sums.append(sum(b.balance_cents for b in balances))
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
    assert count("expenses") == writers * per_writer
    assert count("shares") == writers * per_writer * 3
    assert sums and all(s == 0 for s in sums)
