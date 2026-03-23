"""Workspace management and file operations API."""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.models.workspace import (
    FileContent,
    FileSearch,
    FileWrite,
    SearchResult,
    WorkspaceChangeResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.routers.auth import get_current_user
from app.services import workspace_service

router = APIRouter(tags=["workspaces"])

WORKSPACES_BASE = Path.home() / ".agentforge" / "workspaces"


# --- Workspace CRUD ---


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    ws: WorkspaceCreate,
    user=Depends(get_current_user),  # noqa: B008
):
    """Create a new workspace (directory + DB entry)."""
    workspace_dir = WORKSPACES_BASE / ws.name
    if workspace_dir.exists():
        raise HTTPException(status_code=409, detail=f"Workspace '{ws.name}' already exists")

    workspace_dir.mkdir(parents=True, exist_ok=True)

    data = ws.model_dump()
    data["user_id"] = user.id
    data["path"] = str(workspace_dir)
    data["status"] = "active"

    result = get_db().table("workspaces").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create workspace")
    return result.data[0]


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user=Depends(get_current_user),  # noqa: B008
):
    """List all workspaces for the current user."""
    result = get_db().table("workspaces").select("*").eq("user_id", user.id).eq("status", "active").order("updated_at", desc=True).execute()
    return result.data


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get workspace details."""
    result = get_db().table("workspaces").select("*").eq("id", workspace_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if result.data["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return result.data


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    ws: WorkspaceUpdate,
    user=Depends(get_current_user),  # noqa: B008
):
    """Update workspace metadata."""
    existing = get_db().table("workspaces").select("user_id").eq("id", workspace_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Workspace not found")

    update_data = ws.model_dump(exclude_none=True)
    result = get_db().table("workspaces").update(update_data).eq("id", workspace_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update workspace")
    return result.data[0]


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Soft-delete a workspace (marks as deleted, keeps files)."""
    existing = get_db().table("workspaces").select("user_id").eq("id", workspace_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    get_db().table("workspaces").update({"status": "deleted"}).eq("id", workspace_id).execute()


# --- File operations ---


def _get_workspace_path(workspace_id: str, user_id: str) -> str:
    """Get workspace path with auth check."""
    result = get_db().table("workspaces").select("path, user_id").eq("id", workspace_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if result.data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return str(result.data["path"])


@router.get("/workspaces/{workspace_id}/files")
async def list_files(
    workspace_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """List all files in the workspace as a tree."""
    ws_path = _get_workspace_path(workspace_id, user.id)
    return workspace_service.list_files(ws_path)


@router.get("/workspaces/{workspace_id}/files/{file_path:path}", response_model=FileContent)
async def read_file(
    workspace_id: str,
    file_path: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Read a file from the workspace."""
    ws_path = _get_workspace_path(workspace_id, user.id)
    try:
        content, size = workspace_service.read_file(ws_path, file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return FileContent(path=file_path, content=content, size=size)


@router.put("/workspaces/{workspace_id}/files/{file_path:path}")
async def write_file(
    workspace_id: str,
    file_path: str,
    body: FileWrite,
    user=Depends(get_current_user),  # noqa: B008
):
    """Write/create a file in the workspace."""
    ws_path = _get_workspace_path(workspace_id, user.id)

    # Read before content for history
    content_before = None
    with contextlib.suppress(FileNotFoundError, ValueError):
        content_before, _ = workspace_service.read_file(ws_path, file_path)

    try:
        workspace_service.write_file(ws_path, file_path, body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Record change
    change_type = "modify" if content_before is not None else "create"
    get_db().table("workspace_changes").insert({
        "workspace_id": workspace_id,
        "file_path": file_path,
        "change_type": change_type,
        "content_before": content_before,
        "content_after": body.content,
        "attribution": "user:web",
    }).execute()

    return {"ok": True, "path": file_path, "change_type": change_type}


@router.delete("/workspaces/{workspace_id}/files/{file_path:path}")
async def delete_file(
    workspace_id: str,
    file_path: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Delete a file from the workspace."""
    ws_path = _get_workspace_path(workspace_id, user.id)

    # Read before content for history
    content_before = None
    with contextlib.suppress(FileNotFoundError, ValueError):
        content_before, _ = workspace_service.read_file(ws_path, file_path)

    try:
        workspace_service.delete_file(ws_path, file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    get_db().table("workspace_changes").insert({
        "workspace_id": workspace_id,
        "file_path": file_path,
        "change_type": "delete",
        "content_before": content_before,
        "attribution": "user:web",
    }).execute()

    return {"ok": True}


@router.post("/workspaces/{workspace_id}/files/search", response_model=list[SearchResult])
async def search_files(
    workspace_id: str,
    body: FileSearch,
    user=Depends(get_current_user),  # noqa: B008
):
    """Search for text across workspace files."""
    ws_path = _get_workspace_path(workspace_id, user.id)
    results = workspace_service.search_files(ws_path, body.query, body.glob)
    return results


# --- Change history ---


@router.get("/workspaces/{workspace_id}/history", response_model=list[WorkspaceChangeResponse])
async def get_history(
    workspace_id: str,
    path: str = "",
    limit: int = 50,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get change history for a workspace or specific file."""
    _get_workspace_path(workspace_id, user.id)  # Auth check
    query = get_db().table("workspace_changes").select("*").eq("workspace_id", workspace_id)
    if path:
        query = query.eq("file_path", path)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data
