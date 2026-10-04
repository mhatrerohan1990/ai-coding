import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_by: Mapped[str] = mapped_column(String, default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    updated_by: Mapped[str] = mapped_column(String, default="system")


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class Tenant(AuditMixin, Base):
    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class User(AuditMixin, Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.MEMBER)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Tool(AuditMixin, Base):
    __tablename__ = "tool"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)


class ToolAccess(AuditMixin, Base):
    __tablename__ = "tool_access"
    __table_args__ = (UniqueConstraint("user_id", "tool_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    tool_id: Mapped[str] = mapped_column(ForeignKey("tool.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Agent(AuditMixin, Base):
    __tablename__ = "agent"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)


class TenantAgentAccess(AuditMixin, Base):
    __tablename__ = "tenant_agent_access"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Credential is "<prefix>.<secret>". Prefix is stored plain for lookup,
    # only the sha256 of the secret part is stored.
    secret_prefix: Mapped[str] = mapped_column(String, unique=True)
    secret_hash: Mapped[str] = mapped_column(String)


class ToolCall(AuditMixin, Base):
    __tablename__ = "tool_call"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"))
    tool: Mapped[str] = mapped_column(String)
    allowed: Mapped[bool] = mapped_column(Boolean)
