"""Attachment models shared by the run, blueprint, upload, and dispatch APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Attachment(BaseModel):
    """A file carried into a run: an image (multimodal) or a document (text)."""

    url: str
    kind: Literal["image", "document"]
    name: str
    mime: str


class RunRequest(BaseModel):
    """Optional JSON body for the agent run endpoint.

    Back-compat: ``input_text`` may still arrive as a query param. When a body
    is present its ``input_text`` wins; ``attachments`` are only available via
    the body.
    """

    input_text: str | None = None
    attachments: list[Attachment] = []
