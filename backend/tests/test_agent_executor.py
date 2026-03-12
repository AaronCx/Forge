from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_executor import AgentRunner


@pytest.mark.asyncio
async def test_execute_single_step():
    runner = AgentRunner()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test output"
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 50

    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

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
    runner = AgentRunner()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Step result"
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 30

    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

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
    runner = AgentRunner()

    tools = runner._resolve_tools(["web_search", "summarizer"])
    assert len(tools) == 2

    tools = runner._resolve_tools(["nonexistent_tool"])
    assert len(tools) == 0

    tools = runner._resolve_tools([])
    assert len(tools) == 0
