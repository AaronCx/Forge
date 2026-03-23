"""WebSocket connection manager for workspace real-time sync."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per workspace for real-time file sync."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, workspace_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if workspace_id not in self.active_connections:
            self.active_connections[workspace_id] = []
        self.active_connections[workspace_id].append(websocket)
        logger.info("WebSocket connected to workspace %s (%d clients)", workspace_id, len(self.active_connections[workspace_id]))

    def disconnect(self, workspace_id: str, websocket: WebSocket) -> None:
        if workspace_id in self.active_connections:
            self.active_connections[workspace_id] = [
                ws for ws in self.active_connections[workspace_id] if ws is not websocket
            ]
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]

    async def broadcast(self, workspace_id: str, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
        """Broadcast a message to all clients connected to a workspace."""
        connections = self.active_connections.get(workspace_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            if ws is exclude:
                continue
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(workspace_id, ws)

    def connection_count(self, workspace_id: str) -> int:
        return len(self.active_connections.get(workspace_id, []))

    def has_connections(self, workspace_id: str) -> bool:
        return workspace_id in self.active_connections and len(self.active_connections[workspace_id]) > 0


# Singleton
ws_manager = ConnectionManager()
