"""Real MCP client — JSON-RPC 2.0 over stdio and Streamable HTTP.

Uses the official ``mcp`` SDK. A session is opened per operation (stateless from
the caller's view): connect, ``initialize``, then ``tools/list`` or
``tools/call``. HTTP transports are SSRF-checked and may carry a bearer token
(OAuth) from the connection's ``oauth_json``.

The session-level helpers (``tools_from_session`` / ``call_via_session``) are
split out so the parsing logic is testable against an in-memory session without
spawning a transport.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from app.services.security.url_validator import validate_url

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    transport: str  # "stdio" | "http"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    oauth: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPToolV2:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


def _headers_for(config: MCPServerConfig) -> dict[str, str]:
    headers: dict[str, str] = {}
    token = config.oauth.get("access_token") if config.oauth else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@asynccontextmanager
async def open_session(config: MCPServerConfig):
    """Open, initialize, and yield an MCP ClientSession for the config."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if config.transport == "stdio":
        params = StdioServerParameters(command=config.command, args=list(config.args))
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session
    elif config.transport == "http":
        from mcp.client.streamable_http import streamablehttp_client

        validate_url(config.url)  # SSRF guard for remote transports
        async with streamablehttp_client(
            config.url, headers=_headers_for(config)
        ) as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            yield session
    else:
        raise ValueError(f"unsupported MCP transport: {config.transport!r}")


def tools_from_session_result(result: Any) -> list[MCPToolV2]:
    """Convert an SDK ListToolsResult into MCPToolV2s."""
    tools = []
    for t in result.tools:
        tools.append(
            MCPToolV2(
                name=t.name,
                description=t.description or "",
                input_schema=dict(t.inputSchema or {}),
            )
        )
    return tools


def text_from_call_result(result: Any) -> str:
    """Flatten an SDK CallToolResult's content blocks to text."""
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    return "\n".join(parts)


async def list_tools(config: MCPServerConfig) -> list[MCPToolV2]:
    async with open_session(config) as session:
        return tools_from_session_result(await session.list_tools())


async def call_tool(
    config: MCPServerConfig, name: str, arguments: dict[str, Any] | None = None
) -> str:
    async with open_session(config) as session:
        result = await session.call_tool(name, arguments or {})
        return text_from_call_result(result)
