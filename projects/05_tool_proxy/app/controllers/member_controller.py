from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AgentToolCallRequest, AgentToolCallResponse
from app.services.member_service import MemberService

router = APIRouter(tags=["member"])


def get_member_service(db: Session = Depends(get_db)) -> MemberService:
    return MemberService(db)


# Identity comes from headers for now, as a placeholder until authn is built.
@router.post("/agent/tool-calls", response_model=AgentToolCallResponse)
def create_tool_call(
    request: AgentToolCallRequest,
    tenant_id: str = Header(alias="X-Tenant-Id"),
    user_id: str = Header(alias="X-User-Id"),
    agent_id: str = Header(alias="X-Agent-Id"),
    service: MemberService = Depends(get_member_service),
):
    allowed = service.check_tool_call(tenant_id, user_id, agent_id, request)
    return AgentToolCallResponse(allowed=allowed)
