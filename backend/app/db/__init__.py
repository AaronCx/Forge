"""Pluggable database layer for AgentForge.

Usage:
    from app.db import get_db

    db = get_db()
    result = db.table("agents").select("*").eq("user_id", uid).execute()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.interface import DatabaseBackend

_db: DatabaseBackend | None = None


def init_db(backend: DatabaseBackend) -> None:
    """Set the global database backend. Called once at app startup."""
    global _db
    _db = backend


def get_db() -> DatabaseBackend:
    """Return the initialized database backend.

    In tests, use init_db() to set a mock backend, or patch app.db._db directly.
    """
    import app.db as _mod

    if _mod._db is None:
        raise RuntimeError("Database not initialized. Call init_db() during app startup.")
    return _mod._db


def create_db_from_env() -> DatabaseBackend:
    """Create the appropriate database backend based on environment/config.

    Checks in order:
    1. AGENTFORGE_DB_BACKEND env var ("sqlite" or "supabase")
    2. ~/.agentforge/config.toml [database] backend setting
    3. If SUPABASE_URL and SUPABASE_SERVICE_KEY are set → supabase
    4. Default → sqlite
    """
    backend_type = os.environ.get("AGENTFORGE_DB_BACKEND", "").lower()

    if not backend_type:
        # Try config file
        config_file = Path.home() / ".agentforge" / "config.toml"
        if config_file.exists():
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open(config_file, "rb") as f:
                config = tomllib.load(f)
            backend_type = config.get("database", {}).get("backend", "")

    if not backend_type:
        # Auto-detect: if Supabase env vars are set, use Supabase
        if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
            backend_type = "supabase"
        else:
            backend_type = "sqlite"

    if backend_type == "supabase":
        from app.db.supabase_backend import SupabaseBackend

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set for Supabase backend"
            )
        return SupabaseBackend(url, key)

    elif backend_type == "sqlite":
        from app.db.sqlite_backend import SQLiteBackend

        # Default path
        db_path = os.environ.get(
            "AGENTFORGE_SQLITE_PATH",
            str(Path.home() / ".agentforge" / "agentforge.db"),
        )
        # Check config for custom path
        config_file = Path.home() / ".agentforge" / "config.toml"
        if config_file.exists():
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open(config_file, "rb") as f:
                config = tomllib.load(f)
            db_path = config.get("database", {}).get("sqlite_path", db_path)
            # Expand ~ in path
            db_path = str(Path(db_path).expanduser())

        return SQLiteBackend(db_path)

    else:
        raise ValueError(f"Unknown database backend: {backend_type}")
