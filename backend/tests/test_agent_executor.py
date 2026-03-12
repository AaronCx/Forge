from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import LLMResponse
from app.services.agent_executor import AgentRunner


@pytest.mark.asyncio
async def test_execute_single_step():
    mock_response = LLMResponse(
        content="Test output",
        model="gpt-4o-mini",
        input_tokens=20,
        output_tokens=30,
        finish_reason="stop",
        latency_ms=100,
        provider="openai",
    )

    with patch("app.services.agent_executor.provider_registry") as mock_registry:
        mock_registry.complete = AsyncMock(return_value=mock_response)
        mock_registry.default_model = "gpt-4o-mini"

        runner = AgentRunner()
        config = {
            "name": "Test Agent",
            "system_prompt": "You are a test agent.",
            "tools": [],
            "workflow_steps": [],
        }

        events = []
        async for event in runner.execute(config, "Hello"):
            events.append(event)

        assert len(events) >= 3  # start, step, token, complete
        assert any(e["type"] == "token" for e in events)
        token_event = next(e for e in events if e["type"] == "token")
        assert token_event["content"] == "Test output"


@pytest.mark.asyncio
async def test_execute_multi_step():
    mock_response = LLMResponse(
        content="Step result",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=20,
        finish_reason="stop",
        latency_ms=50,
        provider="openai",
    )

    with patch("app.services.agent_executor.provider_registry") as mock_registry:
        mock_registry.complete = AsyncMock(return_value=mock_response)
        mock_registry.default_model = "gpt-4o-mini"

        runner = AgentRunner()
        config = {
            "name": "Multi-Step Agent",
            "system_prompt": "You are a test agent.",
            "tools": [],
            "workflow_steps": ["Step one", "Step two", "Step three"],
        }

        events = []
        async for event in runner.execute(config, "Process this"):
            events.append(event)

        step_events = [e for e in events if e["type"] == "step"]
        token_events = [e for e in events if e["type"] == "token"]

        assert len(token_events) == 3  # One output per step
        assert len(step_events) >= 7  # start + (step_start + step_complete) * 3


def test_resolve_tools():
    with patch("app.services.agent_executor.provider_registry") as mock_registry:
        mock_registry.default_model = "gpt-4o-mini"
        runner = AgentRunner()

    lc_tools, mcp_tools = runner._resolve_tools(["web_search", "summarizer"])
    assert len(lc_tools) == 2
    assert len(mcp_tools) == 0

    lc_tools, mcp_tools = runner._resolve_tools(["nonexistent_tool"])
    assert len(lc_tools) == 0
    assert len(mcp_tools) == 1  # treated as potential MCP tool

    lc_tools, mcp_tools = runner._resolve_tools([])
    assert len(lc_tools) == 0
    assert len(mcp_tools) == 0
