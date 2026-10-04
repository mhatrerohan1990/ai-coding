from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tenant, TenantAgentAccess, Tool, ToolAccess, User
from app.schemas import AgentToolCallRequest


class MemberService:
    def __init__(self, db: Session):
        self.db = db

    def check_tool_call(
        self, tenant_id: str, user_id: str, agent_id: str, request: AgentToolCallRequest
    ) -> bool:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None or not tenant.enabled or not tenant.ai_enabled:
            return False

        agent_access = self.db.scalar(
            select(TenantAgentAccess).where(
                TenantAgentAccess.tenant_id == tenant_id,
                TenantAgentAccess.agent_id == agent_id,
            )
        )
        if agent_access is None or not agent_access.enabled:
            return False

        user = self.db.scalar(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        if user is None or not user.enabled:
            return False

        tool = self.db.scalar(select(Tool).where(Tool.name == request.tool))
        if tool is None:
            return False

        tool_access = self.db.scalar(
            select(ToolAccess).where(
                ToolAccess.user_id == user.id, ToolAccess.tool_id == tool.id
            )
        )
        return tool_access is not None and tool_access.enabled
