from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db

from app.schemas import AcceptInviteRequest, CreateInviteRequest, InviteCreated, Member
from app.services import invites

router = APIRouter()


@router.post(
    "/tenants/{tenant_id}/invites",
    response_model=InviteCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_invite(
    tenant_id: str, body: CreateInviteRequest, db: Session = Depends(get_db)
) -> InviteCreated:
    return invites.create_invite(db, tenant_id, body.email)


@router.post("/invites/accept", response_model=Member, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInviteRequest, db: Session = Depends(get_db)) -> Member:
    return invites.accept_invite(db, body.token)
