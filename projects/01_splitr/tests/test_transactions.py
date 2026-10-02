"""db.transaction() nesting and db.after_commit() side-effect timing."""

import pytest

from .helpers import count


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
    assert count("groups") == 1

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
    assert count("groups") == 0  # the inner block's write was rolled back too


def test_a_failing_after_commit_callback_does_not_break_the_commit(client):
    from splitr import db

    def boom():
        raise RuntimeError("callback bug")

    with db.transaction() as conn:
        conn.execute("INSERT INTO groups (name) VALUES ('kept')")
        db.after_commit(boom)
    assert count("groups") == 1
