"""FakeProvider conformance — deterministic, interface-complete test double."""

from __future__ import annotations

import pytest

from app.providers.base import LLMProvider, LLMResponse
from app.providers.fake_provider import FakeProvider

_MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "What is 2 + 2?"},
]


def test_fake_provider_is_llm_provider():
    assert isinstance(FakeProvider(), LLMProvider)


@pytest.mark.asyncio
async def test_canned_responses_served_in_order():
    provider = FakeProvider(responses=["first", "second"])
    r1 = await provider.complete(_MESSAGES, "fake-model")
    r2 = await provider.complete(_MESSAGES, "fake-model")
    assert (r1.content, r2.content) == ("first", "second")
    assert isinstance(r1, LLMResponse)
    assert r1.latency_ms == 0.0
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_echo_is_deterministic_when_queue_empty():
    a = await FakeProvider().complete(_MESSAGES, "fake-model")
    b = await FakeProvider().complete(_MESSAGES, "fake-model")
    assert a.content == b.content == "[fake:fake-model] What is 2 + 2?"


@pytest.mark.asyncio
async def test_stream_reassembles_to_full_content():
    provider = FakeProvider(responses=["hello world"])
    chunks = [c.content async for c in provider.stream_complete(_MESSAGES, "fake-model")]
    assert "".join(chunks) == "hello world"
