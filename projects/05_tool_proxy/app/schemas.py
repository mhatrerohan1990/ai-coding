from pydantic import BaseModel


class CreateGrantRequest(BaseModel):
    user_id: str
    tool: str

