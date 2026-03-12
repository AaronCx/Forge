"""Context assembly pipeline — gathers, scores, and prunes context for agent nodes."""

from __future__ import annotations

import re
from typing import Any


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def _score_relevance(text: str, keywords: list[str]) -> float:
    """Score a text chunk for relevance using keyword matching."""
    if not keywords:
        return 1.0

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / len(keywords) if keywords else 0.0


def _extract_keywords(objective: str) -> list[str]:
    """Extract simple keywords from the objective for relevance scoring."""
    # Remove common stop words and split
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "and", "or", "but", "not", "this",
        "that", "it", "its", "as", "if", "then", "than", "so", "up", "out",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", objective.lower())
    return [w for w in words if w not in stop_words]


def assemble_context(
    upstream_outputs: dict[str, dict[str, Any]],
    *,
    context_config: dict[str, Any] | None = None,
    objective: str = "",
    max_tokens: int = 0,
) -> str:
    """
    Assemble context from upstream deterministic node outputs.

    1. Gathers all upstream outputs
    2. Scores each piece for relevance (keyword matching)
    3. Prunes to fit within token budget
    4. Returns assembled context string
    """
    config = context_config or {}
    budget = max_tokens or config.get("max_context_tokens", 8000)
    keywords = _extract_keywords(objective)

    # Collect context pieces with relevance scores
    pieces: list[tuple[float, str, str]] = []  # (score, node_id, text)

    for node_id, output in upstream_outputs.items():
        # Extract text from various output shapes
        text = ""
        if isinstance(output, dict):
            # Check common output keys
            for key in ("text", "rendered", "formatted", "result", "summary", "code"):
                if key in output and output[key]:
                    text = str(output[key])
                    break
            # Handle chunks
            if "chunks" in output and isinstance(output["chunks"], list):
                text = "\n\n".join(str(c) for c in output["chunks"])
        elif isinstance(output, str):
            text = output

        if not text:
            continue

        score = _score_relevance(text, keywords)
        pieces.append((score, node_id, text))

    # Sort by relevance (highest first)
    pieces.sort(key=lambda x: x[0], reverse=True)

    # Prune to fit within token budget
    assembled_parts: list[str] = []
    total_tokens = 0

    for score, node_id, text in pieces:
        text_tokens = _estimate_tokens(text)

        if total_tokens + text_tokens > budget:
            # Truncate this piece to fit remaining budget
            remaining = budget - total_tokens
            if remaining > 100:  # Only include if meaningful
                char_limit = remaining * 4
                text = text[:char_limit] + "... [truncated]"
                assembled_parts.append(f"--- {node_id} ---\n{text}")
            break

        assembled_parts.append(f"--- {node_id} ---\n{text}")
        total_tokens += text_tokens

    return "\n\n".join(assembled_parts)
