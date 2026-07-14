"""Phase 2 — provider adapters speak kernel.

Exercises turn()/stream_turn() across OpenAI, Anthropic, Google, and Ollama with
mocked transports (no live keys): the same two-tool conversation must yield
structurally identical TurnResults, a full tool round trip must convert
correctly, and a streaming tool call must surface the right StreamEvents.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.kernel.types import (
    KMessage,
    TextBlock,
    TextDelta,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    ToolUseDelta,
    ToolUseStart,
    TurnDone,
    UsageEvent,
)
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.google_provider import GoogleProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider

TWO_TOOLS = [
    ToolSpec(name="get_weather", description="Weather", input_schema={"type": "object"}),
    ToolSpec(name="get_time", description="Time", input_schema={"type": "object"}),
]

CONVO = [
    KMessage(role="system", blocks=[TextBlock("You are helpful.")]),
    KMessage(role="user", blocks=[TextBlock("Weather and time in Paris?")]),
]


# --- fake transport responses (two tool calls, usage 10/5) ---


def _fake_openai_response():
    def tool_call(cid, name, args):
        return SimpleNamespace(
            id=cid, type="function", function=SimpleNamespace(name=name, arguments=args)
        )

    message = SimpleNamespace(
        content=None,
        tool_calls=[
            tool_call("c1", "get_weather", '{"city": "Paris"}'),
            tool_call("c2", "get_time", '{"tz": "UTC"}'),
        ],
    )
    return SimpleNamespace(
        model="gpt-4o",
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _fake_anthropic_response():
    return SimpleNamespace(
        model="claude-sonnet-4-20250514",
        content=[
            SimpleNamespace(type="tool_use", id="c1", name="get_weather", input={"city": "Paris"}),
            SimpleNamespace(type="tool_use", id="c2", name="get_time", input={"tz": "UTC"}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def _fake_gemini_json():
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": "get_weather", "args": {"city": "Paris"}}},
                        {"functionCall": {"name": "get_time", "args": {"tz": "UTC"}}},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def _signature(turn):
    """Structural fingerprint that ignores provider-specific ids/model/latency."""
    tools = [
        (b.name, b.input) for b in turn.blocks if isinstance(b, ToolUseBlock)
    ]
    return (
        sorted(tools),
        turn.stop_reason,
        turn.usage.input_tokens,
        turn.usage.output_tokens,
    )


@pytest.mark.asyncio
async def test_two_tool_conversation_is_structurally_identical_across_adapters():
    openai = OpenAIProvider(api_key="x")
    anthropic = AnthropicProvider(api_key="x")
    google = GoogleProvider(api_key="x")
    ollama = OllamaProvider(base_url="http://localhost:11434")

    with (
        patch.object(
            openai.client.chat.completions, "create",
            AsyncMock(return_value=_fake_openai_response()),
        ),
        patch.object(
            anthropic.client.messages, "create",
            AsyncMock(return_value=_fake_anthropic_response()),
        ),
        patch.object(google, "_generate", AsyncMock(return_value=_fake_gemini_json())),
        patch.object(
            ollama.client.chat.completions, "create",
            AsyncMock(return_value=_fake_openai_response()),
        ),
    ):
        turns = {
            "openai": await openai.turn(CONVO, "gpt-4o", tools=TWO_TOOLS),
            "anthropic": await anthropic.turn(CONVO, "claude-sonnet-4-20250514", tools=TWO_TOOLS),
            "google": await google.turn(CONVO, "gemini-1.5-pro", tools=TWO_TOOLS),
            # a non-carded ollama model so tools are not degraded
            "ollama": await ollama.turn(CONVO, "llama3.1:70b-tools", tools=TWO_TOOLS),
        }

    signatures = {name: _signature(t) for name, t in turns.items()}
    expected = (
        [("get_time", {"tz": "UTC"}), ("get_weather", {"city": "Paris"})],
        "tool_use",
        10,
        5,
    )
    for name, sig in signatures.items():
        assert sig == expected, f"{name} diverged: {sig}"


@pytest.mark.asyncio
async def test_ollama_degrades_gracefully_when_model_lacks_tools():
    # qwen2.5:7b-instruct is carded with tools=False.
    ollama = OllamaProvider(base_url="http://localhost:11434")
    create = AsyncMock(return_value=_fake_openai_response())
    with patch.object(ollama.client.chat.completions, "create", create):
        turn = await ollama.turn(CONVO, "qwen2.5:7b-instruct", tools=TWO_TOOLS)
    assert turn.stop_reason == "error"
    assert "does not support tool calling" in turn.text
    create.assert_not_called()  # never a silent call that would drop the tools


@pytest.mark.asyncio
async def test_full_tool_round_trip_converts_messages():
    # assistant tool_use -> tool result -> assistant final answer.
    convo = [
        KMessage(role="user", blocks=[TextBlock("Weather in Paris?")]),
        KMessage(role="assistant", blocks=[ToolUseBlock(id="c1", name="get_weather", input={"city": "Paris"})]),
        KMessage(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", output="18C sunny")]),
    ]
    final = SimpleNamespace(
        model="gpt-4o",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="It is 18C and sunny in Paris.", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=8),
    )
    openai = OpenAIProvider(api_key="x")
    create = AsyncMock(return_value=final)
    with patch.object(openai.client.chat.completions, "create", create):
        turn = await openai.turn(convo, "gpt-4o", tools=TWO_TOOLS)

    assert turn.text == "It is 18C and sunny in Paris."
    assert turn.stop_reason == "end"
    # the tool_use/tool_result messages became valid OpenAI wire shapes
    sent = create.call_args.kwargs["messages"]
    assert any(m.get("tool_calls") for m in sent)
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "c1" for m in sent)


@pytest.mark.asyncio
async def test_anthropic_tool_result_rides_in_user_turn():
    from app.providers.kernel_bridge import kmessages_to_anthropic

    convo = [
        KMessage(role="assistant", blocks=[ToolUseBlock(id="c1", name="f", input={})]),
        KMessage(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", output="done")]),
    ]
    _system, msgs = kmessages_to_anthropic(convo)
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"][0]["type"] == "tool_use"
    assert msgs[1]["role"] == "user"  # tool role has no Anthropic equivalent
    assert msgs[1]["content"][0]["type"] == "tool_result"
    assert msgs[1]["content"][0]["tool_use_id"] == "c1"


# --- streaming tool call ---


async def _fake_openai_stream():
    def chunk(content=None, tool_calls=None, finish=None, usage=None):
        delta = SimpleNamespace(content=content, tool_calls=tool_calls)
        choices = [] if usage and content is None and tool_calls is None and finish is None else [
            SimpleNamespace(delta=delta, finish_reason=finish)
        ]
        return SimpleNamespace(choices=choices, usage=usage)

    def tc(index, cid=None, name=None, args=None):
        fn = SimpleNamespace(name=name, arguments=args)
        return SimpleNamespace(index=index, id=cid, function=fn)

    yield chunk(content="Let me check. ")
    yield chunk(tool_calls=[tc(0, cid="c1", name="get_weather")])
    yield chunk(tool_calls=[tc(0, args='{"city": ')])
    yield chunk(tool_calls=[tc(0, args='"Paris"}')])
    yield chunk(finish="tool_calls")
    yield chunk(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=6))


@pytest.mark.asyncio
async def test_streaming_tool_call_emits_events_and_assembles_turn():
    openai = OpenAIProvider(api_key="x")
    with patch.object(
        openai.client.chat.completions, "create",
        AsyncMock(return_value=_fake_openai_stream()),
    ):
        events = [
            ev async for ev in openai.stream_turn(CONVO, "gpt-4o", tools=TWO_TOOLS)
        ]

    assert any(isinstance(e, TextDelta) for e in events)
    starts = [e for e in events if isinstance(e, ToolUseStart)]
    assert len(starts) == 1 and starts[0].name == "get_weather"
    assert any(isinstance(e, ToolUseDelta) for e in events)
    assert any(isinstance(e, UsageEvent) for e in events)

    done = events[-1]
    assert isinstance(done, TurnDone)
    tool_blocks = [b for b in done.turn.blocks if isinstance(b, ToolUseBlock)]
    assert tool_blocks[0].input == {"city": "Paris"}
    assert done.turn.stop_reason == "tool_use"
    assert done.turn.usage.output_tokens == 6


# --- registry routing + fallback + shim ---


@pytest.mark.asyncio
async def test_registry_resolves_via_model_card_provider():
    from app.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    anthropic = AnthropicProvider(api_key="x")
    reg.register("anthropic", anthropic)
    # gpt-4o-mini would prefix-route to openai, but no openai is registered;
    # claude-sonnet-4 is carded to anthropic, which IS registered.
    provider, model = reg.resolve_provider("claude-sonnet-4-20250514")
    assert provider is anthropic
    assert model == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_registry_turn_no_fallback_on_client_error():
    from app.providers.registry import FallbackPolicy, ProviderRegistry

    reg = ProviderRegistry()
    good = OpenAIProvider(api_key="x")
    bad = AnthropicProvider(api_key="x")
    reg.register("anthropic", bad, default=False)
    reg.register("openai", good, default=True)

    err = Exception("bad request")
    err.status_code = 400  # type: ignore[attr-defined]
    with (
        patch.object(bad, "turn", AsyncMock(side_effect=err)),
        patch.object(good, "turn", AsyncMock(return_value="should-not-be-used")),
        pytest.raises(Exception, match="bad request"),
    ):
        await reg.turn(CONVO, "claude-sonnet-4-20250514",
                       policy=FallbackPolicy(enabled=True, exclude_client_errors=True))


@pytest.mark.asyncio
async def test_turn_result_to_llm_response_shim():
    from app.kernel.types import TurnResult, Usage
    from app.providers.kernel_bridge import turn_result_to_llm_response

    turn = TurnResult(
        blocks=[TextBlock("Hello "), TextBlock("world")],
        stop_reason="end",
        usage=Usage(input_tokens=3, output_tokens=2),
        model="gpt-4o",
        provider="openai",
    )
    resp = turn_result_to_llm_response(turn)
    assert resp.content == "Hello world"
    assert resp.finish_reason == "stop"
    assert (resp.input_tokens, resp.output_tokens) == (3, 2)
