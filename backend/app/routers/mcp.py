"""MCP connection management API routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import supabase
from app.mcp.client import mcp_client
from app.mcp.tool_registry import tool_registry
from app.routers.auth import get_current_user

router = APIRouter(tags=["mcp"])


class MCPConnectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    server_url: str = Field(..., min_length=1)


class MCPConnectionResponse(BaseModel):
    id: str
    name: str
    server_url: str
    status: str
    tools_discovered: list[dict[str, Any]]
    created_at: str
    last_connected_at: str | None


# --- MCP Connection Management ---


@router.post("/mcp/connect")
async def connect_mcp_server(
    req: MCPConnectRequest, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, Any]:
    """Add and test an MCP server connection."""
    # Test connection first
    status = await mcp_client.connect(req.server_url)

    if status.status != "connected":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot connect to MCP server: {status.error or 'unknown error'}",
        )

    # Discover tools
    tools = await mcp_client.discover_tools(req.server_url)
    tools_json = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]

    conn_id = str(uuid.uuid4())
    row = {
        "id": conn_id,
        "user_id": user.id,
        "name": req.name,
        "server_url": req.server_url,
        "status": "connected",
        "tools_discovered": tools_json,
        "last_connected_at": datetime.now(UTC).isoformat(),
    }

    result = supabase.table("mcp_connections").insert(row).execute()
    return result.data[0] if result.data else row


@router.get("/mcp/connections")
async def list_mcp_connections(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List user's MCP connections with status."""
    result = (
        supabase.table("mcp_connections")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.delete("/mcp/connections/{connection_id}")
async def delete_mcp_connection(
    connection_id: str, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, str]:
    """Remove an MCP connection."""
    supabase.table("mcp_connections").delete().eq("id", connection_id).eq(
        "user_id", user.id
    ).execute()
    return {"status": "deleted"}


@router.get("/mcp/connections/{connection_id}/tools")
async def list_connection_tools(
    connection_id: str, user: Any = Depends(get_current_user)  # noqa: B008
) -> list[dict[str, Any]]:
    """List tools from a specific MCP server."""
    result = (
        supabase.table("mcp_connections")
        .select("*")
        .eq("id", connection_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Connection not found")

    conn = result.data
    # Re-discover tools from the server
    tools = await mcp_client.discover_tools(
        conn["server_url"], server_id=conn["id"], server_name=conn["name"]
    )

    tools_json = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]

    # Update stored tools
    supabase.table("mcp_connections").update(
        {"tools_discovered": tools_json, "last_connected_at": datetime.now(UTC).isoformat()}
    ).eq("id", connection_id).execute()

    return tools_json


@router.post("/mcp/connections/{connection_id}/test")
async def test_mcp_connection(
    connection_id: str, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, Any]:
    """Test an MCP connection."""
    result = (
        supabase.table("mcp_connections")
        .select("*")
        .eq("id", connection_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Connection not found")

    conn = result.data
    status = await mcp_client.health_check(conn["server_url"])

    # Update status in DB
    new_status = status.status
    supabase.table("mcp_connections").update(
        {"status": new_status, "last_connected_at": datetime.now(UTC).isoformat()}
    ).eq("id", connection_id).execute()

    return {
        "status": new_status,
        "latency_ms": status.latency_ms,
        "error": status.error,
    }


# --- Unified Tool Listing ---


@router.get("/tools")
async def list_all_tools(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """Unified tool listing — built-in tools + all MCP tools for this user."""
    # Get user's MCP connections
    result = (
        supabase.table("mcp_connections")
        .select("*")
        .eq("user_id", user.id)
        .eq("status", "connected")
        .execute()
    )
    connections = result.data or []

    # Refresh MCP tools
    await tool_registry.refresh_mcp_tools(connections)

    # Build unified list
    tools = []
    for t in tool_registry.list_all():
        tools.append({
            "name": t.name,
            "display_name": t.display_name,
            "description": t.description,
            "source": t.source,
            "source_id": t.source_id,
            "input_schema": t.input_schema,
            "output_schema": t.output_schema,
        })

    return tools
