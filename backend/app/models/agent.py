from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    system_prompt: str = Field(..., min_length=1, max_length=10000)
    tools: list[str] = Field(default_factory=list, max_length=20)
    workflow_steps: list[str] = Field(default_factory=list, max_length=50)
    model: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    system_prompt: str | None = Field(None, min_length=1, max_length=10000)
    tools: list[str] | None = Field(None, max_length=20)
    workflow_steps: list[str] | None = Field(None, max_length=50)
    model: str | None = None


class AgentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    tools: list[str]
    workflow_steps: list[str]
    model: str | None = None
    is_template: bool
    created_at: datetime
    updated_at: datetime
