from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_member_or_admin
from app.db import get_db
from app.schemas import MemberList
from app.services import members

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/members",
    response_model=MemberList,
    dependencies=[Depends(require_member_or_admin)],
)
def list_members(tenant_id: str, db: Session = Depends(get_db)) -> MemberList:
    return MemberList(members=members.list_members(db, tenant_id))
