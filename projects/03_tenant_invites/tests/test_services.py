from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import tokens
from app.errors import AlreadyMemberError, InvalidInviteError, InviteUsedError
from app.models import Invite, User
from app.models import Member as MemberRow
from app.schemas import InviteCreated, Member
from app.services import invites, members

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pending(db, tenant_id="t1", email="a@x.com"):
    return list(
        db.scalars(
            select(Invite).where(
                Invite.tenant_id == tenant_id, Invite.email == email, Invite.used_at.is_(None)
            )
        )
    )


def test_create_invite_returns_token_and_default_7_day_expiry(db):
    result = invites.create_invite(db, "t1", "a@x.com", now=NOW)
    assert isinstance(result, InviteCreated)
    assert (result.tenant_id, result.email) == ("t1", "a@x.com")
    assert result.expires_at == NOW + timedelta(days=7)
    assert tokens.parse(result.token)[0] == result.invite_id


def test_create_invite_stores_only_hash(db):
    result = invites.create_invite(db, "t1", "a@x.com", now=NOW)
    _, secret = tokens.parse(result.token)
    row = db.get(Invite, result.invite_id)
    assert row.used_at is None
    assert row.token_hash == tokens.hash_secret(secret)
    assert secret not in (row.token_hash, row.id)


def test_create_invite_does_not_create_member_or_user(db):
    assert not isinstance(invites.create_invite(db, "t1", "a@x.com"), Member)
    assert db.scalars(select(MemberRow)).all() == []
    assert db.scalars(select(User)).all() == []


def test_email_is_normalized(db):
    result = invites.create_invite(db, "t1", "  A@X.com ")
    assert result.email == "a@x.com"


def test_reissue_keeps_invite_id_rotates_token_and_invalidates_old(db):
    first = invites.create_invite(db, "t1", "a@x.com", now=NOW)
    second = invites.create_invite(db, "t1", "A@x.com", now=NOW + timedelta(days=3))

    assert second.invite_id == first.invite_id
    assert second.token != first.token
    assert second.expires_at == NOW + timedelta(days=10)  # expiry reset

    (row,) = _pending(db)
    _, old_secret = tokens.parse(first.token)
    _, new_secret = tokens.parse(second.token)
    assert not tokens.verify(old_secret, row.token_hash)
    assert tokens.verify(new_secret, row.token_hash)


def test_different_email_or_tenant_gets_separate_invite(db):
    a = invites.create_invite(db, "t1", "a@x.com")
    b = invites.create_invite(db, "t1", "b@x.com")
    c = invites.create_invite(db, "t2", "a@x.com")
    assert len({a.invite_id, b.invite_id, c.invite_id}) == 3


def test_used_invite_does_not_block_a_new_pending_one(db):
    first = invites.create_invite(db, "t1", "a@x.com", now=NOW)
    db.get(Invite, first.invite_id).used_at = NOW
    db.commit()
    second = invites.create_invite(db, "t1", "a@x.com", now=NOW)
    assert second.invite_id != first.invite_id


def test_db_enforces_one_pending_invite_per_tenant_email(db):
    kw = dict(tenant_id="t1", email="a@x.com", token_hash="h", created_at=NOW, expires_at=NOW)
    db.add(Invite(id="i1", **kw))
    db.commit()
    db.add(Invite(id="i2", **kw))
    with pytest.raises(IntegrityError):
        db.commit()


def _count(db, model):
    return len(db.scalars(select(model)).all())


def _invite(db, tenant="t1", email="a@x.com", now=NOW):
    return invites.create_invite(db, tenant, email, now=now)


def test_accept_creates_user_and_member_and_burns_invite(db):
    created = _invite(db)
    member = invites.accept_invite(db, created.token, now=NOW)
    assert isinstance(member, Member)
    assert (member.tenant_id, member.email, member.role) == ("t1", "a@x.com", "member")
    assert _count(db, User) == 1
    assert _count(db, MemberRow) == 1
    assert db.get(Invite, created.invite_id).used_at is not None
    assert [m.email for m in members.list_members(db, "t1")] == ["a@x.com"]


def test_accept_is_single_use(db):
    created = _invite(db)
    invites.accept_invite(db, created.token, now=NOW)
    with pytest.raises(InviteUsedError):
        invites.accept_invite(db, created.token, now=NOW)
    assert _count(db, MemberRow) == 1


def test_accept_reuses_existing_user_across_tenants(db):
    first = invites.accept_invite(db, _invite(db, "t1").token, now=NOW)
    second = invites.accept_invite(db, _invite(db, "t2").token, now=NOW)
    assert first.user_id == second.user_id
    assert (first.tenant_id, second.tenant_id) == ("t1", "t2")
    assert _count(db, User) == 1
    assert _count(db, MemberRow) == 2


def test_accept_when_already_member_stores_nothing(db):
    invites.accept_invite(db, _invite(db).token, now=NOW)
    again = _invite(db)  # new pending invite for the same email/tenant
    with pytest.raises(AlreadyMemberError):
        invites.accept_invite(db, again.token, now=NOW)
    assert _count(db, User) == 1
    assert _count(db, MemberRow) == 1
    assert db.get(Invite, again.invite_id).used_at is None


@pytest.mark.parametrize("bad", ["", "garbage", "a.b.c", ".x", "x."])
def test_accept_rejects_malformed(db, bad):
    with pytest.raises(InvalidInviteError):
        invites.accept_invite(db, bad)


def test_accept_rejects_unknown_id_and_wrong_secret(db):
    created = _invite(db)
    invite_id, _ = tokens.parse(created.token)
    for bad in ["nope." + tokens.new_secret(), tokens.format_token(invite_id, tokens.new_secret())]:
        with pytest.raises(InvalidInviteError):
            invites.accept_invite(db, bad, now=NOW)
    assert db.get(Invite, invite_id).used_at is None
    assert _count(db, MemberRow) == 0


def test_accept_rejects_expired_and_leaves_invite_unused(db):
    created = _invite(db)
    with pytest.raises(InvalidInviteError):
        invites.accept_invite(db, created.token, now=NOW + timedelta(days=7, seconds=1))
    assert _count(db, MemberRow) == 0
    assert db.get(Invite, created.invite_id).used_at is None


def test_accept_at_exact_boundary_before_expiry(db):
    created = _invite(db)
    invites.accept_invite(db, created.token, now=NOW + timedelta(days=7, seconds=-1))


def test_reissued_token_invalidates_old_one(db):
    old = _invite(db)
    new = _invite(db)
    with pytest.raises(InvalidInviteError):
        invites.accept_invite(db, old.token, now=NOW)
    assert invites.accept_invite(db, new.token, now=NOW).email == "a@x.com"


def _add_member(db, id, tenant_id, email, role="member", minute=0):
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(id=f"u-{email}", email=email, created_at=NOW)
        db.add(user)
    db.add(
        MemberRow(
            id=id,
            tenant_id=tenant_id,
            user_id=user.id,
            role=role,
            created_at=NOW + timedelta(minutes=minute),
        )
    )
    db.commit()


def test_list_members_empty_tenant(db):
    assert members.list_members(db, "nobody") == []


def test_list_members_scoped_to_tenant_and_includes_email(db):
    _add_member(db, "m1", "t1", "a@x.com")
    _add_member(db, "m2", "t2", "b@x.com")
    result = members.list_members(db, "t1")
    assert [(m.id, m.email, m.tenant_id) for m in result] == [("m1", "a@x.com", "t1")]


def test_same_user_in_two_tenants(db):
    _add_member(db, "m1", "t1", "a@x.com")
    _add_member(db, "m2", "t2", "a@x.com")
    assert members.list_members(db, "t1")[0].user_id == members.list_members(db, "t2")[0].user_id


def test_list_members_ordered_oldest_first_and_includes_roles(db):
    _add_member(db, "late", "t1", "late@x.com", minute=5)
    _add_member(db, "admin", "t1", "admin@x.com", role="admin", minute=0)
    result = members.list_members(db, "t1")
    assert [(m.id, m.role) for m in result] == [("admin", "admin"), ("late", "member")]
