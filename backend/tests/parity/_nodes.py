"""Fixed inputs and controlled mocks for executing every node type offline.

Each of the 44 registered node types is executed with deterministic inputs
against fakes (no network, no subprocess, no real LLM) so its output dict can be
snapshotted. External boundaries are mocked at the smallest seam that keeps the
executor's own output-shaping logic real:

- LLM nodes (llm_*, cu_*): ``provider_registry.complete`` returns a canned
  ``LLMResponse``.
- Steer/Drive nodes: the ``execute`` CLI shim returns a canned result.
- Agent-control nodes: the ``agent_runner`` methods return canned dicts.
- Deterministic IO nodes: the specific IO call (safe_get / extract_text /
  httpx / knowledge search) is stubbed.
- Pure deterministic nodes run with no mocks at all.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.providers.base import LLMResponse
from app.providers.registry import provider_registry

# --- canned LLM content per node (valid JSON where the executor parses it) ---

_CANNED_LLM: dict[str, str] = {
    "llm_generate": "Generated response.",
    "llm_summarize": "A concise summary of the input.",
    "llm_implement": "def add(a, b):\n    return a + b",
    "llm_extract": '{"entities": ["Alice"], "dates": ["2026-01-01"], "key_facts": []}',
    "llm_review": '[{"severity": "low", "category": "style", '
    '"description": "Prefer f-strings", "suggestion": "Use an f-string"}]',
    "cu_planner": '[{"action": "steer_see", "args": {"target": "screen"}}]',
    "cu_analyzer": '{"app": "Safari", "state": "idle", "content": "A page", '
    '"errors": [], "actions_available": [], "summary": "A page is open"}',
    "cu_verifier": '{"success": true, "confidence": 0.9, '
    '"explanation": "Objective met", "retry_actions": []}',
    "cu_error_handler": '{"diagnosis": "A dialog appeared", "recoverable": true, '
    '"recovery_actions": [], "should_abort": false}',
}


def _canned_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="fake-model",
        input_tokens=7,
        output_tokens=11,
        finish_reason="stop",
        latency_ms=0.0,
        provider="fake",
    )


# --- canned low-level results for CLI / runner boundaries ---

_STEER_RESULT = {"success": True, "output": "ok", "exit_code": 0, "stderr": None}
_DRIVE_RESULT = {"success": True, "output": "hello\n", "exit_code": 0, "stderr": None}


async def _fake_execute(binary: str, args: list[str], timeout: int = 30) -> dict[str, Any]:
    return dict(_DRIVE_RESULT if binary == "drive" else _STEER_RESULT)


class _FakeResp:
    def __init__(self, text: str = "fetched body", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResp:
        return _FakeResp(text="ok")


class _KernelFakeRegistry:
    """A kernel-loop fake for the subagent_run node — one text-only turn."""

    async def stream(self, messages: Any, model: Any, *, tools: Any = None) -> Any:
        from app.kernel.types import TextBlock, TurnDone, TurnResult, Usage

        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock("subagent result")],
            stop_reason="end",
            usage=Usage(input_tokens=7, output_tokens=11),
            model=model or "fake-model",
            provider="fake",
        ))


# --- node fixtures: (config, inputs) ---

NODE_FIXTURES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    # deterministic, pure
    "json_validator": (
        {"schema": {"required": ["name"]}},
        {"text": '{"name": "Alice", "age": 30}'},
    ),
    "text_splitter": (
        {"chunk_size": 20, "overlap": 5},
        {"text": "The quick brown fox jumps over the lazy dog again and again."},
    ),
    "template_renderer": (
        {"template": "Hello {{name}}, you have {{count}} items.", "variables": {"count": "3"}},
        {"name": "Bob"},
    ),
    "output_formatter": ({"format": "json", "data": '{"a": 1, "b": 2}'}, {}),
    "run_linter": ({"language": "javascript", "code": "const x = 1;"}, {}),
    # deterministic, IO-mocked
    "fetch_url": ({"url": "https://example.com/page"}, {}),
    "fetch_document": ({"file_url": "https://example.com/doc.pdf"}, {}),
    "webhook": ({"url": "https://example.com/hook", "payload": {"k": "v"}}, {"a": "b"}),
    "knowledge_retrieval": (
        {"collection_id": "col-1", "query": "what is forge"},
        {"_user_id": "u-1"},
    ),
    "approval_gate": ({"message": "Approve to continue?"}, {}),
    # llm agent nodes
    "llm_generate": ({"user_prompt": "Say hello"}, {"text": "some context"}),
    "llm_summarize": ({"max_length": "short"}, {"text": "A long body of text to summarize."}),
    "llm_extract": ({}, {"text": "Alice met Bob on 2026-01-01."}),
    "llm_review": ({"review_type": "code"}, {"text": "x=1"}),
    "llm_implement": ({"task": "add two numbers", "language": "python"}, {}),
    # cu agent nodes
    "cu_planner": ({"objective": "open Safari"}, {"text": "screen state"}),
    "cu_analyzer": ({"focus": "errors"}, {"text": "screen text", "elements": []}),
    "cu_verifier": ({"objective": "open Safari", "expected": "Safari open"}, {"text": "Safari"}),
    "cu_error_handler": ({"error": "not found"}, {"text": "screen", "original_action": "click"}),
    # steer gui nodes
    "steer_see": ({"target": "screen"}, {}),
    "steer_ocr": ({"target": "screen"}, {}),
    "steer_click": ({"x": 10, "y": 20}, {}),
    "steer_type": ({"text": "hello"}, {}),
    "steer_hotkey": ({"keys": "cmd+s"}, {}),
    "steer_scroll": ({"direction": "down", "amount": 3}, {}),
    "steer_drag": ({"start_x": 0, "start_y": 0, "end_x": 10, "end_y": 10}, {}),
    "steer_focus": ({"app": "Safari"}, {}),
    "steer_find": ({"search_text": "Search"}, {}),
    "steer_wait": ({"search_text": "Done", "timeout": 1}, {}),
    "steer_clipboard": ({"action": "read"}, {}),
    "steer_apps": ({}, {}),
    "recording_control": ({"action": "start", "quality": "medium"}, {"_run_id": "run-1"}),
    # drive terminal nodes
    "drive_session": ({"action": "create", "session": "af-test"}, {}),
    "drive_run": ({"command": "echo hello", "session": "af-test"}, {}),
    "drive_send": ({"keys": "ls", "session": "af-test"}, {}),
    "drive_logs": ({"session": "af-test", "lines": 20}, {}),
    "drive_poll": ({"token": "DONE", "session": "af-test", "timeout": 1}, {}),
    "drive_fanout": ({"commands": ["echo a", "echo b"], "session": "af-test"}, {}),
    # orchestration nodes (Phase 9)
    "subagent_run": (
        {
            "spec": {
                "role": "scout",
                "prompt": "Audit the file for missing auth checks.",
                "tools": ["workspace.read"],
                "success_criteria": "cites each unauthenticated route",
            },
            "agent_id": "agent-eph-1",
            "worker_model": "fake-model",
            "max_concurrent": 2,
            "workflow_title": "Test workflow",
        },
        {"text": "upstream context", "_user_id": "u-1", "_run_id": "run-1",
         "_node_id": "scout-1"},
    ),
    # agent-control nodes
    "agent_spawn": ({"backend": "claude-code", "session": "af-agent-1"}, {}),
    "agent_prompt": ({"session": "af-agent-1", "prompt": "do the task"}, {}),
    "agent_monitor": ({"session": "af-agent-1", "lines": 50}, {}),
    "agent_wait": ({"session": "af-agent-1", "timeout": 1}, {}),
    "agent_stop": ({"session": "af-agent-1"}, {}),
    "agent_result": ({"session": "af-agent-1", "output_format": "text"}, {}),
}

_STEER_KEYS = {k for k in NODE_FIXTURES if k.startswith("steer_")}
_DRIVE_KEYS = {k for k in NODE_FIXTURES if k.startswith("drive_")}
_LLM_KEYS = {"llm_generate", "llm_summarize", "llm_extract", "llm_review", "llm_implement"}
_CU_KEYS = {"cu_planner", "cu_analyzer", "cu_verifier", "cu_error_handler"}

# canned agent_runner return dicts keyed by node
_AGENT_RUNNER_RETURNS: dict[str, tuple[str, dict[str, Any]]] = {
    "agent_spawn": (
        "spawn",
        {"session": "af-agent-1", "backend": "claude-code", "command": "claude", "status": "spawned"},
    ),
    "agent_prompt": (
        "prompt",
        {"session": "af-agent-1", "prompt_sent": True, "prompt_length": 11},
    ),
    "agent_monitor": ("monitor", {"session": "af-agent-1", "output": "working...", "line_count": 1}),
    "agent_wait": (
        "wait_for_completion",
        {"session": "af-agent-1", "completed": True, "elapsed_seconds": 3, "output": "done"},
    ),
    "agent_stop": ("stop", {"session": "af-agent-1", "stopped": True}),
    "agent_result": (
        "capture_result",
        {"session": "af-agent-1", "output": "result text", "parsed": None,
         "format": "text", "length": 11},
    ),
}


def _get_executor(key: str) -> Any:
    from app.services.blueprint_engine import _ALL_AGENT, _ALL_DETERMINISTIC

    if key in _ALL_DETERMINISTIC:
        return _ALL_DETERMINISTIC[key]
    return _ALL_AGENT[key]


async def run_node(key: str) -> dict[str, Any]:
    """Execute node ``key`` with its fixture inputs under controlled mocks."""
    config, inputs = NODE_FIXTURES[key]
    executor = _get_executor(key)

    with contextlib.ExitStack() as stack:
        # Neutralize the process-global rate limiter for every CU node.
        fake_limiter = SimpleNamespace(check=lambda: True, remaining=999)
        stack.enter_context(
            patch("app.services.computer_use.safety.cu_rate_limiter", fake_limiter)
        )

        if key in _LLM_KEYS or key in _CU_KEYS:
            stack.enter_context(
                patch.object(
                    provider_registry,
                    "complete",
                    AsyncMock(return_value=_canned_response(_CANNED_LLM[key])),
                )
            )
        elif key in _STEER_KEYS:
            stack.enter_context(
                patch("app.services.computer_use.steer.nodes.execute", _fake_execute)
            )
        elif key in _DRIVE_KEYS:
            stack.enter_context(
                patch("app.services.computer_use.drive.nodes.execute", _fake_execute)
            )
        elif key == "recording_control":
            stack.enter_context(
                patch(
                    "app.services.computer_use.recorder.recorder_service.start_recording",
                    AsyncMock(return_value={"status": "recording", "recording_path": "/tmp/rec.mp4"}),
                )
            )
        elif key in _AGENT_RUNNER_RETURNS:
            method, ret = _AGENT_RUNNER_RETURNS[key]
            stack.enter_context(
                patch(
                    f"app.services.computer_use.agents.agent_runner.agent_runner.{method}",
                    AsyncMock(return_value=ret),
                )
            )
        elif key == "subagent_run":
            stack.enter_context(
                patch(
                    "app.providers.registry.create_user_registry",
                    AsyncMock(return_value=_KernelFakeRegistry()),
                )
            )
            stack.enter_context(
                patch(
                    "app.services.orchestration.subagent.tool_plane.list_tools",
                    AsyncMock(return_value=[]),
                )
            )
        elif key == "fetch_url":
            stack.enter_context(
                patch("app.services.blueprint_nodes.deterministic.validate_url", lambda u: None)
            )
            stack.enter_context(
                patch(
                    "app.services.blueprint_nodes.deterministic.safe_get",
                    AsyncMock(return_value=_FakeResp(text="fetched body")),
                )
            )
        elif key == "fetch_document":
            stack.enter_context(
                patch("app.services.blueprint_nodes.deterministic.validate_url", lambda u: None)
            )
            stack.enter_context(
                patch(
                    "app.services.blueprint_nodes.deterministic.extract_text",
                    AsyncMock(return_value="Extracted document text."),
                )
            )
        elif key == "webhook":
            stack.enter_context(
                patch("app.services.blueprint_nodes.deterministic.validate_url", lambda u: None)
            )
            stack.enter_context(
                patch(
                    "app.services.blueprint_nodes.deterministic.httpx.AsyncClient",
                    _FakeAsyncClient,
                )
            )
        elif key == "knowledge_retrieval":
            stack.enter_context(
                patch(
                    "app.services.knowledge.knowledge_service.knowledge_service.search",
                    AsyncMock(
                        return_value=[
                            {"chunk_id": "c1", "document_id": "d1", "content": "Forge is a platform.",
                             "chunk_index": 0, "similarity": 0.42, "metadata": {}},
                        ]
                    ),
                )
            )

        try:
            output = await executor(config, inputs)
        except Exception as exc:  # noqa: BLE001 - freezing raise behavior is intentional
            return {"__raises__": type(exc).__name__, "__message__": str(exc)}

    return output
