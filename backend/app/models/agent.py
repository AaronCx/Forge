from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    tools: list[str] = []
    workflow_steps: list[str] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[list[str]] = None
    workflow_steps: Optional[list[str]] = None


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
