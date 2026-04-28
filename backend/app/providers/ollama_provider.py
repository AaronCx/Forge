"""Ollama (local) provider — uses OpenAI-compatible API at localhost:11434."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)


class OllamaProvider(LLMProvider):
    """Ollama local model provider (OpenAI-compatible API)."""

    provider_name = "ollama"
    # Used when the registry falls back to this provider with no specific model
    # in scope. Tool-calling-capable and reasonable on Apple Silicon.
    default_model = "qwen2.5:7b-instruct"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        # Ollama exposes an OpenAI-compatible endpoint at /v1
        self.client = AsyncOpenAI(
            api_key="ollama",  # Ollama doesn't need a real key
            base_url=f"{self.base_url}/v1",
        )

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
        # Ollama doesn't expose a tokenizer — estimate
        return len(text) // 4

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                resp.raise_for_status()
                data = resp.json()

            return [
                ModelInfo(
                    id=m["name"],
                    name=m["name"],
                    provider=self.provider_name,
                    supports_tools=False,  # Most Ollama models don't support tools
                )
                for m in data.get("models", [])
            ]
        except Exception:
            return []

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                resp.raise_for_status()
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
