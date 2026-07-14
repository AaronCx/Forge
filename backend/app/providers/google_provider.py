"""Google (Gemini) provider — native Generative Language REST API.

Implemented over httpx rather than the google-generativeai SDK to stay
dependency-light and easily mockable in tests. Supports text, inline base64
images, tool (function) calling, and streaming, so a Gemini agent is a
first-class kernel citizen.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

_FINISH_MAP = {
    "STOP": "end",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "error",
    "RECITATION": "error",
    "OTHER": "end",
}


def _openai_to_contents(
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Convert OpenAI-format messages to (systemInstruction, contents)."""
    system_parts: list[dict[str, Any]] = []
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        text = content if isinstance(content, str) else json.dumps(content)
        if role == "system":
            system_parts.append({"text": text})
        elif role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.get("tool_call_id", "tool"),
                                "response": {"result": text},
                            }
                        }
                    ],
                }
            )
        else:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
    system = {"parts": system_parts} if system_parts else None
    return system, contents


class GoogleProvider(LLMProvider):
    """Google Gemini provider via the Generative Language REST API."""

    provider_name = "google"
    default_model = "gemini-1.5-flash"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or ""
        self.base_url = (base_url or _GEMINI_BASE).rstrip("/")

    # --- HTTP plumbing ---

    def _url(self, model: str, method: str, *, sse: bool = False) -> str:
        suffix = "?alt=sse&key=" if sse else "?key="
        return f"{self.base_url}/models/{model}:{method}{suffix}{self.api_key}"

    async def _generate(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self._url(model, "generateContent"), json=body)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    @staticmethod
    def _build_body(
        contents: list[dict[str, Any]],
        system: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = system
        if tools:
            body["tools"] = tools
        return body

    @staticmethod
    def _text_and_usage(data: dict[str, Any]) -> tuple[str, str, int, int]:
        candidates = data.get("candidates") or [{}]
        cand = candidates[0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        finish = cand.get("finishReason", "STOP")
        usage = data.get("usageMetadata", {})
        return (
            text,
            finish,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
        )

    # --- legacy interface ---

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
        system, contents = _openai_to_contents(messages)
        body = self._build_body(contents, system, None, temperature, max_tokens)
        start = time.monotonic()
        data = await self._generate(model, body)
        elapsed = (time.monotonic() - start) * 1000
        text, finish, in_tok, out_tok = self._text_and_usage(data)
        return LLMResponse(
            content=text,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            finish_reason=finish,
            latency_ms=elapsed,
            provider=self.provider_name,
            raw_response=data,
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
        system, contents = _openai_to_contents(messages)
        body = self._build_body(contents, system, None, temperature, max_tokens)
        async with httpx.AsyncClient(timeout=60) as client, client.stream(
            "POST", self._url(model, "streamGenerateContent", sse=True), json=body
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                text, finish, _, _ = self._text_and_usage(data)
                yield StreamChunk(
                    content=text,
                    finish_reason=_FINISH_MAP.get(finish),
                    model=model,
                    provider=self.provider_name,
                )

    # --- kernel interface (native tool/image support) ---

    async def turn(
        self,
        messages: list[Any],
        model: str,
        *,
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Any:
        from app.kernel.types import TextBlock, ToolUseBlock, TurnResult, Usage

        system, contents = self._kernel_to_contents(messages)
        gemini_tools = self._kernel_tools(tools)
        body = self._build_body(contents, system, gemini_tools, temperature, max_tokens)
        start = time.monotonic()
        data = await self._generate(model, body)
        elapsed = (time.monotonic() - start) * 1000

        candidates = data.get("candidates") or [{}]
        cand = candidates[0]
        parts = cand.get("content", {}).get("parts", [])
        blocks: list[Any] = []
        has_tool = False
        for i, part in enumerate(parts):
            if "text" in part:
                blocks.append(TextBlock(part["text"]))
            elif "functionCall" in part:
                has_tool = True
                fc = part["functionCall"]
                blocks.append(
                    ToolUseBlock(
                        id=f"{fc.get('name', 'call')}_{i}",
                        name=fc.get("name", ""),
                        input=dict(fc.get("args") or {}),
                    )
                )
        finish = cand.get("finishReason", "STOP")
        stop = "tool_use" if has_tool else _FINISH_MAP.get(finish, "end")
        usage = data.get("usageMetadata", {})
        return TurnResult(
            blocks=blocks,
            stop_reason=stop,  # type: ignore[arg-type]
            usage=Usage(
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
            ),
            model=model,
            provider=self.provider_name,
            latency_ms=elapsed,
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
        from app.kernel.types import TextBlock, TextDelta, TurnDone

        # Gemini's SSE tool-call framing is awkward; derive a faithful turn once
        # and surface its text incrementally plus a terminal TurnDone.
        turn = await self.turn(
            messages, model, tools=tools, temperature=temperature, max_tokens=max_tokens
        )
        for block in turn.blocks:
            if isinstance(block, TextBlock) and block.text:
                yield TextDelta(text=block.text)
        yield TurnDone(turn=turn)

    def _kernel_to_contents(
        self, messages: list[Any]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        from app.kernel.types import (
            ImageBlock,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        system_parts: list[dict[str, Any]] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                for b in m.blocks:
                    if isinstance(b, TextBlock):
                        system_parts.append({"text": b.text})
                continue
            role = "model" if m.role == "assistant" else "user"
            parts: list[dict[str, Any]] = []
            for b in m.blocks:
                if isinstance(b, TextBlock):
                    parts.append({"text": b.text})
                elif isinstance(b, ImageBlock) and b.data is not None:
                    parts.append(
                        {"inline_data": {"mime_type": b.media_type or "image/png", "data": b.data}}
                    )
                elif isinstance(b, ToolUseBlock):
                    parts.append({"functionCall": {"name": b.name, "args": b.input}})
                elif isinstance(b, ToolResultBlock):
                    out = b.output if isinstance(b.output, dict) else {"result": b.output}
                    parts.append(
                        {"functionResponse": {"name": b.tool_use_id, "response": out}}
                    )
            contents.append({"role": role, "parts": parts})
        system = {"parts": system_parts} if system_parts else None
        return system, contents

    @staticmethod
    def _kernel_tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        declarations = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema or {"type": "object", "properties": {}},
            }
            for t in tools
        ]
        return [{"functionDeclarations": declarations}]

    async def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4

    async def list_models(self) -> list[ModelInfo]:
        # Data-driven: surface the Google cards from the kernel model catalog.
        from app.kernel.models import load_base_model_cards

        return [
            ModelInfo(
                id=card.id,
                name=card.display_name,
                provider=self.provider_name,
                context_window=card.context_window,
                max_output_tokens=card.max_output,
                supports_tools=card.tools,
            )
            for card in load_base_model_cards().values()
            if card.provider == "google"
        ]

    async def health_check(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/models?key={self.api_key}")
                resp.raise_for_status()
            return ProviderHealth(
                provider=self.provider_name,
                status="healthy",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ProviderHealth(
                provider=self.provider_name,
                status="unavailable",
                latency_ms=(time.monotonic() - start) * 1000,
                error=str(e),
            )
