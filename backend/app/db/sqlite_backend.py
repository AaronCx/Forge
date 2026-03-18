"""SQLite database backend for AgentForge.

Implements the same fluent query builder API as the Supabase wrapper,
allowing all existing call sites to work without changes.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from app.db.interface import AuthBackend, DatabaseBackend, QueryBuilder, QueryResult
from app.db.sqlite_schema import FK_MAP, JSON_COLUMNS, SCHEMA


class SQLiteQueryBuilder(QueryBuilder):
    """Fluent query builder that accumulates state and builds SQL on execute()."""

    def __init__(self, db_path: str, table_name: str) -> None:
        self._db_path = db_path
        self._table = table_name
        self._operation: str = ""  # select, insert, update, delete, upsert
        self._select_columns: str = "*"
        self._count_mode: str | None = None
        self._insert_data: dict | list[dict] | None = None
        self._update_data: dict | None = None
        self._upsert_conflict: str = ""
        self._filters: list[tuple[str, str, Any]] = []  # (col, op, value)
        self._or_filter: str | None = None
        self._order_by: list[tuple[str, bool]] = []  # (col, desc)
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._single: bool = False
        self._json_cols: set[str] = JSON_COLUMNS.get(table_name, set())

    # --- Operation setters ---

    def select(self, columns: str = "*", *, count: str | None = None) -> SQLiteQueryBuilder:
        self._operation = "select"
        self._select_columns = columns
        self._count_mode = count
        return self

    def insert(self, data: dict[str, Any] | list[dict[str, Any]]) -> SQLiteQueryBuilder:
        self._operation = "insert"
        self._insert_data = data
        return self

    def update(self, data: dict[str, Any]) -> SQLiteQueryBuilder:
        self._operation = "update"
        self._update_data = data
        return self

    def delete(self) -> SQLiteQueryBuilder:
        self._operation = "delete"
        return self

    def upsert(
        self, data: dict[str, Any] | list[dict[str, Any]], *, on_conflict: str = ""
    ) -> SQLiteQueryBuilder:
        self._operation = "upsert"
        self._insert_data = data
        self._upsert_conflict = on_conflict
        return self

    # --- Filter setters ---

    def eq(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, "=", value))
        return self

    def neq(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, "!=", value))
        return self

    def in_(self, column: str, values: list[Any]) -> SQLiteQueryBuilder:
        self._filters.append((column, "IN", values))
        return self

    def gte(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, ">=", value))
        return self

    def lt(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, "<", value))
        return self

    def gt(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, ">", value))
        return self

    def lte(self, column: str, value: Any) -> SQLiteQueryBuilder:
        self._filters.append((column, "<=", value))
        return self

    def ilike(self, column: str, pattern: str) -> SQLiteQueryBuilder:
        self._filters.append((column, "LIKE", pattern))
        return self

    def or_(self, filters: str) -> SQLiteQueryBuilder:
        self._or_filter = filters
        return self

    # --- Modifiers ---

    def order(self, column: str, *, desc: bool = False) -> SQLiteQueryBuilder:
        self._order_by.append((column, desc))
        return self

    def limit(self, count: int) -> SQLiteQueryBuilder:
        self._limit_val = count
        return self

    def range(self, start: int, end: int) -> SQLiteQueryBuilder:
        self._offset_val = start
        self._limit_val = end - start + 1
        return self

    def single(self) -> SQLiteQueryBuilder:
        self._single = True
        self._limit_val = 1
        return self

    # --- Execute ---

    def execute(self) -> QueryResult:
        """Build and execute the SQL query synchronously via event loop bridge."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — use a nested run
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async())
                return future.result()
        else:
            return asyncio.run(self._execute_async())

    async def _execute_async(self) -> QueryResult:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")

            if self._operation == "select":
                return await self._exec_select(db)
            elif self._operation == "insert":
                return await self._exec_insert(db)
            elif self._operation == "update":
                return await self._exec_update(db)
            elif self._operation == "delete":
                return await self._exec_delete(db)
            elif self._operation == "upsert":
                return await self._exec_upsert(db)
            else:
                return QueryResult()

    # --- SQL builders ---

    def _build_where(self) -> tuple[str, list[Any]]:
        """Build WHERE clause from accumulated filters."""
        clauses: list[str] = []
        params: list[Any] = []

        for col, op, val in self._filters:
            # Handle dotted column names for joined table filters (e.g., "agents.user_id")
            actual_col = col.replace(".", "_dot_")  # placeholder — joins handle this
            if "." in col:
                # For join filters like "agents.user_id", use the table-qualified column
                actual_col = col

            if op == "IN":
                placeholders = ",".join("?" for _ in val)
                clauses.append(f"{actual_col} IN ({placeholders})")
                params.extend(val)
            elif val is None and op == "=":
                clauses.append(f"{actual_col} IS NULL")
            elif val is True and op == "=":
                clauses.append(f"{actual_col} = 1")
            elif val is False and op == "=":
                clauses.append(f"{actual_col} = 0")
            else:
                # Convert booleans to int for comparison
                if isinstance(val, bool):
                    val = int(val)
                clauses.append(f"{actual_col} {op} ?")
                params.append(val)

        # Handle or_ filter (PostgREST syntax)
        if self._or_filter:
            or_clause, or_params = self._parse_or_filter(self._or_filter)
            clauses.append(f"({or_clause})")
            params.extend(or_params)

        if clauses:
            return " WHERE " + " AND ".join(clauses), params
        return "", []

    def _parse_or_filter(self, filter_str: str) -> tuple[str, list[Any]]:
        """Parse PostgREST or_ filter syntax to SQL.

        Handles patterns used in the codebase:
        - "receiver_index.eq.5,receiver_index.is.null"
        - "and(sender_index.eq.1,receiver_index.eq.2),and(sender_index.eq.2,receiver_index.eq.1)"
        """
        parts: list[str] = []
        params: list[Any] = []

        # Split on top-level commas (not inside parentheses)
        segments = _split_top_level(filter_str, ",")

        for seg in segments:
            seg = seg.strip()
            if seg.startswith("and(") and seg.endswith(")"):
                # Parse and(...) group
                inner = seg[4:-1]
                inner_parts: list[str] = []
                for item in inner.split(","):
                    clause, p = self._parse_single_filter(item.strip())
                    inner_parts.append(clause)
                    params.extend(p)
                parts.append(f"({' AND '.join(inner_parts)})")
            else:
                clause, p = self._parse_single_filter(seg)
                parts.append(clause)
                params.extend(p)

        return " OR ".join(parts), params

    def _parse_single_filter(self, f: str) -> tuple[str, list[Any]]:
        """Parse a single PostgREST filter like 'column.op.value'."""
        dot_parts = f.split(".", 2)
        if len(dot_parts) < 2:
            return "1=1", []

        col = dot_parts[0]
        op = dot_parts[1]

        if op == "is" and len(dot_parts) > 2 and dot_parts[2] == "null":
            return f"{col} IS NULL", []
        elif op == "eq" and len(dot_parts) > 2:
            val = dot_parts[2]
            # Try to parse as int
            try:
                return f"{col} = ?", [int(val)]
            except ValueError:
                return f"{col} = ?", [val]
        elif op == "neq" and len(dot_parts) > 2:
            val = dot_parts[2]
            try:
                return f"{col} != ?", [int(val)]
            except ValueError:
                return f"{col} != ?", [val]

        return "1=1", []

    def _build_order(self) -> str:
        if not self._order_by:
            return ""
        parts = [f"{col} {'DESC' if desc else 'ASC'}" for col, desc in self._order_by]
        return " ORDER BY " + ", ".join(parts)

    def _build_limit_offset(self) -> str:
        parts = ""
        if self._limit_val is not None:
            parts += f" LIMIT {self._limit_val}"
        if self._offset_val is not None:
            parts += f" OFFSET {self._offset_val}"
        return parts

    def _parse_select_columns(self) -> tuple[list[str], list[dict]]:
        """Parse select columns and extract join specifications.

        Returns (columns, joins) where joins is a list of
        {"table": name, "columns": [...], "inner": bool, "alias": name}
        """
        joins: list[dict] = []
        columns: list[str] = []

        # Match patterns like "agents(name, description)" or "agents!inner(user_id)"
        pattern = r'(\w+)(!inner)?\(([^)]+)\)'
        remaining = self._select_columns

        for m in re.finditer(pattern, remaining):
            join_table = m.group(1)
            is_inner = m.group(2) is not None
            join_cols = [c.strip() for c in m.group(3).split(",")]
            joins.append({
                "table": join_table,
                "columns": join_cols,
                "inner": is_inner,
            })

        # Remove join patterns from select columns
        clean = re.sub(pattern, "", remaining).strip().rstrip(",").strip()
        if clean == "*" or clean == "":
            columns = ["*"]
        else:
            columns = [c.strip() for c in clean.split(",") if c.strip()]

        return columns, joins

    def _serialize_json(self, data: dict[str, Any]) -> dict[str, Any]:
        """Serialize JSON columns and booleans for SQLite storage."""
        result: dict[str, Any] = {}
        for k, v in data.items():
            if k in self._json_cols and v is not None:
                result[k] = json.dumps(v) if not isinstance(v, str) else v
            elif isinstance(v, bool):
                result[k] = int(v)  # type: ignore[assignment]
            elif v == "now()":
                result[k] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            else:
                result[k] = v
        return result

    def _deserialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Deserialize JSON columns and booleans from SQLite."""
        result = {}
        for k, v in row.items():
            if k in self._json_cols and isinstance(v, str):
                try:
                    result[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[k] = v
            elif k in ("is_template", "is_active", "enabled", "is_default", "is_enabled",
                       "computer_use_ready", "success", "steer_available", "drive_available",
                       "tmux_available"):
                result[k] = bool(v) if v is not None else False
            else:
                result[k] = v
        return result

    # --- Execution methods ---

    async def _exec_select(self, db: aiosqlite.Connection) -> QueryResult:
        columns, joins = self._parse_select_columns()

        # Build column list for main table
        if columns == ["*"]:
            col_sql = f"{self._table}.*"
        else:
            col_sql = ", ".join(f"{self._table}.{c}" for c in columns)

        # Build join SQL and add join columns
        join_sql = ""
        join_col_aliases: dict[str, list[str]] = {}  # join_table -> [cols]
        for j in joins:
            fk = FK_MAP.get((self._table, j["table"]))
            if not fk:
                continue
            src_col, tgt_col = fk
            join_type = "INNER JOIN" if j["inner"] else "LEFT JOIN"
            join_sql += f" {join_type} {j['table']} ON {self._table}.{src_col} = {j['table']}.{tgt_col}"
            for jc in j["columns"]:
                col_sql += f", {j['table']}.{jc} AS _join_{j['table']}_{jc}"
            join_col_aliases[j["table"]] = j["columns"]

        where_sql, params = self._build_where()
        order_sql = self._build_order()
        limit_sql = self._build_limit_offset()

        sql = f"SELECT {col_sql} FROM {self._table}{join_sql}{where_sql}{order_sql}{limit_sql}"

        cursor = await db.execute(sql, params)
        raw_rows = await cursor.fetchall()

        # Convert to dicts and nest join columns
        rows: list[dict[str, Any]] = []
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []

        for raw in raw_rows:
            row_dict = dict(zip(col_names, raw, strict=False))

            # Nest join columns under their table name
            for join_table, join_cols in join_col_aliases.items():
                nested: dict[str, Any] = {}
                all_null = True
                for jc in join_cols:
                    alias = f"_join_{join_table}_{jc}"
                    nested[jc] = row_dict.pop(alias, None)
                    if nested[jc] is not None:
                        all_null = False
                row_dict[join_table] = nested if not all_null else None

            rows.append(self._deserialize_row(row_dict))

        # Handle count
        count_val = None
        if self._count_mode == "exact":
            count_sql = f"SELECT COUNT(*) FROM {self._table}{join_sql}{where_sql}"
            cursor2 = await db.execute(count_sql, params)
            count_row = await cursor2.fetchone()
            count_val = count_row[0] if count_row else 0

        if self._single:
            return QueryResult(data=rows[0] if rows else None, count=count_val)
        return QueryResult(data=rows, count=count_val)

    async def _exec_insert(self, db: aiosqlite.Connection) -> QueryResult:
        data_list: list[dict[str, Any]] = self._insert_data if isinstance(self._insert_data, list) else [self._insert_data]  # type: ignore[list-item]
        results: list[dict[str, Any]] = []

        # Get actual table columns to avoid inserting into non-existent columns
        cursor = await db.execute(f"PRAGMA table_info({self._table})")
        table_cols = {row[1] for row in await cursor.fetchall()}

        for data in data_list:
            # Generate UUID if not present and table has id column
            if "id" not in data and "id" in table_cols:
                data["id"] = str(uuid.uuid4())
            # Set timestamps only if table has them
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            if "created_at" in table_cols:
                data.setdefault("created_at", now)
            if "updated_at" in table_cols:
                data.setdefault("updated_at", now)

            serialized = self._serialize_json(data)
            # Filter to only columns that exist in the table
            serialized = {k: v for k, v in serialized.items() if k in table_cols}
            cols = ", ".join(serialized.keys())
            placeholders = ", ".join("?" for _ in serialized)
            values = list(serialized.values())

            sql = f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})"
            await db.execute(sql, values)
            results.append(data)

        await db.commit()
        return QueryResult(data=results)

    async def _exec_update(self, db: aiosqlite.Connection) -> QueryResult:
        if not self._update_data:
            return QueryResult()

        # Check if table has updated_at column
        cursor = await db.execute(f"PRAGMA table_info({self._table})")
        table_cols = {row[1] for row in await cursor.fetchall()}

        data = dict(self._update_data)
        if "updated_at" in table_cols:
            data["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        serialized = self._serialize_json(data)

        set_clauses = ", ".join(f"{k} = ?" for k in serialized)
        set_params = list(serialized.values())

        where_sql, where_params = self._build_where()
        sql = f"UPDATE {self._table} SET {set_clauses}{where_sql}"

        await db.execute(sql, set_params + where_params)
        await db.commit()

        # Fetch updated rows
        select_sql = f"SELECT * FROM {self._table}{where_sql}"
        cursor = await db.execute(select_sql, where_params)
        rows = await cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description] if cursor.description else []
        result_rows = [self._deserialize_row(dict(zip(col_names, r, strict=False))) for r in rows]

        return QueryResult(data=result_rows)

    async def _exec_delete(self, db: aiosqlite.Connection) -> QueryResult:
        where_sql, params = self._build_where()
        sql = f"DELETE FROM {self._table}{where_sql}"
        await db.execute(sql, params)
        await db.commit()
        return QueryResult(data=[])

    async def _exec_upsert(self, db: aiosqlite.Connection) -> QueryResult:
        data_list: list[dict[str, Any]] = self._insert_data if isinstance(self._insert_data, list) else [self._insert_data]  # type: ignore[list-item]
        results: list[dict[str, Any]] = []

        # Get actual table columns
        cursor = await db.execute(f"PRAGMA table_info({self._table})")
        table_cols = {row[1] for row in await cursor.fetchall()}

        for data in data_list:
            if "id" not in data and "id" in table_cols:
                data["id"] = str(uuid.uuid4())
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            if "created_at" in table_cols:
                data.setdefault("created_at", now)
            if "updated_at" in table_cols:
                data.setdefault("updated_at", now)

            serialized = self._serialize_json(data)
            cols = ", ".join(serialized.keys())
            placeholders = ", ".join("?" for _ in serialized)
            values = list(serialized.values())

            if self._upsert_conflict:
                conflict_cols = self._upsert_conflict
                update_cols = [k for k in serialized if k not in conflict_cols.split(",")]
                update_set = ", ".join(f"{k} = excluded.{k}" for k in update_cols)
                sql = f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders}) ON CONFLICT({conflict_cols}) DO UPDATE SET {update_set}"
            else:
                sql = f"INSERT OR REPLACE INTO {self._table} ({cols}) VALUES ({placeholders})"

            await db.execute(sql, values)
            results.append(data)

        await db.commit()
        return QueryResult(data=results)


class SQLiteAuthBackend(AuthBackend):
    """Local JWT auth backend for SQLite mode."""

    def __init__(self, db_path: str, jwt_secret: str = "") -> None:
        self._db_path = db_path
        self._jwt_secret = jwt_secret or "agentforge-local-dev-secret"

    def get_user(self, token: str) -> Any:
        """Verify a local JWT and return a user-like object."""
        import jwt as pyjwt

        try:
            payload = pyjwt.decode(token, self._jwt_secret, algorithms=["HS256"])
        except pyjwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}") from e

        # Return an object that looks like Supabase's user object
        return _LocalUser(
            id=payload.get("sub", ""),
            email=payload.get("email", ""),
        )


class _LocalUser:
    """Mimics Supabase user object with .id attribute."""

    def __init__(self, id: str, email: str = "") -> None:
        self.id = id
        self.email = email


class SQLiteBackend(DatabaseBackend):
    """Database backend using SQLite."""

    def __init__(self, db_path: str, jwt_secret: str = "") -> None:
        self.db_path = str(Path(db_path).expanduser())
        self._auth_backend = SQLiteAuthBackend(self.db_path, jwt_secret)

    def table(self, name: str) -> SQLiteQueryBuilder:
        return SQLiteQueryBuilder(self.db_path, name)

    @property
    def auth(self) -> SQLiteAuthBackend:
        return self._auth_backend

    async def initialize(self) -> None:
        """Create all tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Execute each statement separately (SQLite doesn't support multi-statement)
            for statement in SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    await db.execute(statement)
            await db.commit()

    async def close(self) -> None:
        pass  # aiosqlite connections are opened per-query


def _split_top_level(s: str, sep: str) -> list[str]:
    """Split string on separator, but not inside parentheses."""
    result: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == sep and depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        result.append("".join(current))
    return result
