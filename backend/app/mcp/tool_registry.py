"""Unified tool registry — merges built-in tools with MCP server tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.mcp.client import mcp_client

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Unified tool descriptor for both built-in and MCP tools."""

    name: str
    display_name: str
    description: str
    source: str  # "built-in" or MCP server name
    source_id: str  # "" for built-in, server_id for MCP
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


# Built-in tools metadata
BUILTIN_TOOLS: dict[str, ToolInfo] = {
    "web_search": ToolInfo(
        name="web_search",
        display_name="Web Search",
        description="Search the web using SerpAPI and return results",
        source="built-in",
        source_id="",
    ),
    "document_reader": ToolInfo(
        name="document_reader",
        display_name="Document Reader",
        description="Extract text from PDF, DOCX, or TXT files",
        source="built-in",
        source_id="",
    ),
    "code_executor": ToolInfo(
        name="code_executor",
        display_name="Code Executor",
        description="Execute Python code in a sandboxed environment",
        source="built-in",
        source_id="",
    ),
    "data_extractor": ToolInfo(
        name="data_extractor",
        display_name="Data Extractor",
        description="Extract structured data from text using LLM",
        source="built-in",
        source_id="",
    ),
    "summarizer": ToolInfo(
        name="summarizer",
        display_name="Summarizer",
        description="Summarize text content using LLM",
        source="built-in",
        source_id="",
    ),
}


class ToolRegistry:
    """Unified registry that combines built-in tools and MCP server tools."""

    def __init__(self) -> None:
        self._mcp_tools: dict[str, ToolInfo] = {}  # keyed by "server_id:tool_name"

    def list_builtin(self) -> list[ToolInfo]:
        """List all built-in tools."""
        return list(BUILTIN_TOOLS.values())

    def list_mcp_tools(self) -> list[ToolInfo]:
        """List all discovered MCP tools."""
        return list(self._mcp_tools.values())

    def list_all(self) -> list[ToolInfo]:
        """List all tools (built-in + MCP)."""
        return self.list_builtin() + self.list_mcp_tools()

    def get_tool(self, source: str, name: str) -> ToolInfo | None:
        """Get a specific tool by source and name."""
        if source == "built-in":
            return BUILTIN_TOOLS.get(name)
        key = f"{source}:{name}"
        return self._mcp_tools.get(key)

    def is_builtin(self, name: str) -> bool:
        return name in BUILTIN_TOOLS

    async def refresh_mcp_tools(
        self, connections: list[dict[str, Any]]
    ) -> None:
        """Refresh MCP tools from a list of active connections.

        connections: list of dicts with keys: id, name, server_url
        """
        self._mcp_tools.clear()
        for conn in connections:
            server_id = conn["id"]
            server_name = conn.get("name", server_id)
            server_url = conn["server_url"]
            try:
                tools = await mcp_client.discover_tools(server_url, server_id, server_name)
                for t in tools:
                    key = f"{server_id}:{t.name}"
                    self._mcp_tools[key] = ToolInfo(
                        name=t.name,
                        display_name=t.name.replace("_", " ").title(),
                        description=t.description,
                        source=server_name,
                        source_id=server_id,
                        input_schema=t.input_schema,
                        output_schema=t.output_schema,
                    )
            except Exception:
                logger.warning("Failed to refresh tools from %s", server_url, exc_info=True)

    async def call_mcp_tool(
        self, server_url: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Call a tool on an MCP server."""
        return await mcp_client.call_tool(server_url, tool_name, arguments)


tool_registry = ToolRegistry()
