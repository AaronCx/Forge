"""Forge as an MCP server (harness-plan.md Phase 5).

Exposes the ToolPlane (blueprints, nodes, knowledge search, workspace) to any
MCP client — Claude Code, Codex, etc. Computer-use (``cu.*``) and agent-control
(``agent.*``) tools are excluded by default; opt in with ``FORGE_MCP_EXPOSE_CU``.

``build_forge_mcp_server`` returns a low-level ``mcp.server.Server`` whose
``list_tools``/``call_tool`` delegate to the plane. Serve it over stdio for a
local client, or over Streamable HTTP (see ``streamable_http_app``) behind the
app's existing API-key auth for a remote one.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _expose_cu(override: bool | None) -> bool:
    if override is not None:
        return override
    return os.getenv("FORGE_MCP_EXPOSE_CU", "").strip().lower() in ("1", "true", "yes", "on")


def _is_excluded(name: str, expose_cu: bool) -> bool:
    if expose_cu:
        return False
    return name.startswith("cu.") or name.startswith("agent.")


def build_forge_mcp_server(user_id: str, *, expose_cu: bool | None = None) -> Any:
    """Build an MCP Server that proxies the ToolPlane for one user."""
    from mcp import types
    from mcp.server import Server

    from app.kernel.toolplane import ExecContext, tool_plane
    from app.kernel.types import ToolUseBlock

    expose = _expose_cu(expose_cu)
    server: Any = Server("forge")

    @server.list_tools()
    async def _list_tools() -> list[Any]:
        specs = await tool_plane.list_tools(user_id, ExecContext(user_id=user_id))
        return [
            types.Tool(
                name=s.name,
                description=s.description,
                inputSchema=s.input_schema or {"type": "object", "properties": {}},
            )
            for s in specs
            if not _is_excluded(s.name, expose)
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        if _is_excluded(name, expose):
            return [types.TextContent(type="text", text=f"Tool '{name}' is not exposed.")]
        result = await tool_plane.execute(
            ToolUseBlock(id="mcp-server", name=name, input=arguments or {}),
            ExecContext(user_id=user_id),
        )
        return [types.TextContent(type="text", text=str(result.output))]

    return server


def streamable_http_app(user_id: str, *, expose_cu: bool | None = None) -> Any:
    """A Streamable HTTP ASGI app serving Forge's MCP server.

    Mount behind the app's API-key auth. Kept as a factory (not mounted into the
    main app by default) so the public route surface stays stable until wired in.
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    server = build_forge_mcp_server(user_id, expose_cu=expose_cu)
    manager = StreamableHTTPSessionManager(app=server)
    return manager


async def serve_stdio(user_id: str, *, expose_cu: bool | None = None) -> None:  # pragma: no cover
    """Serve Forge's MCP server over stdio (used by ``forge mcp-server``)."""
    from mcp.server.stdio import stdio_server

    server = build_forge_mcp_server(user_id, expose_cu=expose_cu)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
