"""Concurrent accepts of one token, each on its own session against a real file DB."""

import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.db import Base, get_db
from app.errors import InviteUsedError
from app.main import app
from app.models import Invite, User
from app.models import Member as MemberRow
from app.services import invites
from tests.helpers import as_

N = 10


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False, "timeout": 30}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _race(fn) -> list:
    barrier = threading.Barrier(N)
    results: list = [None] * N

    def run(i):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as e:  # noqa: BLE001
            results[i] = e

    threads = [threading.Thread(target=run, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_accepts_service_level(factory):
    with factory() as s:
        token = invites.create_invite(s, "t1", "a@x.com").token
    now = datetime.now(timezone.utc)

    def accept():
        with factory() as s:
            return invites.accept_invite(s, token, now=now)

    results = _race(accept)

    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(winners) == 1
    assert len(losers) == N - 1 and all(isinstance(e, InviteUsedError) for e in losers)
    with factory() as s:
        assert len(s.scalars(select(MemberRow)).all()) == 1
        assert len(s.scalars(select(User)).all()) == 1
        assert s.scalars(select(Invite)).one().used_at is not None


def test_concurrent_accepts_http_level(factory):
    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        token = client.post("/tenants/t1/invites", json={"email": "a@x.com"}, headers=as_("t1")).json()["token"]
        codes = _race(lambda: client.post("/invites/accept", json={"token": token}).status_code)
    finally:
        app.dependency_overrides.clear()

    assert sorted(codes) == [201] + [409] * (N - 1)
    with factory() as s:
        assert len(s.scalars(select(MemberRow)).all()) == 1
