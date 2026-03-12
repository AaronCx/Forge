"""Base interface and response types for LLM providers."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    latency_ms: float
    provider: str
    raw_response: Any = None


@dataclass
class StreamChunk:
    """A single chunk from a streaming LLM response."""

    content: str = ""
    finish_reason: str | None = None
    model: str = ""
    provider: str = ""


@dataclass
class ModelInfo:
    """Metadata about an available model."""

    id: str
    name: str
    provider: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_streaming: bool = True


@dataclass
class ProviderHealth:
    """Health status of a provider."""

    provider: str
    status: str  # "healthy", "degraded", "unavailable"
    latency_ms: float | None = None
    error: str | None = None
    checked_at: float = field(default_factory=time.time)


class LLMProvider(ABC):
    """Base interface that every LLM provider implements."""

    provider_name: str = ""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """Generate a completion from the model.

        Args:
            messages: Chat messages in OpenAI format
                      [{"role": "system", "content": "..."}, ...]
            model: Model identifier (e.g. "gpt-4o", "claude-sonnet-4-20250514")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Tool definitions for function calling
            stream: Whether to stream the response (use stream_complete instead)

        Returns:
            Standardized LLMResponse.
        """

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion from the model.

        Yields StreamChunk objects as they arrive.
        """
        # Make this an async generator to satisfy type checkers
        yield StreamChunk()  # pragma: no cover

    @abstractmethod
    async def count_tokens(self, text: str, model: str) -> int:
        """Count the number of tokens in the given text for the specified model."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return the list of models available from this provider."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check whether the provider is reachable and responsive."""
