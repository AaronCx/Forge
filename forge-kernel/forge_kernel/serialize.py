"""JSON (de)serialization for kernel messages — the session event log format.

Round-trips ``KMessage``/``Block`` through plain dicts using each block's
``kind`` discriminator, so durable sessions (Phase 6) and any future persistence
store kernel state losslessly.
"""

from __future__ import annotations

import dataclasses
import types as _types
import typing
from dataclasses import asdict
from typing import Any, Literal, Union

from forge_kernel.types import (
    Block,
    BudgetSpec,
    ImageBlock,
    KMessage,
    SubAgentSpec,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    WorkflowSpec,
    WorkflowStage,
)


def block_to_dict(block: Block) -> dict[str, Any]:
    return asdict(block)


def block_from_dict(data: dict[str, Any]) -> Block:
    kind = data.get("kind")
    if kind == "text":
        return TextBlock(text=data.get("text", ""))
    if kind == "image":
        return ImageBlock(
            media_type=data.get("media_type", ""),
            data=data.get("data"),
            url=data.get("url"),
        )
    if kind == "tool_use":
        return ToolUseBlock(
            id=data.get("id", ""), name=data.get("name", ""), input=data.get("input", {})
        )
    if kind == "tool_result":
        return ToolResultBlock(
            tool_use_id=data.get("tool_use_id", ""),
            output=data.get("output", ""),
            is_error=data.get("is_error", False),
        )
    if kind == "thinking":
        return ThinkingBlock(text=data.get("text", ""))
    # Unknown block kind — preserve as text so nothing is silently dropped.
    return TextBlock(text=str(data))


def message_to_dict(message: KMessage) -> dict[str, Any]:
    return {"role": message.role, "blocks": [block_to_dict(b) for b in message.blocks]}


def message_from_dict(data: dict[str, Any]) -> KMessage:
    return KMessage(
        role=data.get("role", "user"),
        blocks=[block_from_dict(b) for b in data.get("blocks", [])],
    )


# --- workflow specs (Phase 9) ---


def workflow_spec_to_dict(spec: WorkflowSpec) -> dict[str, Any]:
    return asdict(spec)


def workflow_spec_from_dict(data: dict[str, Any]) -> WorkflowSpec:
    """Build a WorkflowSpec from planner/model output, tolerating extras."""

    def budget(d: dict[str, Any] | None) -> BudgetSpec | None:
        if not isinstance(d, dict):
            return None
        return BudgetSpec(
            max_tokens=d.get("max_tokens"), max_seconds=d.get("max_seconds")
        )

    def agent(d: dict[str, Any]) -> SubAgentSpec:
        tools = d.get("tools", "inherit")
        if not isinstance(tools, list | str):
            tools = "inherit"
        return SubAgentSpec(
            role=str(d.get("role", "worker")),
            prompt=str(d.get("prompt", "")),
            tools=tools,
            model=d.get("model"),
            budget=budget(d.get("budget")),
            success_criteria=str(d.get("success_criteria", "")),
            inputs=d.get("inputs") if isinstance(d.get("inputs"), dict) else {},
            outputs=[str(o) for o in d.get("outputs", []) if o],
        )

    def stage(d: dict[str, Any]) -> WorkflowStage:
        kind = d.get("kind", "single")
        if kind not in ("fanout", "single", "verify", "reduce"):
            kind = "single"
        return WorkflowStage(
            id=str(d.get("id", "")),
            kind=kind,
            agents=[agent(a) for a in d.get("agents", []) if isinstance(a, dict)],
            depends_on=[str(x) for x in d.get("depends_on", []) if x],
            concurrency=d.get("concurrency"),
            target=d.get("target"),
        )

    return WorkflowSpec(
        title=str(data.get("title", "Untitled workflow")),
        rationale=str(data.get("rationale", "")),
        stages=[stage(s) for s in data.get("stages", []) if isinstance(s, dict)],
        max_concurrent=int(data.get("max_concurrent", 16) or 16),
        max_agents_total=int(data.get("max_agents_total", 200) or 200),
        worker_model=data.get("worker_model"),
        verify=bool(data.get("verify", True)),
    )


def _type_to_schema(tp: Any) -> dict[str, Any]:
    """A minimal Python-type → JSON-schema mapper for the workflow dataclasses."""
    origin = typing.get_origin(tp)
    if origin in (Union, _types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        nullable = len(args) < len(typing.get_args(tp))
        schemas = [_type_to_schema(a) for a in args]
        merged = schemas[0] if len(schemas) == 1 else {"anyOf": schemas}
        if nullable:
            merged = dict(merged)
            merged["nullable"] = True  # informational; planner output is parsed leniently
        return merged
    if origin is Literal:
        values = list(typing.get_args(tp))
        return {"type": "string", "enum": values}
    if origin is list:
        (item,) = typing.get_args(tp) or (Any,)
        return {"type": "array", "items": _type_to_schema(item)}
    if origin is dict:
        return {"type": "object"}
    if dataclasses.is_dataclass(tp):
        return dataclass_json_schema(tp)
    return {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
    }.get(tp, {})


def dataclass_json_schema(cls: type) -> dict[str, Any]:
    """Generate a JSON schema from a (frozen) dataclass — never hand-maintained.

    The planner tool's ``input_schema`` for ``WorkflowSpec`` is produced from
    the dataclasses themselves, so the schema can not drift from the types.
    """
    hints = typing.get_type_hints(cls)
    props: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        if not f.init:  # discriminator fields like `kind`
            continue
        schema = _type_to_schema(hints[f.name])
        props[f.name] = schema
        has_default = (
            f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING
        )
        if not has_default:
            required.append(f.name)
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def workflow_spec_json_schema() -> dict[str, Any]:
    """The generated JSON schema for ``WorkflowSpec`` (planner tool input)."""
    return dataclass_json_schema(WorkflowSpec)
