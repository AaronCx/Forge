"""Tests for MCP client, tool registry, triggers, and API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from app.mcp.client import MCPClient, MCPServerStatus, MCPTool
from app.mcp.scheduler import CronScheduler
from app.mcp.tool_registry import ToolRegistry
from app.mcp.triggers import TriggerService

# === MCPClient tests ===


@pytest.mark.asyncio
async def test_mcp_health_check_success():
    client = MCPClient()
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.health_check("http://localhost:3100")

    assert result.status == "connected"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_mcp_health_check_failure():
    client = MCPClient()

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=Exception("refused")):
        result = await client.health_check("http://localhost:9999")

    assert result.status == "disconnected"
    assert "refused" in (result.error or "")


@pytest.mark.asyncio
async def test_mcp_health_check_http_error():
    client = MCPClient()
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 500

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.health_check("http://localhost:3100")

    assert result.status == "error"
    assert "500" in (result.error or "")


@pytest.mark.asyncio
async def test_mcp_discover_tools():
    client = MCPClient()
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "tools": [
            {"name": "list_repos", "description": "List repos", "input_schema": {"type": "object"}},
            {"name": "create_pr", "description": "Create PR", "inputSchema": {"type": "object"}},
        ]
    }

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
        tools = await client.discover_tools("http://localhost:3100", server_id="s1", server_name="GitHub")

    assert len(tools) == 2
    assert tools[0].name == "list_repos"
    assert tools[0].server_id == "s1"
    assert tools[0].server_name == "GitHub"
    assert tools[1].name == "create_pr"
    # Should accept both input_schema and inputSchema
    assert tools[1].input_schema == {"type": "object"}


@pytest.mark.asyncio
async def test_mcp_discover_tools_flat_array():
    """MCP servers may return a flat array instead of {tools: [...]}."""
    client = MCPClient()
    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = [
        {"name": "search", "description": "Search things"},
    ]

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_resp):
        tools = await client.discover_tools("http://localhost:3100")

    assert len(tools) == 1
    assert tools[0].name == "search"


@pytest.mark.asyncio
async def test_mcp_discover_tools_error():
    client = MCPClient()

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=Exception("timeout")):
        tools = await client.discover_tools("http://localhost:9999")

    assert tools == []


@pytest.mark.asyncio
async def test_mcp_call_tool():
    client = MCPClient()
    mock_resp = MagicMock(spec=Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": "success", "data": [1, 2, 3]}

    with patch.object(client._http, "post", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.call_tool("http://localhost:3100", "list_repos", {"org": "acme"})

    assert result["result"] == "success"


@pytest.mark.asyncio
async def test_mcp_connect():
    client = MCPClient()
    mock_health = MagicMock(spec=Response)
    mock_health.status_code = 200

    mock_tools = MagicMock(spec=Response)
    mock_tools.status_code = 200
    mock_tools.raise_for_status = MagicMock()
    mock_tools.json.return_value = [{"name": "tool1", "description": "A tool"}]

    async def mock_get(url):
        if "/health" in url:
            return mock_health
        return mock_tools

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=mock_get):
        result = await client.connect("http://localhost:3100")

    assert result.status == "connected"
    assert result.tools_count == 1


# === ToolRegistry tests ===


def test_tool_registry_builtin():
    registry = ToolRegistry()
    builtin = registry.list_builtin()
    assert len(builtin) == 5
    names = {t.name for t in builtin}
    assert "web_search" in names
    assert "summarizer" in names


def test_tool_registry_get_builtin():
    registry = ToolRegistry()
    tool = registry.get_tool("built-in", "web_search")
    assert tool is not None
    assert tool.name == "web_search"
    assert tool.source == "built-in"


def test_tool_registry_is_builtin():
    registry = ToolRegistry()
    assert registry.is_builtin("web_search") is True
    assert registry.is_builtin("unknown_tool") is False


def test_tool_registry_list_all_no_mcp():
    registry = ToolRegistry()
    all_tools = registry.list_all()
    assert len(all_tools) == 5  # only built-in


@pytest.mark.asyncio
async def test_tool_registry_refresh_mcp_tools():
    registry = ToolRegistry()

    mock_tools = [
        MCPTool(name="search", description="Search", server_id="s1", server_name="TestServer"),
        MCPTool(name="fetch", description="Fetch", server_id="s1", server_name="TestServer"),
    ]

    with patch("app.mcp.tool_registry.mcp_client.discover_tools", new_callable=AsyncMock, return_value=mock_tools):
        await registry.refresh_mcp_tools([
            {"id": "s1", "name": "TestServer", "server_url": "http://localhost:3100"}
        ])

    all_tools = registry.list_all()
    assert len(all_tools) == 7  # 5 built-in + 2 MCP

    mcp_tools = registry.list_mcp_tools()
    assert len(mcp_tools) == 2

    # Get MCP tool
    tool = registry.get_tool("s1", "search")
    assert tool is not None
    assert tool.source == "TestServer"


# === CronScheduler tests ===


def test_cron_validate():
    assert CronScheduler.validate_cron("0 * * * *") is True
    assert CronScheduler.validate_cron("0 9 * * 1-5") is True
    assert CronScheduler.validate_cron("invalid") is False
    assert CronScheduler.validate_cron("") is False


def test_cron_next_fire_time():
    result = CronScheduler.next_fire_time("0 * * * *")
    assert result is not None

    result = CronScheduler.next_fire_time("invalid")
    assert result is None


# === TriggerService tests ===


@pytest.mark.asyncio
async def test_trigger_create():
    service = TriggerService()

    mock_result = MagicMock()
    mock_result.data = [{
        "id": "t1",
        "user_id": "u1",
        "type": "webhook",
        "config": {"webhook_secret": "abc"},
        "target_type": "agent",
        "target_id": "a1",
        "enabled": True,
        "fire_count": 0,
    }]

    with patch("app.mcp.triggers.supabase") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_result
        result = await service.create_trigger(
            user_id="u1",
            trigger_type="webhook",
            config={},
            target_type="agent",
            target_id="a1",
        )

    assert result["type"] == "webhook"
    assert result["target_type"] == "agent"


@pytest.mark.asyncio
async def test_trigger_list():
    service = TriggerService()

    mock_result = MagicMock()
    mock_result.data = [
        {"id": "t1", "type": "webhook", "enabled": True},
        {"id": "t2", "type": "cron", "enabled": False},
    ]

    with patch("app.mcp.triggers.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result
        triggers = await service.list_triggers("u1")

    assert len(triggers) == 2


@pytest.mark.asyncio
async def test_trigger_toggle():
    service = TriggerService()

    mock_get_result = MagicMock()
    mock_get_result.data = {"id": "t1", "enabled": True}

    mock_update_result = MagicMock()
    mock_update_result.data = [{"id": "t1", "enabled": False}]

    with patch("app.mcp.triggers.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get_result
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_update_result

        result = await service.toggle_trigger("t1")

    assert result is not None
    assert result["enabled"] is False


# === API Route tests ===


@pytest.mark.asyncio
async def test_mcp_connect_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.routers.mcp.get_current_user", return_value=MagicMock(id="user1")), \
         patch("app.routers.mcp.mcp_client") as mock_client:
            mock_client.connect = AsyncMock(return_value=MCPServerStatus(
                server_id="", server_url="http://test:3100", status="connected",
                latency_ms=50, tools_count=2,
            ))
            mock_client.discover_tools = AsyncMock(return_value=[
                MCPTool(name="t1", description="Tool 1"),
                MCPTool(name="t2", description="Tool 2"),
            ])
            with patch("app.routers.mcp.supabase") as mock_sb:
                mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(
                    data=[{"id": "c1", "name": "Test", "server_url": "http://test:3100",
                           "status": "connected", "tools_discovered": []}]
                )

                test_client = TestClient(app)
                resp = test_client.post(
                    "/api/mcp/connect",
                    json={"name": "Test", "server_url": "http://test:3100"},
                    headers={"Authorization": "Bearer test"},
                )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_receiver_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.routers.triggers.trigger_service") as mock_ts:
        mock_ts.get_trigger = AsyncMock(return_value={
            "id": "t1", "type": "webhook", "enabled": True, "config": {},
            "target_type": "agent", "target_id": "a1", "user_id": "u1",
        })
        mock_ts.fire_trigger = AsyncMock(return_value={
            "trigger_id": "t1", "target_type": "agent", "target_id": "a1",
            "run_id": "r1", "status": "fired",
        })

        test_client = TestClient(app)
        resp = test_client.post(
            "/api/webhooks/t1",
            json={"text": "Hello from GitHub"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fired"
    assert data["run_id"] == "r1"


@pytest.mark.asyncio
async def test_webhook_receiver_disabled():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.routers.triggers.trigger_service") as mock_ts:
        mock_ts.get_trigger = AsyncMock(return_value={
            "id": "t1", "type": "webhook", "enabled": False, "config": {},
        })

        test_client = TestClient(app)
        resp = test_client.post("/api/webhooks/t1", json={})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_receiver_wrong_type():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.routers.triggers.trigger_service") as mock_ts:
        mock_ts.get_trigger = AsyncMock(return_value={
            "id": "t1", "type": "cron", "enabled": True, "config": {},
        })

        test_client = TestClient(app)
        resp = test_client.post("/api/webhooks/t1", json={})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_receiver_not_found():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch("app.routers.triggers.trigger_service") as mock_ts:
        mock_ts.get_trigger = AsyncMock(return_value=None)

        test_client = TestClient(app)
        resp = test_client.post("/api/webhooks/nonexistent", json={})

    assert resp.status_code == 404


def test_tools_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.mcp.tool_registry import ToolInfo
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.mcp.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            with patch("app.routers.mcp.tool_registry") as mock_tr:
                mock_tr.refresh_mcp_tools = AsyncMock()
                mock_tr.list_all.return_value = [
                    ToolInfo(
                        name="web_search", display_name="Web Search",
                        description="Search", source="built-in", source_id="",
                        input_schema={}, output_schema={},
                    )
                ]

                test_client = TestClient(app)
                resp = test_client.get("/api/tools")

        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) == 1
        assert tools[0]["name"] == "web_search"
    finally:
        app.dependency_overrides.clear()
