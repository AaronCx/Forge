"""Deterministic in-process provider for parity and unit tests.

FakeProvider implements the full LLMProvider contract with canned,
fully reproducible responses so golden-snapshot tests never drift:
latency is always 0.0, token counts derive only from message/response
lengths, and content comes from an optional response queue or a
deterministic echo of the last user message.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)


def _text_of(content: Any) -> str:
    """Flatten string-or-blocks message content to plain text."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return " ".join(part for part in parts if part)
    return str(content)


class FakeProvider(LLMProvider):
    """LLM provider returning canned, deterministic responses.

    Responses are served from ``responses`` in order; once the queue is
    exhausted (or when none is given) the provider echoes a digest of the
    request: ``[fake:<model>] <last user message, truncated>``. Every call
    is appended to ``self.calls`` for assertions.
    """

    provider_name = "fake"
    default_model = "fake-model"

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def _next_content(self, messages: list[dict[str, Any]], model: str) -> str:
        if self._responses:
            return self._responses.pop(0)
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = _text_of(msg.get("content", ""))
                break
        return f"[fake:{model}] {last_user[:120]}"

    def _input_tokens(self, messages: list[dict[str, Any]]) -> int:
        return sum(len(_text_of(m.get("content", ""))) // 4 for m in messages)

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
        self.calls.append(
            {"messages": messages, "model": model, "tools": tools, "temperature": temperature}
        )
        content = self._next_content(messages, model)
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=self._input_tokens(messages),
            output_tokens=len(content) // 4,
            finish_reason="stop",
            latency_ms=0.0,
            provider=self.provider_name,
        )

    async def stream_complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        response = await self.complete(
            messages, model, temperature=temperature, max_tokens=max_tokens, tools=tools
        )
        # Two-chunk split keeps streaming consumers honest without
        # introducing any nondeterminism.
        midpoint = len(response.content) // 2
        for piece in (response.content[:midpoint], response.content[midpoint:]):
            if piece:
                yield StreamChunk(content=piece, model=model, provider=self.provider_name)
        yield StreamChunk(finish_reason="stop", model=model, provider=self.provider_name)

    async def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=self.default_model,
                name="Fake Model",
                provider=self.provider_name,
                context_window=128000,
                max_output_tokens=4096,
            )
        ]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, status="healthy", latency_ms=0.0)
