"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)

ANTHROPIC_MODELS: dict[str, dict[str, Any]] = {
    "claude-opus-4-20250514": {"context_window": 200000, "max_output": 16000},
    "claude-sonnet-4-20250514": {"context_window": 200000, "max_output": 16000},
    "claude-haiku-4-20250506": {"context_window": 200000, "max_output": 16000},
    "claude-3-5-sonnet-20241022": {"context_window": 200000, "max_output": 8192},
    "claude-3-5-haiku-20241022": {"context_window": 200000, "max_output": 8192},
}


def _convert_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert OpenAI-format messages to Anthropic format.

    Returns (system_prompt, messages) where system is extracted
    from any role="system" message.
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, Any]] = []

    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    return "\n\n".join(system_parts), anthropic_messages


def _convert_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-format tool definitions to Anthropic format."""
    anthropic_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            fn = tool["function"]
            anthropic_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
    return anthropic_tools


class AnthropicProvider(LLMProvider):
    """Anthropic API provider (Claude models)."""

    provider_name = "anthropic"
    default_model = "claude-haiku-4-5"

    def __init__(self, api_key: str | None = None) -> None:
        self.client = AsyncAnthropic(api_key=api_key)

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
        system_prompt, anthropic_msgs = _convert_messages_to_anthropic(messages)

        start = time.monotonic()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        response = await self.client.messages.create(**kwargs)
        elapsed = (time.monotonic() - start) * 1000

        # Extract text from content blocks
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "end_turn",
            latency_ms=elapsed,
            provider=self.provider_name,
            raw_response=response,
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
        system_prompt, anthropic_msgs = _convert_messages_to_anthropic(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(
                    content=text,
                    model=model,
                    provider=self.provider_name,
                )
            # Final chunk with finish reason
            final = await stream.get_final_message()
            yield StreamChunk(
                content="",
                finish_reason=final.stop_reason or "end_turn",
                model=model,
                provider=self.provider_name,
            )

    async def count_tokens(self, text: str, model: str) -> int:
        # Anthropic doesn't expose a tokenizer — estimate at ~4 chars per token
        return len(text) // 4

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.provider_name,
                context_window=meta["context_window"],
                max_output_tokens=meta["max_output"],
            )
            for model_id, meta in ANTHROPIC_MODELS.items()
        ]

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            # Minimal request to check connectivity
            await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            elapsed = (time.monotonic() - start) * 1000
            return ProviderHealth(
                provider=self.provider_name,
                status="healthy",
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ProviderHealth(
                provider=self.provider_name,
                status="unavailable",
                latency_ms=elapsed,
                error=str(e),
            )
