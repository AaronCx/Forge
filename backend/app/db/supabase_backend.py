"""Supabase backend — thin wrapper around supabase-py.

This wrapper delegates every operation to the real supabase-py client,
ensuring zero behavior change from the pre-abstraction code. The only
transformation is converting APIResponse → QueryResult.
"""

from __future__ import annotations

from typing import Any

from app.db.interface import AuthBackend, DatabaseBackend, QueryBuilder, QueryResult


class SupabaseQueryBuilder(QueryBuilder):
    """Wraps the real supabase-py query builder with our abstract interface."""

    def __init__(self, builder: Any) -> None:
        self._builder = builder

    def select(self, columns: str = "*", *, count: str | None = None) -> SupabaseQueryBuilder:
        if count:
            self._builder = self._builder.select(columns, count=count)
        else:
            self._builder = self._builder.select(columns)
        return self

    def insert(self, data: dict[str, Any] | list[dict[str, Any]]) -> SupabaseQueryBuilder:
        self._builder = self._builder.insert(data)
        return self

    def update(self, data: dict[str, Any]) -> SupabaseQueryBuilder:
        self._builder = self._builder.update(data)
        return self

    def delete(self) -> SupabaseQueryBuilder:
        self._builder = self._builder.delete()
        return self

    def upsert(
        self, data: dict[str, Any] | list[dict[str, Any]], *, on_conflict: str = ""
    ) -> SupabaseQueryBuilder:
        if on_conflict:
            self._builder = self._builder.upsert(data, on_conflict=on_conflict)
        else:
            self._builder = self._builder.upsert(data)
        return self

    def eq(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.eq(column, value)
        return self

    def neq(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.neq(column, value)
        return self

    def in_(self, column: str, values: list[Any]) -> SupabaseQueryBuilder:
        self._builder = self._builder.in_(column, values)
        return self

    def gte(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.gte(column, value)
        return self

    def lt(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.lt(column, value)
        return self

    def gt(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.gt(column, value)
        return self

    def lte(self, column: str, value: Any) -> SupabaseQueryBuilder:
        self._builder = self._builder.lte(column, value)
        return self

    def ilike(self, column: str, pattern: str) -> SupabaseQueryBuilder:
        self._builder = self._builder.ilike(column, pattern)
        return self

    def or_(self, filters: str) -> SupabaseQueryBuilder:
        self._builder = self._builder.or_(filters)
        return self

    def order(self, column: str, *, desc: bool = False) -> SupabaseQueryBuilder:
        self._builder = self._builder.order(column, desc=desc)
        return self

    def limit(self, count: int) -> SupabaseQueryBuilder:
        self._builder = self._builder.limit(count)
        return self

    def range(self, start: int, end: int) -> SupabaseQueryBuilder:
        self._builder = self._builder.range(start, end)
        return self

    def single(self) -> SupabaseQueryBuilder:
        self._builder = self._builder.single()
        return self

    def execute(self) -> QueryResult:
        result = self._builder.execute()
        return QueryResult(
            data=result.data,
            count=getattr(result, "count", None),
        )


class SupabaseAuthBackend(AuthBackend):
    """Wraps supabase-py auth."""

    def __init__(self, auth_client: Any) -> None:
        self._auth = auth_client

    def get_user(self, token: str) -> Any:
        response = self._auth.get_user(token)
        if not response or not response.user:
            raise ValueError("Invalid token")
        return response.user


class SupabaseBackend(DatabaseBackend):
    """Database backend using Supabase (existing behavior)."""

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self._client = create_client(url, key)
        self._auth_backend = SupabaseAuthBackend(self._client.auth)

    def table(self, name: str) -> SupabaseQueryBuilder:
        return SupabaseQueryBuilder(self._client.table(name))

    @property
    def auth(self) -> SupabaseAuthBackend:
        return self._auth_backend

    async def initialize(self) -> None:
        pass  # Schema managed externally via Supabase dashboard/migrations

    async def close(self) -> None:
        pass  # supabase-py manages its own connections
