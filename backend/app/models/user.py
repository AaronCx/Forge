from pydantic import BaseModel
from typing import Optional


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    created_at: str
    last_used_at: Optional[str] = None
