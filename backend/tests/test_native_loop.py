"""Phase 4 — Forge-native agent loop.

Asserts that with FORGE_NATIVE_LOOP on, the legacy step/token event subsequence
is byte-identical to the flag-off path (and the Phase-0 golden), that a tool
loop streams rich events and records time-travel, and that the loop drives tools
through the plane to completion.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.kernel.types import (
    KMessage,
    TextBlock,
    TextDelta,
    ToolUseBlock,
    ToolUseStart,
    TurnDone,
    TurnResult,
    Usage,
    UsageEvent,
)

GOLDEN = Path(__file__).parent / "parity" / "golden" / "agent_execute_stream.json"

AGENT_CONFIG = {
    "id": "agent-1",
    "name": "Parity Agent",
    "system_prompt": "You are a helpful assistant.",
    "tools": [],
    "workflow_steps": ["Understand the request.", "Produce the answer."],
}

ANSWER = "This is the model's answer for the step."


class _FakeRegistry:
    """A registry whose stream yields a fixed single final turn per call."""

    def __init__(self, turns):
        self._turns = turns
        self.calls = 0

    async def stream(self, messages, model, *, tools=None):
        events = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        for ev in events:
            yield ev


def _final_turn_events(text=ANSWER, provider="openai"):
    return [
        TextDelta(text=text),
        UsageEvent(usage=Usage(input_tokens=7, output_tokens=11)),
        TurnDone(
            turn=TurnResult(
                blocks=[TextBlock(text)],
                stop_reason="end",
                usage=Usage(input_tokens=7, output_tokens=11),
                model="gpt-4o-mini",
                provider=provider,
            )
        ),
    ]


def _legacy_subsequence(events):
    return [e for e in events if e.get("type") in ("step", "token")]


@pytest.mark.asyncio
async def test_native_loop_legacy_subsequence_matches_golden():
    # A no-tools agent on the single (native) stack still emits the exact
    # step/token subsequence captured in the Phase-0 golden.
    from app.providers.base import LLMResponse
    from app.services.agent_executor import AgentRunner

    resp = LLMResponse(
        content=ANSWER, model="gpt-4o-mini", input_tokens=7, output_tokens=11,
        finish_reason="stop", latency_ms=0.0, provider="openai",
    )
    with (
        patch("app.services.agent_executor.provider_registry") as reg,
        patch("app.services.tailoring.load_custom_instructions", return_value=""),
    ):
        reg.default_model = "gpt-4o-mini"
        reg.complete = AsyncMock(return_value=resp)
        runner = AgentRunner(user_id=None)
        events = [e async for e in runner.execute(AGENT_CONFIG, "Hello there")]

    golden = json.loads(GOLDEN.read_text())
    assert _legacy_subsequence(events) == golden


@pytest.mark.asyncio
async def test_tool_loop_streams_events_and_records_timetravel(monkeypatch):
    from app.services.agent_executor import AgentRunner
    from app.services.timetravel.recorder import RunRecorder

    monkeypatch.setenv("FORGE_NATIVE_LOOP", "1")

    # Turn 1 asks to call node.template_renderer; turn 2 (after the tool result)
    # returns the final answer.
    tool_turn = [
        ToolUseStart(id="c1", name="node.template_renderer"),
        TurnDone(
            turn=TurnResult(
                blocks=[ToolUseBlock(
                    id="c1", name="node.template_renderer",
                    input={"template": "Hi {{name}}", "variables": {"name": "Bob"}},
                )],
                stop_reason="tool_use",
                usage=Usage(input_tokens=5, output_tokens=3),
                model="gpt-4o-mini", provider="openai",
            )
        ),
    ]
    # Call 1 requests the tool; call 2 (after the tool result) is the final answer.
    fake = _FakeRegistry([tool_turn, _final_turn_events(text="Done: Hi Bob")])

    recorded = []

    class CapturingRecorder(RunRecorder):
        def __init__(self):
            super().__init__(run_id="run1", enabled=False)

        def model_turn(self, step, turn):
            recorded.append(("model_turn", turn.stop_reason))

        def tool_call_kernel(self, step, tool_use, result):
            recorded.append(("tool_call", tool_use.name, result.is_error))

    config = {**AGENT_CONFIG, "tools": ["node.template_renderer"], "workflow_steps": ["Do it."]}
    with (
        patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)),
        patch("app.services.tailoring.load_custom_instructions", return_value=""),
    ):
        runner = AgentRunner(user_id="u1", recorder=CapturingRecorder())
        events = [e async for e in runner.execute(config, "go", run_id="run1", user_id="u1")]

    types = [e["type"] for e in events]
    assert "tool_use" in types
    assert "tool_result" in types
    # the final token event carries the post-tool answer
    tokens = [e for e in events if e["type"] == "token"]
    assert tokens[-1]["content"] == "Done: Hi Bob"
    # tool result round-tripped through the plane (template rendered)
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert not tool_results[0]["is_error"]
    assert "Hi Bob" in tool_results[0]["output"]
    # time-travel captured both a model turn and the tool call
    assert ("tool_call", "node.template_renderer", False) in recorded
    assert any(r[0] == "model_turn" for r in recorded)


async def _openai_text_stream():
    from types import SimpleNamespace

    def chunk(content=None, finish=None, usage=None):
        choices = (
            [SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None), finish_reason=finish)]
            if (content is not None or finish is not None)
            else []
        )
        return SimpleNamespace(choices=choices, usage=usage)

    yield chunk(content="Answer from the real adapter.")
    yield chunk(finish="stop")
    yield chunk(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6))


@pytest.mark.asyncio
async def test_native_loop_drives_real_provider_adapter():
    # loop → registry.stream → resolve_provider → provider.stream_turn → transport
    from app.kernel.loop import run_agent_turn
    from app.providers.ollama_provider import OllamaProvider
    from app.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    ollama = OllamaProvider(base_url="http://localhost:11434")
    reg.register("ollama", ollama, default=True)

    messages = [KMessage(role="user", blocks=[TextBlock("hi")])]
    with patch.object(
        ollama.client.chat.completions, "create",
        AsyncMock(return_value=_openai_text_stream()),
    ):
        events = [
            ev async for ev in run_agent_turn(
                messages, None, "llama3.1:8b-notools",
                registry=reg, plane=None, ctx=None,
            )
        ]

    done = [e for e in events if isinstance(e, TurnDone)]
    assert done and done[0].turn.text == "Answer from the real adapter."
    assert done[0].turn.stop_reason == "end"
    assert any(isinstance(e, TextDelta) for e in events)


@pytest.mark.asyncio
async def test_loop_stops_at_max_iterations(monkeypatch):
    # A registry that always asks for a tool would loop forever without the cap.
    from app.kernel.loop import run_agent_turn

    class AlwaysToolRegistry:
        async def stream(self, messages, model, *, tools=None):
            yield TurnDone(
                turn=TurnResult(
                    blocks=[ToolUseBlock(id="c", name="node.template_renderer", input={"template": "x"})],
                    stop_reason="tool_use",
                    usage=Usage(),
                    model="m", provider="p",
                )
            )

    class NoopPlane:
        async def execute(self, tool_use, ctx):
            from app.kernel.types import ToolResultBlock

            return ToolResultBlock(tool_use_id=tool_use.id, output="ok")

    messages = [KMessage(role="user", blocks=[TextBlock("go")])]
    count = 0
    async for _ in run_agent_turn(
        messages, None, "m", registry=AlwaysToolRegistry(), plane=NoopPlane(),
        ctx=None, max_iterations=3,
    ):
        count += 1
    # 3 iterations × (1 TurnDone + 1 ToolExecuted) = 6 events, then it stops.
    assert count == 6
