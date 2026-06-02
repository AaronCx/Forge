"""Dispatcher models — routing decision + the /api/dispatch request body."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.attachment import Attachment


class CatalogEntry(BaseModel):
    """A routable target shown to the routing LLM."""

    type: Literal["agent", "blueprint"]
    id: str
    name: str
    description: str = ""


class Decision(BaseModel):
    """The routing LLM's structured decision."""

    action: Literal["route", "clarify", "none"]
    target_type: Literal["agent", "blueprint"] | None = None
    target_id: str | None = None
    input_text: str = ""
    rationale: str = ""
    clarifying_question: str = ""


class DispatchRequest(BaseModel):
    """Body for POST /api/dispatch."""

    message: str = Field("", max_length=50_000)
    attachments: list[Attachment] = Field(default_factory=list)
    thread_id: str | None = None
    # PR-7: lets the user override the routing target and re-run.
    target_type: Literal["agent", "blueprint"] | None = None
    target_id: str | None = None
