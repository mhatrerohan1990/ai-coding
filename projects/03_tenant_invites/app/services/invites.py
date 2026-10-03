from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import tokens
from app.config import INVITE_TTL
from app.errors import AlreadyMemberError, InvalidInviteError, InviteUsedError
from app.models import Invite
from app.models import Member as MemberRow
from app.models import User
from app.schemas import InviteCreated, Member


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_pending(db: Session, tenant_id: str, email: str) -> Invite | None:
    return db.scalar(
        select(Invite).where(
            Invite.tenant_id == tenant_id, Invite.email == email, Invite.used_at.is_(None)
        )
    )


def create_invite(
    db: Session, tenant_id: str, email: str, now: datetime | None = None
) -> InviteCreated:
    """Generate a single-use invite token for (tenant, email). Does not create a member.

    One pending invite per (tenant_id, email): if one exists, keep its id, issue a new
    token (replacing the stored hash, which invalidates the old token) and reset expiry.
    """
    now = now or datetime.now(timezone.utc)
    email = normalize_email(email)
    secret = tokens.new_secret()
    token_hash = tokens.hash_secret(secret)
    expires_at = now + INVITE_TTL

    invite = _find_pending(db, tenant_id, email)
    if invite is None:
        invite = Invite(
            id=tokens.new_invite_id(),
            tenant_id=tenant_id,
            email=email,
            token_hash=token_hash,
            created_at=now,
            expires_at=expires_at,
        )
        db.add(invite)
        try:
            db.commit()
        except IntegrityError:
            # Lost a race with a concurrent create for the same (tenant, email).
            db.rollback()
            invite = _find_pending(db, tenant_id, email)
            assert invite is not None
            invite.token_hash, invite.expires_at = token_hash, expires_at
            db.commit()
    else:
        invite.token_hash, invite.expires_at = token_hash, expires_at
        db.commit()

    return InviteCreated(
        invite_id=invite.id,
        tenant_id=tenant_id,
        email=email,
        token=tokens.format_token(invite.id, secret),
        expires_at=invite.expires_at,
    )


_DUMMY_HASH = tokens.hash_secret("dummy")  # compared against when the invite id is unknown


def accept_invite(db: Session, token: str, now: datetime | None = None) -> Member:
    """Redeem an invite token: find-or-create the user, add them to the tenant, burn the token.

    Raises InvalidInviteError for a bad token (malformed, unknown, wrong secret, expired),
    InviteUsedError if it was already redeemed, and AlreadyMemberError if the email is
    already a member. On any error nothing is
    stored and the invite stays unused.
    """
    now = now or datetime.now(timezone.utc)
    try:
        return _accept_once(db, token, now)
    except IntegrityError:
        # Lost a race (e.g. concurrent first-time creation of the same user). Retry once;
        # the retry sees the committed rows and either succeeds or reports AlreadyMember.
        db.rollback()
        try:
            return _accept_once(db, token, now)
        except IntegrityError:
            db.rollback()
            raise InvalidInviteError from None


def _accept_once(db: Session, token: str, now: datetime) -> Member:
    parsed = tokens.parse(token)
    if parsed is None:
        raise InvalidInviteError
    invite_id, secret = parsed

    invite = db.get(Invite, invite_id)
    secret_ok = tokens.verify(secret, invite.token_hash if invite else _DUMMY_HASH)
    if invite is None or not secret_ok:
        raise InvalidInviteError
    tenant_id, email = invite.tenant_id, invite.email

    # Atomic single-use claim; this is the real gate against replay and concurrent accepts.
    claimed = db.execute(
        update(Invite)
        .where(Invite.id == invite_id, Invite.used_at.is_(None), Invite.expires_at > now)
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        # Secret already verified, so telling the holder it was used leaks nothing.
        if db.scalar(select(Invite.used_at).where(Invite.id == invite_id)) is not None:
            raise InviteUsedError
        raise InvalidInviteError  # expired
    db.expire(invite)

    user = db.scalar(select(User).where(User.email == email))
    if user is not None and db.scalar(
        select(MemberRow.id).where(MemberRow.tenant_id == tenant_id, MemberRow.user_id == user.id)
    ):
        db.rollback()  # undoes the claim: nothing stored, invite stays unused
        raise AlreadyMemberError

    if user is None:
        user = User(id=str(uuid4()), email=email, created_at=now)
        db.add(user)
    member = MemberRow(
        id=str(uuid4()), tenant_id=tenant_id, user_id=user.id, role="member", created_at=now
    )
    db.add(member)
    db.commit()
    return Member(
        id=member.id, user_id=user.id, email=email, tenant_id=tenant_id, role=member.role
    )
