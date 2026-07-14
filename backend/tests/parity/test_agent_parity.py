"""Parity golden test: freeze AgentRunner.execute's ordered SSE event stream.

Runs a no-tools, two-step agent end to end against a canned provider response
and snapshots the full ordered list of ``{"type": "step"|"token", ...}`` events
emitted by ``agent_executor.py``. Phase 4 must keep this legacy subsequence
byte-identical when ``FORGE_NATIVE_LOOP`` is off.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.base import LLMResponse

from ._harness import assert_golden


def _canned_registry() -> MagicMock:
    registry = MagicMock()
    registry.default_model = "gpt-4o-mini"
    registry.complete = AsyncMock(
        return_value=LLMResponse(
            content="This is the model's answer for the step.",
            model="gpt-4o-mini",
            input_tokens=7,
            output_tokens=11,
            finish_reason="stop",
            latency_ms=0.0,
            provider="openai",
        )
    )
    return registry


@pytest.mark.asyncio
async def test_agent_execute_event_stream_matches_golden():
    from app.services.agent_executor import AgentRunner

    agent_config = {
        "id": "agent-1",
        "name": "Parity Agent",
        "system_prompt": "You are a helpful assistant.",
        "tools": [],
        "workflow_steps": ["Understand the request.", "Produce the answer."],
    }

    with (
        patch("app.services.agent_executor.provider_registry", _canned_registry()),
        patch("app.services.tailoring.load_custom_instructions", return_value=""),
    ):
        runner = AgentRunner(user_id=None)
        events = [event async for event in runner.execute(agent_config, "Hello there")]

    assert_golden("agent_execute_stream", events)
