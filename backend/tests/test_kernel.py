"""Kernel tests — block types, model cards, and lossless OpenAI round-trips."""

from __future__ import annotations

import pytest

from app.kernel.convert import (
    from_openai_messages,
    to_openai_messages,
)
from app.kernel.models import ModelCard, load_model_cards
from app.kernel.types import (
    ImageBlock,
    KMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    TurnResult,
    Usage,
)

# --- round-trip cases: OpenAI -> kernel -> OpenAI is lossless ---

TEXT_ONLY = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello there."},
    {"role": "assistant", "content": "Hi! How can I help?"},
]

IMAGE_CASE = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ],
    },
]

IMAGE_URL_CASE = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe:"},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
        ],
    },
]

TOOL_USE_CASE = [
    {"role": "user", "content": "What's the weather in Paris?"},
    {
        "role": "assistant",
        "content": "Let me check.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ],
    },
]

TOOL_RESULT_CASE = [
    {"role": "tool", "tool_call_id": "call_1", "content": "18C and sunny"},
]


@pytest.mark.parametrize(
    "messages",
    [TEXT_ONLY, IMAGE_CASE, IMAGE_URL_CASE, TOOL_USE_CASE, TOOL_RESULT_CASE],
    ids=["text", "image_data", "image_url", "tool_use", "tool_result"],
)
def test_openai_round_trip_is_lossless(messages):
    kernel = from_openai_messages(messages)
    back = to_openai_messages(kernel)
    assert back == messages


def test_from_openai_produces_expected_blocks():
    kernel = from_openai_messages(TOOL_USE_CASE)
    assistant = kernel[1]
    assert assistant.role == "assistant"
    assert isinstance(assistant.blocks[0], TextBlock)
    tool_use = assistant.blocks[1]
    assert isinstance(tool_use, ToolUseBlock)
    assert tool_use.name == "get_weather"
    assert tool_use.input == {"city": "Paris"}


def test_image_data_uri_parsed_into_media_type_and_data():
    kernel = from_openai_messages(IMAGE_CASE)
    image = kernel[0].blocks[1]
    assert isinstance(image, ImageBlock)
    assert image.media_type == "image/png"
    assert image.data == "QUJD"
    assert image.url is None


def test_tool_result_round_trip_via_kernel():
    kernel = from_openai_messages(TOOL_RESULT_CASE)
    assert kernel[0].role == "tool"
    result = kernel[0].blocks[0]
    assert isinstance(result, ToolResultBlock)
    assert result.tool_use_id == "call_1"
    assert result.output == "18C and sunny"


def test_kernel_to_openai_round_trip():
    # kernel -> OpenAI -> kernel is also stable for a mixed message set.
    original = [
        KMessage(role="user", blocks=[TextBlock("hi")]),
        KMessage(
            role="assistant",
            blocks=[ToolUseBlock(id="c1", name="f", input={"a": 1})],
        ),
        KMessage(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", output="ok")]),
    ]
    assert from_openai_messages(to_openai_messages(original)) == original


# --- TurnResult convenience views ---


def test_turn_result_text_and_tool_calls():
    turn = TurnResult(
        blocks=[TextBlock("Hello "), TextBlock("world"), ToolUseBlock(id="c", name="f")],
        stop_reason="tool_use",
        usage=Usage(input_tokens=3, output_tokens=5),
        model="fake-model",
        provider="fake",
    )
    assert turn.text == "Hello world"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "f"


# --- model cards ---


def test_models_json_validates_against_model_card():
    cards = load_model_cards()
    assert len(cards) >= 15
    for card in cards.values():
        assert isinstance(card, ModelCard)
        assert card.id and card.provider and card.display_name
        assert card.context_window > 0
        assert card.max_output > 0
    # A representative from each provider family is present.
    providers = {c.provider for c in cards.values()}
    assert {"openai", "anthropic", "google", "ollama"} <= providers


def test_per_user_override_merges_and_adds():
    overrides = [
        {"id": "gpt-4o-mini", "display_name": "My Mini"},  # partial override
        {
            "id": "custom-local",
            "provider": "ollama",
            "display_name": "Custom Local",
            "context_window": 4096,
            "max_output": 1024,
        },
    ]
    cards = load_model_cards(overrides)
    assert cards["gpt-4o-mini"].display_name == "My Mini"
    # untouched base fields survive the partial override
    assert cards["gpt-4o-mini"].context_window == 128000
    assert "custom-local" in cards
    assert cards["custom-local"].provider == "ollama"


def test_incomplete_new_override_is_skipped():
    # A new id lacking required fields must not create a broken card.
    cards = load_model_cards([{"id": "broken-new", "display_name": "Nope"}])
    assert "broken-new" not in cards


# --- Phase 9: workflow orchestration types ---


def test_workflow_spec_round_trips_through_dicts():
    from app.kernel.serialize import workflow_spec_from_dict, workflow_spec_to_dict
    from app.kernel.types import BudgetSpec, SubAgentSpec, WorkflowSpec, WorkflowStage

    spec = WorkflowSpec(
        title="Audit routers",
        rationale="One scout per router file, then verify.",
        stages=[
            WorkflowStage(
                id="scout",
                kind="fanout",
                agents=[
                    SubAgentSpec(
                        role="scout",
                        prompt="Audit router X for missing auth checks.",
                        tools=["workspace.read", "workspace.search"],
                        budget=BudgetSpec(max_tokens=20000, max_seconds=120),
                        success_criteria="Cites each unauthenticated route.",
                        inputs={"file": "routers/x.py"},
                        outputs=["findings"],
                    )
                ],
                concurrency=2,
            ),
            WorkflowStage(id="check", kind="verify", depends_on=["scout"]),
        ],
        max_concurrent=4,
        worker_model="gpt-4o-mini",
    )
    assert workflow_spec_from_dict(workflow_spec_to_dict(spec)) == spec
    assert spec.agent_count == 1


def test_workflow_spec_from_dict_tolerates_sloppy_planner_output():
    from app.kernel.serialize import workflow_spec_from_dict

    spec = workflow_spec_from_dict({
        "title": "T",
        "stages": [
            {"id": "s1", "kind": "not-a-kind", "agents": [{"prompt": "p", "tools": 42}]},
            "not-a-stage",
        ],
        "max_concurrent": None,
    })
    assert spec.stages[0].kind == "single"          # unknown kind demoted
    assert spec.stages[0].agents[0].tools == "inherit"  # bad tools demoted
    assert len(spec.stages) == 1                     # non-dict stage dropped
    assert spec.max_concurrent == 16                 # None → default


def test_workflow_spec_json_schema_is_generated_from_dataclasses():
    from app.kernel.serialize import workflow_spec_json_schema

    schema = workflow_spec_json_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["title"]
    props = schema["properties"]
    assert props["max_concurrent"] == {"type": "integer"}
    assert props["verify"] == {"type": "boolean"}
    stage = props["stages"]["items"]
    assert stage["required"] == ["id"]
    assert stage["properties"]["kind"]["enum"] == ["fanout", "single", "verify", "reduce"]
    agent = stage["properties"]["agents"]["items"]
    assert set(agent["required"]) == {"role", "prompt"}
    # tools is list[str] | "inherit"
    assert "anyOf" in agent["properties"]["tools"]
    # nested budget object is generated too
    assert agent["properties"]["budget"]["properties"]["max_tokens"]["type"] == "integer"


def test_workflow_events_are_stream_events():
    import typing

    from app.kernel.types import (
        StreamEvent,
        WorkflowDone,
        WorkflowPlanProposed,
        WorkflowProgress,
        WorkflowSpec,
    )

    members = typing.get_args(StreamEvent)
    assert WorkflowPlanProposed in members
    assert WorkflowProgress in members
    assert WorkflowDone in members
    ev = WorkflowPlanProposed(spec=WorkflowSpec(title="t"), estimated_tokens=1000)
    assert ev.kind == "workflow_plan_proposed"
    assert WorkflowDone(status="cancelled").kind == "workflow_done"
