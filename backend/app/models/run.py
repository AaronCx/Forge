from datetime import datetime

from pydantic import BaseModel


class RunCreate(BaseModel):
    input_text: str | None = None
    input_file_url: str | None = None


class StepLog(BaseModel):
    step: int
    result: str
    duration_ms: int


class RunResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str
    input_text: str | None
    input_file_url: str | None
    output: str | None
    step_logs: list[StepLog]
    status: str
    tokens_used: int
    duration_ms: int | None
    created_at: datetime
