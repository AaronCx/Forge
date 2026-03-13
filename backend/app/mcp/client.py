"""MCP (Model Context Protocol) client — connects to external MCP servers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.security.url_validator import validate_url

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """A tool discovered from an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    server_id: str = ""
    server_name: str = ""


@dataclass
class MCPServerStatus:
    """Health/status of an MCP server connection."""

    server_id: str
    server_url: str
    status: str  # "connected", "disconnected", "error"
    latency_ms: float | None = None
    error: str | None = None
    tools_count: int = 0


class MCPClient:
    """Client for communicating with MCP-compatible tool servers.

    MCP servers expose tools via a standard HTTP API:
      GET  /tools          — list available tools
      POST /tools/{name}   — call a tool with arguments
      GET  /health         — health check
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    async def health_check(self, server_url: str) -> MCPServerStatus:
        """Check if an MCP server is reachable and responsive."""
        validate_url(server_url)
        start = time.time()
        try:
            resp = await self._http.get(f"{server_url.rstrip('/')}/health")
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return MCPServerStatus(
                    server_id="",
                    server_url=server_url,
                    status="connected",
                    latency_ms=latency,
                )
            return MCPServerStatus(
                server_id="",
                server_url=server_url,
                status="error",
                latency_ms=latency,
                error=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return MCPServerStatus(
                server_id="",
                server_url=server_url,
                status="disconnected",
                latency_ms=latency,
                error=str(e),
            )

    async def discover_tools(self, server_url: str, server_id: str = "", server_name: str = "") -> list[MCPTool]:
        """List available tools from an MCP server."""
        validate_url(server_url)
        try:
            resp = await self._http.get(f"{server_url.rstrip('/')}/tools")
            resp.raise_for_status()
            data = resp.json()

            tools_data = data if isinstance(data, list) else data.get("tools", [])
            tools = []
            for t in tools_data:
                tools.append(
                    MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("input_schema", t.get("inputSchema", {})),
                        output_schema=t.get("output_schema", t.get("outputSchema", {})),
                        server_id=server_id,
                        server_name=server_name,
                    )
                )
            return tools
        except Exception as e:
            logger.warning("Failed to discover tools from %s: %s", server_url, e)
            return []

    async def call_tool(
        self, server_url: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a tool on an MCP server."""
        validate_url(server_url)
        url = f"{server_url.rstrip('/')}/tools/{tool_name}"
        resp = await self._http.post(url, json=arguments)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def connect(self, server_url: str) -> MCPServerStatus:
        """Establish a connection to an MCP server (health check + tool discovery)."""
        status = await self.health_check(server_url)
        if status.status == "connected":
            tools = await self.discover_tools(server_url)
            status.tools_count = len(tools)
        return status


mcp_client = MCPClient()
