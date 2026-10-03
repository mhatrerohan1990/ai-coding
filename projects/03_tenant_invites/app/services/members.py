from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Member as MemberRow
from app.models import User
from app.schemas import Member


def list_members(db: Session, tenant_id: str) -> list[Member]:
    """List all members of a tenant, oldest first."""
    rows = db.execute(
        select(MemberRow, User.email)
        .join(User, User.id == MemberRow.user_id)
        .where(MemberRow.tenant_id == tenant_id)
        .order_by(MemberRow.created_at, MemberRow.id)
    )
    return [
        Member(id=m.id, user_id=m.user_id, email=email, tenant_id=m.tenant_id, role=m.role)
        for m, email in rows
    ]
