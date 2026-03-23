"""Pydantic models for the Workspace system."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=2000)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=2000)


class WorkspaceResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    path: str
    status: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FileEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: int | None = None
    children: list["FileEntry"] | None = None


class FileContent(BaseModel):
    path: str
    content: str
    size: int


class FileWrite(BaseModel):
    content: str


class FileSearch(BaseModel):
    query: str
    glob: str = "*"


class SearchResult(BaseModel):
    path: str
    line: int
    content: str


class WorkspaceChangeResponse(BaseModel):
    id: str
    workspace_id: str
    file_path: str
    change_type: str
    attribution: str
    created_at: datetime
