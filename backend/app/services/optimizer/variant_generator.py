"""Prompt-variant generation for the self-optimization loop.

Variant generation is a single model call: given the current system prompt and a
transcript of the failing eval cases, ask the model for N improved prompts. The
generator is an injectable interface so tests can supply a deterministic fake;
the default implementation calls the real backend LLM path
(``provider_registry.complete``), the same convention the eval runner uses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.providers.registry import provider_registry

logger = logging.getLogger(__name__)


@dataclass
class PromptVariant:
    """A single candidate system prompt produced by a generator."""

    system_prompt: str
    rationale: str = ""


@dataclass
class VariantRequest:
    """Inputs handed to a variant generator."""

    current_prompt: str
    failures: list[dict[str, Any]] = field(default_factory=list)
    n: int = 3
    model: str | None = None


@runtime_checkable
class VariantGenerator(Protocol):
    """Callable interface that proposes improved prompt variants.

    Implementations must be async and return between 1 and ``request.n``
    variants. Tests can supply a deterministic fake satisfying this protocol.
    """

    async def __call__(self, request: VariantRequest) -> list[PromptVariant]: ...


def _format_failures(failures: list[dict[str, Any]], *, limit: int = 10) -> str:
    """Render failing eval cases into a compact transcript for the model."""
    lines: list[str] = []
    for i, f in enumerate(failures[:limit], start=1):
        inp = f.get("input")
        expected = f.get("expected")
        actual = f.get("actual")
        reason = f.get("reason", "")
        lines.append(
            f"Case {i}:\n"
            f"  Input: {json.dumps(inp, default=str)[:500]}\n"
            f"  Expected: {json.dumps(expected, default=str)[:500]}\n"
            f"  Actual: {json.dumps(actual, default=str)[:500]}\n"
            f"  Grader: {reason}"
        )
    remaining = len(failures) - limit
    if remaining > 0:
        lines.append(f"... and {remaining} more failing case(s).")
    return "\n\n".join(lines) if lines else "(no failure detail available)"


class LLMVariantGenerator:
    """Default generator — one model call returns N improved prompts."""

    async def __call__(self, request: VariantRequest) -> list[PromptVariant]:
        system_prompt = (
            "You are a prompt engineer improving an AI agent's system prompt. "
            "You are given the agent's current system prompt and a transcript of "
            "eval cases it FAILED. Propose improved system prompts that would make "
            "the agent pass these cases while preserving its original intent. "
            f"Return strictly a JSON object: {{\"variants\": [{{\"system_prompt\": "
            "\"...\", \"rationale\": \"...\"}}]}} with exactly "
            f"{request.n} variant(s). Do not include any prose outside the JSON."
        )
        user_prompt = (
            f"Current system prompt:\n---\n{request.current_prompt}\n---\n\n"
            f"Failing eval cases:\n{_format_failures(request.failures)}\n\n"
            f"Propose {request.n} improved system prompt variant(s) as JSON."
        )

        response = await provider_registry.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=request.model,
            temperature=0.7,
        )

        return self._parse(response.content, fallback=request.current_prompt, n=request.n)

    @staticmethod
    def _parse(content: str, *, fallback: str, n: int) -> list[PromptVariant]:
        """Parse the model's JSON response into PromptVariant objects."""
        text = content.strip()
        # Tolerate fenced code blocks the model may wrap the JSON in.
        if text.startswith("```"):
            text = text.split("```", 2)[1] if "```" in text[3:] else text
            text = text.removeprefix("json").strip().strip("`").strip()

        variants: list[PromptVariant] = []
        try:
            parsed = json.loads(text)
            raw = parsed.get("variants", []) if isinstance(parsed, dict) else parsed
            for item in raw:
                if isinstance(item, dict) and item.get("system_prompt"):
                    variants.append(
                        PromptVariant(
                            system_prompt=str(item["system_prompt"]),
                            rationale=str(item.get("rationale", "")),
                        )
                    )
                elif isinstance(item, str) and item.strip():
                    variants.append(PromptVariant(system_prompt=item))
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning("Variant generator returned non-JSON; using raw content as one variant")
            if text and text != fallback:
                variants.append(PromptVariant(system_prompt=text, rationale="raw model output"))

        return variants[:n]


default_variant_generator: VariantGenerator = LLMVariantGenerator()
