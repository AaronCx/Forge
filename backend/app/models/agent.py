from datetime import datetime

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    tools: list[str] = []
    workflow_steps: list[str] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    workflow_steps: list[str] | None = None


class AgentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    tools: list[str]
    workflow_steps: list[str]
    is_template: bool
    created_at: datetime
    updated_at: datetime
