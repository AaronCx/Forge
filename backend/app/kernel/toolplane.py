"""The tool plane — every Forge capability as a callable ``ToolSpec``.

One aggregator lists tools from all sources (builtin tools, blueprint nodes,
saved blueprints, computer-use actions, workspace ops, agent control) and one
executor runs any of them behind a single permission policy with uniform
timeout, error capture, and audit logging. MCP tools plug in later (Phase 5)
through ``register_source``.

Namespaces: builtins are bare names; everything else is ``<source>.<action>``
(``node.json_validator``, ``blueprint.<slug>``, ``cu.steer_click``,
``workspace.read``, ``agent.spawn``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.kernel.permissions import (
    PermissionResolver,
    PolicyDecision,
    load_user_tool_policies,
)
from app.kernel.types import DangerLevel, ToolResultBlock, ToolSpec, ToolUseBlock

logger = logging.getLogger(__name__)

# An executor takes the tool-call args and the exec context, returns raw output.
Executor = Callable[[dict[str, Any], "ExecContext"], Awaitable[Any]]
# A source yields (spec, executor) pairs for a given context (used by MCP later).
Source = Callable[["ExecContext"], Awaitable[list[tuple[ToolSpec, Executor]]]]


ApproveScope = Literal["call", "tool", "session"]


@dataclass
class ExecContext:
    """Everything a tool call needs to run under a policy."""

    user_id: str
    run_id: str = ""
    session_id: str = ""
    workspace_root: str = ""
    session_overrides: dict[str, PolicyDecision] = field(default_factory=dict)
    timeout: float = 60.0
    # How far a human approval of a *caution* tool extends: one exact call,
    # any call of that tool this run (default), or any call this session.
    # Dangerous tools are always approved per exact call, regardless.
    approve_scope: ApproveScope = "tool"


def approval_input_hash(tool_input: dict[str, Any]) -> str:
    """A stable hash of a tool call's input, for input-scoped approval keys."""
    canonical = json.dumps(tool_input, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def approval_key(spec: ToolSpec, tool_use: ToolUseBlock, scope: ApproveScope) -> str:
    """The approvals-table ``node_id`` for a tool call.

    Dangerous tools are keyed on the exact input so approving one invocation
    never green-lights a different one (audit H1); caution tools follow the
    context's ``approve_scope``.
    """
    if spec.danger_level == "dangerous" or scope == "call":
        return f"tool:{spec.name}:{approval_input_hash(tool_use.input)}"
    return f"tool:{spec.name}"


# --- danger levels ---

_NODE_CATEGORY_DANGER: dict[str, DangerLevel] = {
    "computer_use_gui": "caution",
    "computer_use_terminal": "dangerous",
    "computer_use_agent": "safe",
    "agent_control": "dangerous",
}
_DANGEROUS_DRIVE = {"drive_run", "drive_fanout", "drive_send"}
_AGENT_OP_DANGER: dict[str, DangerLevel] = {
    "spawn": "dangerous",
    "prompt": "dangerous",
    "stop": "dangerous",
    "monitor": "caution",
    "wait": "caution",
    "result": "caution",
}

# --- builtin tools (kept as LangChain tools; invoked via the public interface) ---

_BUILTIN_META: dict[str, tuple[str, dict[str, Any], list[str], DangerLevel]] = {
    "web_search": ("Search the web and return top results.", {"query": {"type": "string"}}, ["query"], "safe"),
    "document_reader": ("Extract text from a PDF/DOCX/TXT at a URL.", {"file_url": {"type": "string"}}, ["file_url"], "safe"),
    "code_executor": ("Execute sandboxed Python for pure computation.", {"code": {"type": "string"}}, ["code"], "caution"),
    "data_extractor": ("Extract structured JSON data from text.", {"text": {"type": "string"}}, ["text"], "safe"),
    "summarizer": ("Summarize long text into a concise summary.", {"text": {"type": "string"}}, ["text"], "safe"),
}


def _obj_schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "blueprint"


def _serialize(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


# --- node/blueprint schema helpers ---


def nodetype_to_toolspec(nt: Any) -> ToolSpec:
    """Build a ``node.<key>`` ToolSpec from a blueprint ``NodeType``."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for field_name, meta in (nt.input_schema or {}).items():
        if not isinstance(meta, dict):
            continue
        prop: dict[str, Any] = {"type": meta.get("type", "string")}
        if "description" in meta:
            prop["description"] = meta["description"]
        if "enum" in meta:
            prop["enum"] = meta["enum"]
        props[field_name] = prop
        if meta.get("required"):
            required.append(field_name)
    danger = _NODE_CATEGORY_DANGER.get(nt.category, "safe")
    return ToolSpec(
        name=f"node.{nt.key}",
        description=nt.description or nt.display_name,
        input_schema=_obj_schema(props, required),
        source="blueprint",
        source_id=nt.key,
        danger_level=danger,
    )


class ToolPlane:
    """Aggregates and executes tools from every source behind one policy."""

    def __init__(self) -> None:
        self._extra_sources: list[Source] = []

    def register_source(self, source: Source) -> None:
        """Register an additional tool source (used by MCP in Phase 5)."""
        self._extra_sources.append(source)

    # --- listing ---

    async def list_tools(
        self, user_id: str, context: ExecContext | None = None
    ) -> list[ToolSpec]:
        """List every available ToolSpec for a user/context (aggregated sources)."""
        index = await self._build_index(context or ExecContext(user_id=user_id))
        return [spec for spec, _ in index.values()]

    async def _build_index(
        self, ctx: ExecContext
    ) -> dict[str, tuple[ToolSpec, Executor]]:
        index: dict[str, tuple[ToolSpec, Executor]] = {}
        for spec, executor in self._builtin_entries():
            index[spec.name] = (spec, executor)
        for spec, executor in self._node_entries():
            index[spec.name] = (spec, executor)
        for spec, executor in self._cu_entries():
            index[spec.name] = (spec, executor)
        for spec, executor in self._agent_entries():
            index[spec.name] = (spec, executor)
        for spec, executor in self._workspace_entries():
            index[spec.name] = (spec, executor)
        for spec, executor in await self._blueprint_entries(ctx):
            index[spec.name] = (spec, executor)
        for source in self._extra_sources:
            try:
                for spec, executor in await source(ctx):
                    index[spec.name] = (spec, executor)
            except Exception as exc:  # noqa: BLE001 - one bad source must not break the plane
                logger.warning("tool source failed: %s", exc)
        return index

    # --- source: builtin tools ---

    def _builtin_entries(self) -> list[tuple[ToolSpec, Executor]]:
        entries: list[tuple[ToolSpec, Executor]] = []
        for name, (desc, props, required, danger) in _BUILTIN_META.items():
            spec = ToolSpec(
                name=name,
                description=desc,
                input_schema=_obj_schema(props, required),
                source="builtin",
                source_id=name,
                danger_level=danger,
            )
            entries.append((spec, self._make_builtin_executor(name)))
        return entries

    @staticmethod
    def _make_builtin_executor(name: str) -> Executor:
        async def run(args: dict[str, Any], ctx: ExecContext) -> Any:
            import inspect

            from app.services.tools.code_executor import code_executor
            from app.services.tools.data_extractor import data_extractor
            from app.services.tools.document_reader import document_reader
            from app.services.tools.summarizer import summarizer
            from app.services.tools.web_search import web_search

            tools: dict[str, Any] = {
                "web_search": web_search,
                "document_reader": document_reader,
                "code_executor": code_executor,
                "data_extractor": data_extractor,
                "summarizer": summarizer,
            }
            result = tools[name](**args)
            if inspect.isawaitable(result):
                result = await result
            return result

        return run

    # --- source: blueprint nodes ---

    def _node_entries(self) -> list[tuple[ToolSpec, Executor]]:
        from app.services.blueprint_nodes.registry import NODE_REGISTRY

        entries: list[tuple[ToolSpec, Executor]] = []
        for key, nt in NODE_REGISTRY.items():
            spec = nodetype_to_toolspec(nt)
            entries.append((spec, self._make_node_executor(key)))
        return entries

    @staticmethod
    def _make_node_executor(key: str) -> Executor:
        async def run(args: dict[str, Any], ctx: ExecContext) -> Any:
            return await _run_node(key, args, ctx)

        return run

    # --- source: computer-use actions (cu.<key>) ---

    def _cu_entries(self) -> list[tuple[ToolSpec, Executor]]:
        from app.services.blueprint_nodes.registry import NODE_REGISTRY

        cu_categories = {"computer_use_gui", "computer_use_terminal", "computer_use_agent"}
        entries: list[tuple[ToolSpec, Executor]] = []
        for key, nt in NODE_REGISTRY.items():
            if nt.category not in cu_categories:
                continue
            danger = self._cu_danger(key, nt.category)
            spec = ToolSpec(
                name=f"cu.{key}",
                description=nt.description or nt.display_name,
                input_schema=nodetype_to_toolspec(nt).input_schema,
                source="computer_use",
                source_id=key,
                danger_level=danger,
            )
            entries.append((spec, self._make_node_executor(key)))
        return entries

    @staticmethod
    def _cu_danger(key: str, category: str) -> DangerLevel:
        if key in _DANGEROUS_DRIVE:
            return "dangerous"
        if category == "computer_use_agent":
            return "safe"
        return "caution"

    # --- source: agent control (agent.<op>) ---

    def _agent_entries(self) -> list[tuple[ToolSpec, Executor]]:
        from app.services.blueprint_nodes.registry import NODE_REGISTRY

        entries: list[tuple[ToolSpec, Executor]] = []
        for op, danger in _AGENT_OP_DANGER.items():
            key = f"agent_{op}"
            nt = NODE_REGISTRY.get(key)
            if nt is None:
                continue
            spec = ToolSpec(
                name=f"agent.{op}",
                description=nt.description or nt.display_name,
                input_schema=nodetype_to_toolspec(nt).input_schema,
                source="computer_use",
                source_id=key,
                danger_level=danger,
            )
            entries.append((spec, self._make_node_executor(key)))
        return entries

    # --- source: workspace ops ---

    def _workspace_entries(self) -> list[tuple[ToolSpec, Executor]]:
        ops: list[tuple[str, str, dict[str, Any], list[str], DangerLevel]] = [
            ("read", "Read a file from the session workspace.",
             {"path": {"type": "string"}}, ["path"], "safe"),
            ("write", "Write a file in the session workspace.",
             {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], "caution"),
            ("list", "List the session workspace file tree.", {}, [], "safe"),
            ("search", "Search the session workspace for text.",
             {"query": {"type": "string"}, "glob": {"type": "string"}}, ["query"], "safe"),
        ]
        entries: list[tuple[ToolSpec, Executor]] = []
        for op, desc, props, required, danger in ops:
            spec = ToolSpec(
                name=f"workspace.{op}",
                description=desc,
                input_schema=_obj_schema(props, required),
                source="workspace",
                source_id=op,
                danger_level=danger,
            )
            entries.append((spec, self._make_workspace_executor(op)))
        return entries

    @staticmethod
    def _make_workspace_executor(op: str) -> Executor:
        async def run(args: dict[str, Any], ctx: ExecContext) -> Any:
            return await _run_workspace(op, args, ctx)

        return run

    # --- source: saved blueprints ---

    async def _blueprint_entries(self, ctx: ExecContext) -> list[tuple[ToolSpec, Executor]]:
        from app.db import get_db

        try:
            result = (
                get_db()
                .table("blueprints")
                .select("id, name, description, nodes")
                .eq("user_id", ctx.user_id)
                .execute()
            )
            rows = list(result.data) if isinstance(result.data, list) else []
            templates = (
                get_db().table("blueprints").select("id, name, description, nodes")
                .eq("is_template", True).execute()
            )
            if isinstance(templates.data, list):
                rows.extend(templates.data)
        except Exception as exc:  # noqa: BLE001 - blueprints are optional
            logger.debug("blueprint listing failed: %s", exc)
            return []

        entries: list[tuple[ToolSpec, Executor]] = []
        seen: set[str] = set()
        for row in rows:
            bid = row.get("id")
            if not bid or bid in seen:
                continue
            seen.add(bid)
            slug = _slugify(row.get("name", ""))
            danger = self._blueprint_danger(row.get("nodes") or [])
            spec = ToolSpec(
                name=f"blueprint.{slug}",
                description=row.get("description") or f"Run the '{row.get('name')}' blueprint.",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                source="blueprint",
                source_id=bid,
                danger_level=danger,
            )
            entries.append((spec, self._make_blueprint_executor(bid)))
        return entries

    @staticmethod
    def _blueprint_danger(nodes: list[dict[str, Any]]) -> DangerLevel:
        for node in nodes:
            t = node.get("type", "")
            if t.startswith(("drive_", "agent_", "steer_")):
                return "dangerous"
        return "caution"

    @staticmethod
    def _make_blueprint_executor(blueprint_id: str) -> Executor:
        async def run(args: dict[str, Any], ctx: ExecContext) -> Any:
            return await _run_blueprint(blueprint_id, args, ctx)

        return run

    # --- execution ---

    async def execute(self, tool_use: ToolUseBlock, ctx: ExecContext) -> ToolResultBlock:
        index = await self._build_index(ctx)
        entry = index.get(tool_use.name)
        if entry is None:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                output=f"Unknown tool: {tool_use.name}",
                is_error=True,
            )
        spec, executor = entry

        resolver = await self._resolver(ctx)
        decision = resolver.decide(spec)
        if decision == "deny":
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                output=f"Tool '{spec.name}' is denied by policy.",
                is_error=True,
            )
        if decision == "ask":
            state = await self._approval_state(spec, tool_use, ctx)
            if state == "rejected":
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    output=f"Tool '{spec.name}' was rejected by an approver.",
                    is_error=True,
                )
            if state == "pending":
                # Informational, not an error: error-shaped results push models
                # toward apologizing and giving up (audit M3). The approved call
                # is auto-retried by the session layer on the next message.
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    output=(
                        f"APPROVAL_PENDING: '{spec.name}' is awaiting human approval. "
                        "A request was filed in the approvals inbox — tell the user to "
                        "approve or reject it there (web: Dashboard → Approvals; CLI: "
                        "`forge ops approvals`). Do not retry this tool yourself; once "
                        "approved it runs automatically and the result arrives with the "
                        "user's next message."
                    ),
                    is_error=False,
                )

        try:
            result = await asyncio.wait_for(
                executor(dict(tool_use.input), ctx), timeout=ctx.timeout
            )
        except TimeoutError:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                output=f"Tool '{spec.name}' timed out after {ctx.timeout}s.",
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001 - a tool error must not kill the loop
            logger.info("tool '%s' failed: %s", spec.name, exc)
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                output=f"Tool '{spec.name}' error: {exc}",
                is_error=True,
            )

        logger.info("tool executed: %s (user=%s run=%s)", spec.name, ctx.user_id, ctx.run_id)
        return ToolResultBlock(
            tool_use_id=tool_use.id, output=_serialize(result), is_error=False
        )

    async def _resolver(self, ctx: ExecContext) -> PermissionResolver:
        policies = await load_user_tool_policies(ctx.user_id)
        return PermissionResolver(
            user_policies=policies, session_overrides=dict(ctx.session_overrides)
        )

    @staticmethod
    def _approval_run_id(ctx: ExecContext) -> str:
        if ctx.approve_scope == "session" and ctx.session_id:
            return ctx.session_id
        return ctx.run_id or ctx.session_id or "toolplane"

    @classmethod
    async def peek_approval_state(
        cls, spec: ToolSpec, tool_use: ToolUseBlock, ctx: ExecContext
    ) -> str | None:
        """The current approval status for this exact call, or None if no row exists.

        Read-only — never files a new approval request (used by the session
        layer to auto-retry calls whose approvals flipped to approved, M3).
        """
        from app.services.evals.approvals import approval_service

        node_id = approval_key(spec, tool_use, ctx.approve_scope)
        existing = await approval_service.get_approval_for_run(
            cls._approval_run_id(ctx), node_id
        )
        return existing.get("status") if existing else None

    @classmethod
    async def _approval_state(
        cls, spec: ToolSpec, tool_use: ToolUseBlock, ctx: ExecContext
    ) -> str:
        """Return 'approved' | 'rejected' | 'pending', creating a pending row if new."""
        from app.services.evals.approvals import approval_service

        state = await cls.peek_approval_state(spec, tool_use, ctx)
        if state in ("approved", "rejected"):
            return state
        if state is None:
            await approval_service.create_approval(
                user_id=ctx.user_id,
                blueprint_run_id=cls._approval_run_id(ctx),
                node_id=approval_key(spec, tool_use, ctx.approve_scope),
                context={
                    "message": f"Approve tool call: {spec.name}",
                    "tool": spec.name,
                    "danger_level": spec.danger_level,
                    "input": tool_use.input,
                },
            )
        return "pending"


# --- shared executors ---


async def _run_node(key: str, args: dict[str, Any], ctx: ExecContext) -> Any:
    from app.services.blueprint_engine import _ALL_AGENT, _ALL_DETERMINISTIC

    executor = _ALL_DETERMINISTIC.get(key) or _ALL_AGENT.get(key)
    if executor is None:
        raise KeyError(f"unknown node type: {key}")
    trusted = {
        "_user_id": ctx.user_id,
        "_run_id": ctx.run_id or ctx.session_id or "toolplane",
        "_node_id": f"tool:{key}",
    }
    inputs = {**args, **trusted}
    return await executor(dict(args), inputs)


async def _run_workspace(op: str, args: dict[str, Any], ctx: ExecContext) -> Any:
    from app.services import workspace_service as ws

    root = ctx.workspace_root
    if not root:
        raise ValueError("workspace tools require a workspace_root in the context")
    if op == "read":
        content, size = ws.read_file(root, args["path"])
        return {"content": content, "size": size}
    if op == "write":
        ws.write_file(root, args["path"], args.get("content", ""))
        return {"ok": True, "path": args["path"]}
    if op == "list":
        return {"files": ws.list_files(root)}
    if op == "search":
        return {"results": ws.search_files(root, args["query"], args.get("glob", "*"))}
    raise ValueError(f"unknown workspace op: {op}")


async def _run_blueprint(blueprint_id: str, args: dict[str, Any], ctx: ExecContext) -> Any:
    from app.db import get_db
    from app.services.blueprint_engine import blueprint_engine

    result = get_db().table("blueprints").select("*").eq("id", blueprint_id).execute()
    rows = result.data if isinstance(result.data, list) else []
    if not rows:
        raise ValueError(f"blueprint not found: {blueprint_id}")
    blueprint = rows[0]
    run_id = ctx.run_id or ctx.session_id or f"tool-{blueprint_id[:8]}"
    payload = {"text": args.get("text", ""), **{k: v for k, v in args.items() if k != "text"}}

    final: dict[str, Any] | None = None
    async for event in blueprint_engine.execute(
        blueprint=blueprint, input_payload=payload, user_id=ctx.user_id, run_id=run_id
    ):
        if event.get("type") == "result":
            final = event
    return final.get("data") if final else None


# Process-wide default plane; sources (MCP) register onto it in later phases.
tool_plane = ToolPlane()
