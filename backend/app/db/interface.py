"""Abstract database interface for Forge.

Defines the contract that all database backends (Supabase, SQLite, etc.) must implement.
Uses a fluent query builder pattern that mirrors the supabase-py API so that existing
call sites require only an import swap, not logic changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    """Unified query result returned by all backends."""

    data: Any = field(default_factory=list)
    count: int | None = None


class QueryBuilder(ABC):
    """Fluent query builder that mirrors the supabase-py table API.

    Usage mirrors existing code exactly:
        db.table("agents").select("*").eq("user_id", uid).order("created_at", desc=True).execute()
    """

    @abstractmethod
    def select(self, columns: str = "*", *, count: str | None = None) -> QueryBuilder: ...

    @abstractmethod
    def insert(self, data: dict[str, Any] | list[dict[str, Any]]) -> QueryBuilder: ...

    @abstractmethod
    def update(self, data: dict[str, Any]) -> QueryBuilder: ...

    @abstractmethod
    def delete(self) -> QueryBuilder: ...

    @abstractmethod
    def upsert(
        self, data: dict[str, Any] | list[dict[str, Any]], *, on_conflict: str = ""
    ) -> QueryBuilder: ...

    @abstractmethod
    def eq(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def neq(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def in_(self, column: str, values: list[Any]) -> QueryBuilder: ...

    @abstractmethod
    def gte(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def lt(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def gt(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def lte(self, column: str, value: Any) -> QueryBuilder: ...

    @abstractmethod
    def ilike(self, column: str, pattern: str) -> QueryBuilder: ...

    @abstractmethod
    def or_(self, filters: str) -> QueryBuilder: ...

    @abstractmethod
    def order(self, column: str, *, desc: bool = False) -> QueryBuilder: ...

    @abstractmethod
    def limit(self, count: int) -> QueryBuilder: ...

    @abstractmethod
    def range(self, start: int, end: int) -> QueryBuilder: ...

    @abstractmethod
    def single(self) -> QueryBuilder: ...

    @abstractmethod
    def execute(self) -> QueryResult: ...


class AuthBackend(ABC):
    """Abstract auth backend."""

    @abstractmethod
    def get_user(self, token: str) -> Any:
        """Verify a token and return a user-like object with .id attribute."""
        ...


class DatabaseBackend(ABC):
    """Top-level database backend that all storage implementations must provide."""

    @abstractmethod
    def table(self, name: str) -> QueryBuilder:
        """Return a query builder for the given table."""
        ...

    @property
    @abstractmethod
    def auth(self) -> AuthBackend:
        """Return the auth backend."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the database (create tables, run migrations, etc.).

        No-op for Supabase (schema managed externally).
        Creates all tables for SQLite.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up connections."""
        ...
