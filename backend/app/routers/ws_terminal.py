"""WebSocket terminal endpoint — spawns a shell in the workspace directory."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import struct
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/terminal/{workspace_id}")
async def terminal_websocket(websocket: WebSocket, workspace_id: str, token: str = ""):
    """WebSocket terminal: spawns a pty shell with CWD set to workspace directory."""
    # Auth check
    if token:
        try:
            get_db().auth.get_user(token)
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

    # Get workspace path
    result = get_db().table("workspaces").select("path").eq("id", workspace_id).single().execute()
    if not result.data:
        await websocket.close(code=4004, reason="Workspace not found")
        return

    workspace_path = str(result.data["path"])
    await websocket.accept()

    # Spawn a pty
    shell = os.environ.get("SHELL", "/bin/bash")
    pid, fd = pty.openpty()

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"

    child_pid = os.fork()
    if child_pid == 0:
        # Child process
        os.close(fd)
        os.setsid()
        os.dup2(pid, 0)
        os.dup2(pid, 1)
        os.dup2(pid, 2)
        os.close(pid)
        os.chdir(workspace_path)
        os.execvpe(shell, [shell], env)

    os.close(pid)

    # Set non-blocking
    import fcntl as _fcntl
    flags = _fcntl.fcntl(fd, _fcntl.F_GETFL)
    _fcntl.fcntl(fd, _fcntl.F_SETFL, flags | os.O_NONBLOCK)

    async def read_pty():
        """Read from pty and send to WebSocket."""
        try:
            while True:
                await asyncio.sleep(0.01)
                try:
                    data = os.read(fd, 4096)
                    if data:
                        await websocket.send_bytes(data)
                except OSError:
                    break
        except Exception:
            pass

    async def write_pty():
        """Read from WebSocket and write to pty."""
        try:
            while True:
                data = await websocket.receive()
                if "bytes" in data:
                    os.write(fd, data["bytes"])
                elif "text" in data:
                    text = data["text"]
                    # Handle resize messages
                    if text.startswith('{"type":"resize"'):
                        import json
                        try:
                            msg = json.loads(text)
                            if msg.get("type") == "resize":
                                cols = msg.get("cols", 80)
                                rows = msg.get("rows", 24)
                                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                                fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
                        except Exception:
                            pass
                    else:
                        os.write(fd, text.encode())
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(read_pty(), write_pty())
    finally:
        try:
            os.close(fd)
            os.kill(child_pid, 9)
            os.waitpid(child_pid, 0)
        except Exception:
            pass
