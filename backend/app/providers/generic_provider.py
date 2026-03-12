"""Generic OpenAI-compatible provider (LM Studio, vLLM, Groq, Together, etc.)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)


class GenericOpenAIProvider(LLMProvider):
    """Generic OpenAI-compatible API provider.

    Works with any service that implements the OpenAI chat completions API:
    LM Studio, vLLM, Groq, Together AI, Fireworks, etc.
    """

    provider_name = "generic"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider_name: str = "generic",
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        start = time.monotonic()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self.client.chat.completions.create(**kwargs)
        elapsed = (time.monotonic() - start) * 1000

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            finish_reason=choice.finish_reason or "stop",
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
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            yield StreamChunk(
                content=delta.content or "",
                finish_reason=chunk.choices[0].finish_reason,
                model=model,
                provider=self.provider_name,
            )

    async def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self.client.models.list()
            return [
                ModelInfo(
                    id=m.id,
                    name=m.id,
                    provider=self.provider_name,
                )
                for m in response.data
            ]
        except Exception:
            return []

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            await self.client.models.list()
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
