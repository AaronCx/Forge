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

    # --- kernel interface (harness-plan.md Phase 2) ---
    #
    # Default implementations derive kernel turns from the legacy
    # complete()/stream_complete() via message conversion, so every existing
    # provider (and every test double) speaks kernel without changes. Providers
    # with native tool/image support override these for full fidelity.

    async def turn(
        self,
        messages: list[Any],
        model: str,
        *,
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Any:
        """Run one kernel turn and return a ``TurnResult``.

        ``messages`` is a list of ``KMessage``; ``tools`` a list of ``ToolSpec``.
        """
        from app.kernel.convert import to_openai_messages
        from app.kernel.types import TurnResult, Usage
        from app.providers.kernel_bridge import (
            default_turn_blocks_from_text,
            stop_from_openai,
            tools_to_openai,
        )

        resp = await self.complete(
            to_openai_messages(messages),
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools_to_openai(tools),
        )
        return TurnResult(
            blocks=default_turn_blocks_from_text(resp.content),
            stop_reason=stop_from_openai(resp.finish_reason),
            usage=Usage(input_tokens=resp.input_tokens, output_tokens=resp.output_tokens),
            model=resp.model,
            provider=resp.provider,
            latency_ms=resp.latency_ms,
        )

    async def stream_turn(
        self,
        messages: list[Any],
        model: str,
        *,
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[Any]:
        """Stream one kernel turn as ``StreamEvent``s, ending with ``TurnDone``."""
        from app.kernel.convert import to_openai_messages
        from app.kernel.types import TextBlock, TextDelta, TurnDone, TurnResult, Usage
        from app.providers.kernel_bridge import stop_from_openai, tools_to_openai

        text_parts: list[str] = []
        finish_reason: str | None = None
        async for chunk in self.stream_complete(
            to_openai_messages(messages),
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools_to_openai(tools),
        ):
            if chunk.content:
                text_parts.append(chunk.content)
                yield TextDelta(text=chunk.content)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
        text = "".join(text_parts)
        yield TurnDone(
            turn=TurnResult(
                blocks=[TextBlock(text)] if text else [],
                stop_reason=stop_from_openai(finish_reason),
                usage=Usage(),
                model=model,
                provider=self.provider_name,
            )
        )

    @abstractmethod
    async def count_tokens(self, text: str, model: str) -> int:
        """Count the number of tokens in the given text for the specified model."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return the list of models available from this provider."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check whether the provider is reachable and responsive."""
