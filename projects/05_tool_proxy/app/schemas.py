from datetime import datetime

from pydantic import BaseModel


class CreateGrantRequest(BaseModel):
    user_id: str
    tool: str



class ToolCallResponse(BaseModel):
    call_id: str
    actor_sub: str
    agent_id: str
    tool: str
    allowed: bool
    created_at: datetime
