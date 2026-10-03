from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Invite
from app.models import Member as MemberRow
from app.services import invites
from app.models import User
from tests.helpers import as_

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _invite(client, tenant="t1", email="a@x.com"):
    return client.post(f"/tenants/{tenant}/invites", json={"email": email}, headers=as_(tenant))


def test_create_invite(client):
    resp = _invite(client)
    assert resp.status_code == 201
    body = resp.json()
    assert (body["tenant_id"], body["email"]) == ("t1", "a@x.com")
    assert body["token"].startswith(body["invite_id"] + ".")
    assert "token_hash" not in body


def test_create_invite_again_returns_same_id_and_new_token(client):
    first = _invite(client).json()
    second = _invite(client, email="A@X.com").json()
    assert second["invite_id"] == first["invite_id"]
    assert second["token"] != first["token"]


def test_create_invite_validates_email(client):
    assert _invite(client, email="not-an-email").status_code == 422
    assert client.post("/tenants/t1/invites", json={}, headers=as_("t1")).status_code == 422
    assert client.post("/tenants/t1/invites", headers=as_("t1")).status_code == 422


def _accept(client, token):
    return client.post("/invites/accept", json={"token": token})


def test_accept_invite_end_to_end(client):
    token = _invite(client).json()["token"]
    resp = _accept(client, token)
    assert resp.status_code == 201
    body = resp.json()
    assert (body["email"], body["tenant_id"], body["role"]) == ("a@x.com", "t1", "member")

    listed = client.get("/tenants/t1/members", headers=as_("t1")).json()["members"]
    assert [m["email"] for m in listed] == ["a@x.com"]


def test_accept_invite_second_use_is_409(client):
    token = _invite(client).json()["token"]
    assert _accept(client, token).status_code == 201
    resp = _accept(client, token)
    assert resp.status_code == 409
    assert resp.json() == {"detail": "This invite has already been used."}
    assert len(client.get("/tenants/t1/members", headers=as_("t1")).json()["members"]) == 1


def test_accept_twice_second_is_409_and_one_member_row(client, db):
    token = _invite(client).json()["token"]
    assert _accept(client, token).status_code == 201
    assert _accept(client, token).status_code == 409
    assert db.scalar(select(func.count()).select_from(MemberRow)) == 1
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_accept_expired_invite_creates_no_member(client, db):
    # Invite issued 8 days ago (default TTL is 7), redeemed now over HTTP.
    created = invites.create_invite(
        db, "t1", "a@x.com", now=datetime.now(timezone.utc) - timedelta(days=8)
    )
    resp = _accept(client, created.token)
    assert resp.status_code == 400
    assert db.scalar(select(func.count()).select_from(MemberRow)) == 0
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.get(Invite, created.invite_id).used_at is None


def test_accept_invite_bad_token_is_400(client):
    assert _accept(client, "abc").status_code == 400
    assert _accept(client, "nope.nope").status_code == 400


def test_accept_invite_old_token_after_reissue_is_400(client):
    old = _invite(client).json()["token"]
    new = _invite(client).json()["token"]
    assert _accept(client, old).status_code == 400
    assert _accept(client, new).status_code == 201


def test_accept_invite_already_member_is_409_and_nothing_stored(client):
    assert _accept(client, _invite(client).json()["token"]).status_code == 201
    resp = _accept(client, _invite(client).json()["token"])
    assert resp.status_code == 409
    assert resp.json() == {"detail": "You are already a member of this tenant."}
    assert len(client.get("/tenants/t1/members", headers=as_("t1")).json()["members"]) == 1


def test_same_email_can_join_multiple_tenants(client):
    assert _accept(client, _invite(client, "t1").json()["token"]).status_code == 201
    assert _accept(client, _invite(client, "t2").json()["token"]).status_code == 201


def test_list_members(client, db):
    db.add_all(
        [
            User(id="u1", email="a@x.com", created_at=NOW),
            User(id="u2", email="b@x.com", created_at=NOW),
            MemberRow(id="m1", tenant_id="t1", user_id="u1", role="admin", created_at=NOW),
            MemberRow(id="m2", tenant_id="t2", user_id="u2", created_at=NOW),
        ]
    )
    db.commit()
    resp = client.get("/tenants/t1/members", headers=as_("t1"))
    assert resp.status_code == 200
    assert resp.json() == {
        "members": [
            {"id": "m1", "user_id": "u1", "email": "a@x.com", "tenant_id": "t1", "role": "admin"}
        ]
    }


def test_list_members_empty_tenant_is_200(client):
    resp = client.get("/tenants/unknown/members", headers=as_("unknown"))
    assert resp.status_code == 200
    assert resp.json() == {"members": []}


def test_accept_invite_requires_token(client):
    assert client.post("/invites/accept", json={}).status_code == 422


def test_accept_invite_rejects_missing_body(client):
    assert client.post("/invites/accept").status_code == 422


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
