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
    # Nullable: when an agent is deleted, the run row is preserved (per QA
    # playbook §6.4) and its back-reference is set to NULL.
    agent_id: str | None
    user_id: str
    input_text: str | None
    input_file_url: str | None
    output: str | None
    step_logs: list[StepLog]
    status: str
    tokens_used: int
    duration_ms: int | None
    created_at: datetime
