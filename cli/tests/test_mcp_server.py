"""Tests for the Forge MCP server adapter."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from forge import mcp_server
from forge.main import app

runner = CliRunner()


def test_mcp_server_command_registered():
    """`forge mcp-server` is wired into the CLI with a transport option."""
    result = runner.invoke(app, ["mcp-server", "--help"])
    assert result.exit_code == 0
    assert "transport" in result.output.lower()


def test_serve_rejects_unknown_transport():
    with pytest.raises(mcp_server.ForgeMCPError):
        mcp_server.serve(transport="carrier-pigeon")


def test_headers_requires_auth():
    with patch("forge.mcp_server.get_api_key", return_value=""):
        with pytest.raises(mcp_server.ForgeMCPError):
            mcp_server._headers()


def test_get_wraps_http_errors():
    with patch("forge.mcp_server.get_api_key", return_value="k"), \
         patch("forge.mcp_server.get_api_url", return_value="http://x"), \
         patch("forge.mcp_server.httpx.get", side_effect=mcp_server.httpx.ConnectError("boom")):
        with pytest.raises(mcp_server.ForgeMCPError):
            mcp_server._get("/api/agents")


class _FakeStream:
    """Minimal context-manager standing in for httpx.stream()."""

    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self._lines


def test_stream_run_aggregates_tokens_and_run_id():
    lines = [
        'data: {"type": "token", "data": "Hello "}',
        'data: {"type": "token", "data": "world"}',
        'data: {"type": "done", "run_id": "run_123"}',
        "data: [DONE]",
    ]
    with patch("forge.mcp_server.get_api_key", return_value="k"), \
         patch("forge.mcp_server.get_api_url", return_value="http://x"), \
         patch("forge.mcp_server.httpx.stream", return_value=_FakeStream(lines)):
        result = mcp_server._stream_run("/api/agents/a/run")
    assert result["output"] == "Hello world"
    assert result["run_id"] == "run_123"
    assert any(e["type"] == "token" for e in result["events"])


def test_stream_run_extracts_result_block_output():
    lines = [
        'data: {"type": "status", "data": "starting"}',
        'data: {"type": "result", "data": {"output": "final answer", "run_id": "run_9"}}',
        "data: [DONE]",
    ]
    with patch("forge.mcp_server.get_api_key", return_value="k"), \
         patch("forge.mcp_server.get_api_url", return_value="http://x"), \
         patch("forge.mcp_server.httpx.stream", return_value=_FakeStream(lines)):
        result = mcp_server._stream_run("/api/blueprints/b/run", json_body={"input_text": "go"})
    assert result["output"] == "final answer"
    assert result["run_id"] == "run_9"


def test_stream_run_raises_on_error_event():
    lines = ['data: {"type": "error", "data": "model exploded"}']
    with patch("forge.mcp_server.get_api_key", return_value="k"), \
         patch("forge.mcp_server.get_api_url", return_value="http://x"), \
         patch("forge.mcp_server.httpx.stream", return_value=_FakeStream(lines)):
        with pytest.raises(mcp_server.ForgeMCPError):
            mcp_server._stream_run("/api/agents/a/run")


def test_build_server_registers_five_tools():
    """build_server wires exactly the five documented tools (skips if mcp absent)."""
    pytest.importorskip("mcp")
    import asyncio

    server = mcp_server.build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "forge_list_agents",
        "forge_run_agent",
        "forge_list_blueprints",
        "forge_run_blueprint",
        "forge_get_run_status",
    }


def test_short_truncates():
    assert mcp_server._short("x" * 200, limit=10).endswith("…")
    assert mcp_server._short("short") == "short"
