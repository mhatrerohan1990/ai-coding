from datetime import datetime

from pydantic import BaseModel, EmailStr


class CreateInviteRequest(BaseModel):
    email: EmailStr


class InviteCreated(BaseModel):
    invite_id: str
    tenant_id: str
    email: str
    token: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    token: str


class Member(BaseModel):
    id: str
    user_id: str
    email: str
    tenant_id: str
    role: str


class MemberList(BaseModel):
    members: list[Member]
