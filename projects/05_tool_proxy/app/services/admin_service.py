from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import BadRequestError, NotFoundError
from app.models import Tenant, Tool, ToolAccess, User
from app.schemas import CreateGrantRequest


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    def create_grant(self, tenant_id: str, request: CreateGrantRequest) -> None:
        if self.db.get(Tenant, tenant_id) is None:
            raise NotFoundError("tenant not found")

        # Scoped to the path tenant: a user from another tenant looks the same as a missing one.
        user = self.db.scalar(
            select(User).where(User.id == request.user_id, User.tenant_id == tenant_id)
        )
        if user is None:
            raise NotFoundError("user not found")

        tool = self.db.scalar(select(Tool).where(Tool.name == request.tool))
        if tool is None:
            raise BadRequestError("tool not found")

        access = self.db.scalar(
            select(ToolAccess).where(ToolAccess.user_id == user.id, ToolAccess.tool_id == tool.id)
        )
        if access is None:
            access = ToolAccess(user_id=user.id, tool_id=tool.id, enabled=True)
            self.db.add(access)
        else:
            access.enabled = True
        self.db.commit()

    def list_tool_calls(self, tenant_id: str) -> None:
        pass
