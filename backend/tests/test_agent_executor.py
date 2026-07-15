"""AgentRunner tests — the Forge-native kernel loop (Phase 8 removed LangChain)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import LLMResponse
from app.services.agent_executor import AgentRunner


def _resp(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="gpt-4o-mini", input_tokens=20,
                       output_tokens=30, finish_reason="stop", latency_ms=1.0, provider="openai")


@pytest.mark.asyncio
async def test_execute_single_step():
    # A no-tools agent takes the cache-aware provider_registry.complete seam.
    with patch("app.services.agent_executor.provider_registry") as reg:
        reg.complete = AsyncMock(return_value=_resp("Test output"))
        reg.default_model = "gpt-4o-mini"
        runner = AgentRunner()
        config = {"name": "Test Agent", "system_prompt": "You are a test agent.",
                  "tools": [], "workflow_steps": []}
        events = [e async for e in runner.execute(config, "Hello")]

    token_event = next(e for e in events if e["type"] == "token")
    assert token_event["content"] == "Test output"


@pytest.mark.asyncio
async def test_execute_multi_step():
    with patch("app.services.agent_executor.provider_registry") as reg:
        reg.complete = AsyncMock(return_value=_resp("Step result"))
        reg.default_model = "gpt-4o-mini"
        runner = AgentRunner()
        config = {"name": "Multi-Step Agent", "system_prompt": "You are a test agent.",
                  "tools": [], "workflow_steps": ["Step one", "Step two", "Step three"]}
        events = [e async for e in runner.execute(config, "Process this")]

    token_events = [e for e in events if e["type"] == "token"]
    step_events = [e for e in events if e["type"] == "step"]
    assert len(token_events) == 3  # one output per step
    assert len(step_events) >= 7  # start + (step_start + step_complete) * 3


@pytest.mark.asyncio
async def test_resolve_tools_native_maps_names_to_specs(db_unused=None):
    # Tool names resolve to ToolPlane ToolSpecs (builtins + node.*); unknown names
    # are dropped rather than failing the run.
    runner = AgentRunner(user_id="u1")
    specs = await runner._resolve_tools_native(["web_search", "node.json_validator"], "u1")
    names = {s.name for s in specs}
    assert "web_search" in names
    assert "node.json_validator" in names

    assert await runner._resolve_tools_native(["nonexistent_tool"], "u1") == []
    assert await runner._resolve_tools_native([], "u1") == []
