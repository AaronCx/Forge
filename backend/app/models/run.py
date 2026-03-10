from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RunCreate(BaseModel):
    input_text: Optional[str] = None
    input_file_url: Optional[str] = None


class StepLog(BaseModel):
    step: int
    result: str
    duration_ms: int


class RunResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str
    input_text: Optional[str]
    input_file_url: Optional[str]
    output: Optional[str]
    step_logs: list[StepLog]
    status: str
    tokens_used: int
    duration_ms: Optional[int]
    created_at: datetime
