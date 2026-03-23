"""Workspace file operations service.

Handles all file I/O for workspaces with path traversal protection.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any


def resolve_path(workspace_path: str, relative_path: str) -> Path:
    """Resolve a relative path within a workspace, preventing traversal."""
    base = Path(workspace_path).resolve()
    # Normalize and reject traversal attempts
    clean = os.path.normpath(relative_path).lstrip("/")
    if ".." in clean.split(os.sep):
        raise ValueError("Path traversal not allowed")
    resolved = (base / clean).resolve()
    if not str(resolved).startswith(str(base)):
        raise ValueError("Path traversal not allowed")
    return resolved


def list_files(workspace_path: str) -> list[dict[str, Any]]:
    """List all files in a workspace as a recursive tree."""
    base = Path(workspace_path)
    if not base.exists():
        return []
    return _walk_dir(base, base)


def _walk_dir(path: Path, base: Path) -> list[dict[str, Any]]:
    """Recursively walk a directory and build a file tree."""
    entries: list[dict[str, Any]] = []
    try:
        items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return entries

    for item in items:
        # Skip hidden files and common ignored directories
        if item.name.startswith(".") or item.name in ("__pycache__", "node_modules", ".git"):
            continue

        rel = str(item.relative_to(base))
        if item.is_dir():
            children = _walk_dir(item, base)
            entries.append({
                "name": item.name,
                "path": rel,
                "type": "directory",
                "size": None,
                "children": children,
            })
        else:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            entries.append({
                "name": item.name,
                "path": rel,
                "type": "file",
                "size": size,
                "children": None,
            })
    return entries


def read_file(workspace_path: str, relative_path: str) -> tuple[str, int]:
    """Read a file from the workspace. Returns (content, size)."""
    resolved = resolve_path(workspace_path, relative_path)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    content = resolved.read_text(errors="replace")
    return content, resolved.stat().st_size


def write_file(workspace_path: str, relative_path: str, content: str) -> None:
    """Write content to a file in the workspace. Creates parent dirs if needed."""
    resolved = resolve_path(workspace_path, relative_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)


def delete_file(workspace_path: str, relative_path: str) -> None:
    """Delete a file from the workspace."""
    resolved = resolve_path(workspace_path, relative_path)
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if resolved.is_dir():
        import shutil
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


def search_files(workspace_path: str, query: str, glob_pattern: str = "*") -> list[dict[str, Any]]:
    """Search for text in workspace files. Returns matching lines."""
    base = Path(workspace_path)
    results: list[dict[str, Any]] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for root, _dirs, files in os.walk(base):
        # Skip hidden and ignored directories
        rel_root = os.path.relpath(root, base)
        if any(part.startswith(".") or part in ("__pycache__", "node_modules") for part in Path(rel_root).parts):
            continue

        for fname in files:
            if not fnmatch.fnmatch(fname, glob_pattern):
                continue
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(base))
            try:
                with open(fpath, errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if pattern.search(line):
                            results.append({
                                "path": rel,
                                "line": i,
                                "content": line.rstrip()[:200],
                            })
                            if len(results) >= 100:
                                return results
            except (OSError, UnicodeDecodeError):
                continue

    return results
