"""WebSocket endpoint for workspace real-time file sync."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import get_db
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/workspace/{workspace_id}")
async def workspace_websocket(websocket: WebSocket, workspace_id: str, token: str = ""):
    """WebSocket endpoint for real-time workspace file sync.

    Clients connect and receive file change notifications:
    - file_changed: {type, path, content, change_type: "modified"}
    - file_created: {type, path, content, change_type: "created"}
    - file_deleted: {type, path, change_type: "deleted"}
    - file_renamed: {type, old_path, new_path, change_type: "renamed"}

    Clients can send:
    - file_save: {type: "file_save", path, content} — saves file to disk
    """
    # Auth check
    if token:
        try:
            get_db().auth.get_user(token)
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

    # Verify workspace exists
    result = get_db().table("workspaces").select("path").eq("id", workspace_id).single().execute()
    if not result.data:
        await websocket.close(code=4004, reason="Workspace not found")
        return

    workspace_path = result.data["path"]
    await ws_manager.connect(workspace_id, websocket)

    # Start file watcher if this is the first client
    try:
        from app.services.file_watcher import watcher_manager
        watcher_manager.start_watching(workspace_id, workspace_path)
    except ImportError:
        pass  # File watcher not available (watchdog not installed)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "file_save":
                # Client is saving a file — write to disk and broadcast to others
                from app.services import workspace_service

                path = msg.get("path", "")
                content = msg.get("content", "")
                if path:
                    try:
                        workspace_service.write_file(workspace_path, path, content)
                        # Broadcast to other clients (not the sender)
                        await ws_manager.broadcast(workspace_id, {
                            "type": "file_changed",
                            "path": path,
                            "content": content,
                            "change_type": "modified",
                            "source": "user:web",
                        }, exclude=websocket)
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": str(e),
                        }))

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(workspace_id, websocket)
        # Stop watcher if no more clients
        if not ws_manager.has_connections(workspace_id):
            try:
                from app.services.file_watcher import watcher_manager
                watcher_manager.stop_watching(workspace_id)
            except ImportError:
                pass
