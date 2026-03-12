"""Embedding service — generates vector embeddings via OpenAI API."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


async def generate_embeddings(
    texts: list[str],
    *,
    model: str = "text-embedding-3-small",
) -> list[list[float]]:
    """Generate embeddings for a batch of texts via OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set — required for embeddings")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()

    embeddings: list[list[float]] = []
    for item in sorted(data["data"], key=lambda x: x["index"]):
        embeddings.append(item["embedding"])

    return embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    result: float = dot / (norm_a * norm_b)
    return result
