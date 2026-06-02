"""Pydantic models for the Blueprint system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.attachment import Attachment


class BlueprintNode(BaseModel):
    """A single node in the blueprint DAG."""

    id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    label: str = Field("", max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    position: dict[str, float] | None = None  # For React Flow {x, y}


class BlueprintCreate(BaseModel):
    """Create a new blueprint."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    nodes: list[BlueprintNode] = Field(default_factory=list, max_length=50)
    context_config: dict[str, Any] = Field(default_factory=dict)
    tool_scope: list[str] = Field(default_factory=list, max_length=20)
    retry_policy: dict[str, int] = Field(default_factory=lambda: {"max_retries": 2})
    output_schema: dict[str, Any] | None = None


class BlueprintUpdate(BaseModel):
    """Update a blueprint."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    nodes: list[BlueprintNode] | None = Field(None, max_length=50)
    context_config: dict[str, Any] | None = None
    tool_scope: list[str] | None = Field(None, max_length=20)
    retry_policy: dict[str, int] | None = None
    output_schema: dict[str, Any] | None = None


class BlueprintResponse(BaseModel):
    """Blueprint response with full data."""

    id: str
    user_id: str
    name: str
    description: str
    version: int
    is_template: bool
    nodes: list[dict[str, Any]]
    context_config: dict[str, Any]
    tool_scope: list[str]
    retry_policy: dict[str, Any]
    output_schema: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class BlueprintRunRequest(BaseModel):
    """Request to execute a blueprint."""

    input_text: str = Field("", max_length=50000)
    input_data: dict[str, Any] = Field(default_factory=dict)
    attachments: list[Attachment] = Field(default_factory=list)


class BlueprintRunResponse(BaseModel):
    """Blueprint run execution record."""

    id: str
    blueprint_id: str
    user_id: str
    status: str
    input_payload: dict[str, Any]
    output: dict[str, Any] | None
    execution_trace: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
