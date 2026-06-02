"""Onboarding PR-4 — custom_instructions injected into the runner + dispatcher."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services import dispatcher
from app.services.agent_executor import AgentRunner
from app.services.tailoring import ABOUT_USER_MARKER

CATALOG = [
    dispatcher.CatalogEntry(type="agent", id="agent-1", name="Reviewer", description="reviews code"),
]

AGENT_CONFIG = {
    "id": "a1", "name": "Reviewer", "system_prompt": "You review code.",
    "tools": [], "workflow_steps": ["Review it."], "model": "ollama/llama3.2:3b",
}


async def _fake_step(self, system_prompt, step, user_input, context, *, model=None, image_blocks=None):
    _fake_step.captured = system_prompt  # type: ignore[attr-defined]
    return {"content": "ok", "tokens": 0, "input_tokens": 0, "output_tokens": 0,
            "latency_ms": 0, "model": model, "provider": "ollama"}


@pytest.mark.asyncio
async def test_runner_injects_custom_instructions():
    runner = AgentRunner(user_id="u1")
    with patch("app.services.tailoring.load_custom_instructions", return_value="I work in Rust, prefer terse output."), \
         patch.object(AgentRunner, "_execute_step", new=_fake_step):
        async for _ in runner.execute(AGENT_CONFIG, "hi", user_id="u1"):
            pass

    assert ABOUT_USER_MARKER in _fake_step.captured  # type: ignore[attr-defined]
    assert "I work in Rust" in _fake_step.captured  # type: ignore[attr-defined]
    assert "You review code." in _fake_step.captured  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_runner_no_block_when_instructions_empty():
    runner = AgentRunner(user_id="u1")
    with patch("app.services.tailoring.load_custom_instructions", return_value=""), \
         patch.object(AgentRunner, "_execute_step", new=_fake_step):
        async for _ in runner.execute(AGENT_CONFIG, "hi", user_id="u1"):
            pass

    assert ABOUT_USER_MARKER not in _fake_step.captured  # type: ignore[attr-defined]
    assert _fake_step.captured == "You review code."  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_dispatcher_injects_custom_instructions_into_routing():
    captured = {}

    async def fake_invoke(user_id, messages):
        captured["messages"] = messages
        return json.dumps({"action": "none"}), 1, 1, "m"

    with patch("app.services.dispatcher._invoke", new=fake_invoke), \
         patch("app.services.tailoring.load_custom_instructions", return_value="Answer in Rust terms."), \
         patch("app.services.token_tracker.token_tracker"):
        await dispatcher.route("u1", "do a thing", catalog=CATALOG)

    system_message = captured["messages"][0]["content"]
    assert ABOUT_USER_MARKER in system_message
    assert "Answer in Rust terms." in system_message


@pytest.mark.asyncio
async def test_dispatcher_no_block_when_instructions_empty():
    captured = {}

    async def fake_invoke(user_id, messages):
        captured["messages"] = messages
        return json.dumps({"action": "none"}), 1, 1, "m"

    with patch("app.services.dispatcher._invoke", new=fake_invoke), \
         patch("app.services.tailoring.load_custom_instructions", return_value=""), \
         patch("app.services.token_tracker.token_tracker"):
        await dispatcher.route("u1", "do a thing", catalog=CATALOG)

    assert ABOUT_USER_MARKER not in captured["messages"][0]["content"]
