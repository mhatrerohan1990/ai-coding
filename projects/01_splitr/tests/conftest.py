"""Fixtures shared by every test module."""

import pytest

from splitr.app import create_app

from .helpers import NAMES, make_users


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


@pytest.fixture
def ids(client):
    """``{"alice": <uuid>, "bob": <uuid>, "carol": <uuid>}``"""
    return make_users(client, NAMES)


@pytest.fixture
def group_id(client, ids):
    res = client.post("/groups", json={"name": "trip", "members": list(ids.values())})
    return res.get_json()["id"]
