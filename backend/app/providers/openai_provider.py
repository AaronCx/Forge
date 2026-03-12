"""OpenAI provider implementation."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import tiktoken
from openai import AsyncOpenAI

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)

# Known OpenAI models with metadata
OPENAI_MODELS: dict[str, dict[str, Any]] = {
    "gpt-4o": {"context_window": 128000, "max_output": 16384},
    "gpt-4o-mini": {"context_window": 128000, "max_output": 16384},
    "gpt-4-turbo": {"context_window": 128000, "max_output": 4096},
    "gpt-3.5-turbo": {"context_window": 16385, "max_output": 4096},
    "o1": {"context_window": 200000, "max_output": 100000},
    "o1-mini": {"context_window": 128000, "max_output": 65536},
    "o3-mini": {"context_window": 200000, "max_output": 100000},
}


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-4o, GPT-4, etc.)."""

    provider_name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
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
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self.client.models.list()
            models = []
            for m in response.data:
                meta = OPENAI_MODELS.get(m.id, {})
                if m.id.startswith("gpt-") or m.id.startswith("o1") or m.id.startswith("o3"):
                    models.append(
                        ModelInfo(
                            id=m.id,
                            name=m.id,
                            provider=self.provider_name,
                            context_window=meta.get("context_window"),
                            max_output_tokens=meta.get("max_output"),
                        )
                    )
            return sorted(models, key=lambda m: m.id)
        except Exception:
            # Fallback to known models
            return [
                ModelInfo(
                    id=k,
                    name=k,
                    provider=self.provider_name,
                    context_window=v["context_window"],
                    max_output_tokens=v["max_output"],
                )
                for k, v in OPENAI_MODELS.items()
            ]

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
