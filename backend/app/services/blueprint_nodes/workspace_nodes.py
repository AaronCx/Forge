"""Workspace blueprint node executors.

These nodes allow blueprints to read/write/search files in workspaces,
enabling agents to operate directly on workspace content.
"""

from __future__ import annotations

from typing import Any

from app.services import workspace_service


async def execute_workspace_read(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Read a file from a workspace."""
    workspace_path = config.get("workspace_path", inputs.get("workspace_path", ""))
    file_path = config.get("file_path", inputs.get("file_path", ""))

    if not workspace_path or not file_path:
        return {"error": "workspace_path and file_path are required"}

    try:
        content, size = workspace_service.read_file(workspace_path, file_path)
        return {"content": content, "size": size, "path": file_path}
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}", "content": ""}
    except ValueError as e:
        return {"error": str(e), "content": ""}


async def execute_workspace_write(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Write content to a file in a workspace."""
    workspace_path = config.get("workspace_path", inputs.get("workspace_path", ""))
    file_path = config.get("file_path", inputs.get("file_path", ""))
    content = config.get("content", inputs.get("content", ""))

    if not workspace_path or not file_path:
        return {"error": "workspace_path and file_path are required"}

    try:
        workspace_service.write_file(workspace_path, file_path, content)

        # Broadcast change via WebSocket
        try:

            # Find workspace_id from path (best effort)
            from app.db import get_db
            from app.services.ws_manager import ws_manager
            result = get_db().table("workspaces").select("id").eq("path", workspace_path).single().execute()
            if result.data:
                await ws_manager.broadcast(result.data["id"], {
                    "type": "file_changed",
                    "path": file_path,
                    "content": content,
                    "change_type": "modified",
                    "source": "agent:blueprint",
                })
        except Exception:
            pass  # WebSocket broadcast is best-effort

        return {"ok": True, "path": file_path, "bytes_written": len(content)}
    except ValueError as e:
        return {"error": str(e)}


async def execute_workspace_list(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """List files in a workspace."""
    workspace_path = config.get("workspace_path", inputs.get("workspace_path", ""))
    if not workspace_path:
        return {"error": "workspace_path is required"}

    files = workspace_service.list_files(workspace_path)
    # Flatten for agent consumption
    flat: list[str] = []
    _flatten_files(files, flat)
    return {"files": flat, "count": len(flat)}


def _flatten_files(entries: list[dict[str, Any]], result: list[str]) -> None:
    for entry in entries:
        if entry["type"] == "file":
            result.append(entry["path"])
        if entry.get("children"):
            _flatten_files(entry["children"], result)


async def execute_workspace_search(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Search across workspace files."""
    workspace_path = config.get("workspace_path", inputs.get("workspace_path", ""))
    query = config.get("query", inputs.get("query", ""))
    glob_pattern = config.get("glob", inputs.get("glob", "*"))

    if not workspace_path or not query:
        return {"error": "workspace_path and query are required"}

    results = workspace_service.search_files(workspace_path, query, glob_pattern)
    return {"results": results, "count": len(results)}
