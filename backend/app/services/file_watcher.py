"""File system watcher for workspace real-time sync.

Uses watchdog to monitor workspace directories and broadcast changes
to all connected WebSocket clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]


class WorkspaceEventHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Converts watchdog filesystem events to WebSocket broadcasts."""

    def __init__(self, workspace_id: str, workspace_path: str, loop: asyncio.AbstractEventLoop) -> None:
        self.workspace_id = workspace_id
        self.workspace_path = workspace_path
        self.loop = loop
        self._last_events: dict[str, float] = {}
        self._debounce_ms = 200

    def _should_ignore(self, path: str) -> bool:
        """Ignore hidden files, __pycache__, etc."""
        parts = Path(path).parts
        return any(p.startswith(".") or p in ("__pycache__", "node_modules", ".git") for p in parts)

    def _debounce(self, path: str) -> bool:
        """Simple debounce: skip if same path was handled within debounce window."""
        now = time.time() * 1000
        last = self._last_events.get(path, 0)
        if now - last < self._debounce_ms:
            return True
        self._last_events[path] = now
        return False

    def _relative_path(self, path: str) -> str:
        try:
            return str(Path(path).relative_to(self.workspace_path))
        except ValueError:
            return path

    def _broadcast(self, message: dict[str, Any]) -> None:
        from app.services.ws_manager import ws_manager

        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast(self.workspace_id, message),
            self.loop,
        )

    def on_created(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if event.is_directory or self._should_ignore(str(event.src_path)):
            return
        rel = self._relative_path(str(event.src_path))
        if self._debounce(rel):
            return

        content = None
        with contextlib.suppress(Exception):
            content = Path(str(event.src_path)).read_text(errors="replace")

        self._broadcast({
            "type": "file_created",
            "path": rel,
            "content": content,
            "change_type": "created",
            "source": "external",
        })

    def on_modified(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if event.is_directory or self._should_ignore(str(event.src_path)):
            return
        rel = self._relative_path(str(event.src_path))
        if self._debounce(rel):
            return

        content = None
        with contextlib.suppress(Exception):
            content = Path(str(event.src_path)).read_text(errors="replace")

        self._broadcast({
            "type": "file_changed",
            "path": rel,
            "content": content,
            "change_type": "modified",
            "source": "external",
        })

    def on_deleted(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if self._should_ignore(str(event.src_path)):
            return
        rel = self._relative_path(str(event.src_path))
        if self._debounce(rel):
            return

        self._broadcast({
            "type": "file_deleted",
            "path": rel,
            "change_type": "deleted",
            "source": "external",
        })

    def on_moved(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if self._should_ignore(str(str(event.src_path))):
            return
        old_rel = self._relative_path(str(str(event.src_path)))
        new_rel = self._relative_path(str(getattr(event, "dest_path", str(event.src_path))))

        self._broadcast({
            "type": "file_renamed",
            "old_path": old_rel,
            "new_path": new_rel,
            "change_type": "renamed",
            "source": "external",
        })


class WorkspaceWatcherManager:
    """Manages file system watchers for active workspaces.

    Reference-counted: starts watching when first WebSocket connects,
    stops when last disconnects.
    """

    def __init__(self) -> None:
        self._observers: dict[str, Any] = {}
        self._ref_counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start_watching(self, workspace_id: str, workspace_path: str) -> None:
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not installed — file watching disabled")
            return

        with self._lock:
            self._ref_counts[workspace_id] = self._ref_counts.get(workspace_id, 0) + 1

            if workspace_id in self._observers:
                return

            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    logger.warning("No event loop available for file watcher")
                    return

            handler = WorkspaceEventHandler(workspace_id, workspace_path, self._loop)
            observer = Observer()
            observer.schedule(handler, workspace_path, recursive=True)
            observer.daemon = True
            observer.start()
            self._observers[workspace_id] = observer
            logger.info("Started watching workspace %s at %s", workspace_id, workspace_path)

    def stop_watching(self, workspace_id: str) -> None:
        with self._lock:
            self._ref_counts[workspace_id] = max(0, self._ref_counts.get(workspace_id, 0) - 1)

            if self._ref_counts.get(workspace_id, 0) > 0:
                return

            observer = self._observers.pop(workspace_id, None)
            if observer:
                observer.stop()
                observer.join(timeout=2)
                logger.info("Stopped watching workspace %s", workspace_id)

    def stop_all(self) -> None:
        with self._lock:
            for _wid, observer in self._observers.items():
                observer.stop()
                observer.join(timeout=2)
            self._observers.clear()
            self._ref_counts.clear()


# Singleton
watcher_manager = WorkspaceWatcherManager()
