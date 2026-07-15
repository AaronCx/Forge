"""Phase 3 — one tool plane.

Verifies the plane aggregates every source into ToolSpecs, executes them behind
one permission policy (allow/ask/deny), routes ``ask`` through the approvals
inbox, keeps errors from killing the caller, and reproduces a node's Phase-0
golden output.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.toolplane import ExecContext, ToolPlane
from app.kernel.types import ToolUseBlock

GOLDEN = Path(__file__).parent / "parity" / "golden"


@pytest.fixture
def db(monkeypatch):
    """A real, empty SQLite backend so the plane's DB reads return real lists."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    # initialize() is async; run it on a fresh loop before the test's loop starts.
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


def _ctx(**kw):
    return ExecContext(user_id="u1", run_id="run1", **kw)


@pytest.mark.asyncio
async def test_list_returns_all_sources_over_seventy(db):
    plane = ToolPlane()
    specs = await plane.list_tools("u1", _ctx())
    names = {s.name for s in specs}
    assert len(specs) >= 70, f"only {len(specs)} specs"
    # a representative from each source is present
    assert "web_search" in names
    assert "node.json_validator" in names
    assert "cu.steer_click" in names
    assert "agent.spawn" in names
    assert "workspace.read" in names


@pytest.mark.asyncio
async def test_danger_levels_drive_defaults(db):
    plane = ToolPlane()
    specs = {s.name: s for s in await plane.list_tools("u1", _ctx())}
    assert specs["node.json_validator"].danger_level == "safe"
    assert specs["cu.steer_click"].danger_level == "caution"
    assert specs["cu.drive_run"].danger_level == "dangerous"
    assert specs["agent.spawn"].danger_level == "dangerous"
    assert specs["workspace.write"].danger_level == "caution"


@pytest.mark.asyncio
async def test_node_execution_matches_phase0_golden(db):
    plane = ToolPlane()
    call = ToolUseBlock(
        id="t1",
        name="node.json_validator",
        input={"schema": {"required": ["name"]}, "text": '{"name": "Alice", "age": 30}'},
    )
    result = await plane.execute(call, _ctx())
    assert not result.is_error
    golden = json.loads((GOLDEN / "node_json_validator.json").read_text())
    assert json.loads(result.output) == golden


@pytest.mark.asyncio
async def test_safe_and_workspace_tools_round_trip(db, tmp_path):
    # The Phase 3 exit flow: a conversation calls node.template_renderer then
    # workspace.read; both round-trip.
    (tmp_path / "notes.txt").write_text("hello from workspace")
    plane = ToolPlane()
    ctx = _ctx(workspace_root=str(tmp_path))

    r1 = await plane.execute(
        ToolUseBlock(id="a", name="node.template_renderer",
                     input={"template": "Hi {{name}}", "variables": {"name": "Bob"}}),
        ctx,
    )
    assert not r1.is_error
    assert json.loads(r1.output)["rendered"] == "Hi Bob"

    r2 = await plane.execute(
        ToolUseBlock(id="b", name="workspace.read", input={"path": "notes.txt"}), ctx
    )
    assert not r2.is_error
    assert json.loads(r2.output)["content"] == "hello from workspace"


@pytest.mark.asyncio
async def test_dangerous_tool_creates_approval_and_pends(db):
    plane = ToolPlane()
    call = ToolUseBlock(id="t", name="cu.drive_run", input={"command": "ls"})
    result = await plane.execute(call, _ctx())
    assert result.is_error
    assert "APPROVAL_PENDING" in result.output
    # an approval row now exists for this exact call (input-scoped key)
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    assert any(r["node_id"].startswith("tool:cu.drive_run:") for r in rows)


@pytest.mark.asyncio
async def test_command_blocklist_blocks_when_allowed(db):
    plane = ToolPlane()
    # Session override to allow so the tool actually executes and hits the
    # command blocklist inside the drive node.
    ctx = _ctx(session_overrides={"cu.drive_run": "allow"})
    call = ToolUseBlock(id="t", name="cu.drive_run", input={"command": "rm -rf /"})
    result = await plane.execute(call, ctx)
    assert result.is_error
    assert "blocked" in result.output.lower()
    # no approval created (it was allowed, not asked)
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    assert not rows


@pytest.mark.asyncio
async def test_deny_policy_returns_error_not_exception(db):
    db.table("tool_policies").insert(
        {"id": "p1", "user_id": "u1", "tool_name": "web_search", "decision": "deny"}
    ).execute()
    plane = ToolPlane()
    result = await plane.execute(
        ToolUseBlock(id="t", name="web_search", input={"query": "anything"}), _ctx()
    )
    assert result.is_error
    assert "denied by policy" in result.output


@pytest.mark.asyncio
async def test_unknown_tool_is_error_not_exception(db):
    plane = ToolPlane()
    result = await plane.execute(
        ToolUseBlock(id="t", name="node.does_not_exist", input={}), _ctx()
    )
    assert result.is_error
    assert "Unknown tool" in result.output


@pytest.mark.asyncio
async def test_approved_tool_executes(db):
    # Pre-approve a dangerous tool call (exact input), then it should run
    # instead of pending.
    from app.kernel.toolplane import approval_key
    from app.kernel.types import ToolSpec

    call = ToolUseBlock(id="t", name="cu.drive_run", input={"command": "shutdown"})
    spec = ToolSpec(name="cu.drive_run", description="", danger_level="dangerous")
    db.table("approvals").insert(
        {
            "id": "ap1",
            "user_id": "u1",
            "blueprint_run_id": "run1",
            "node_id": approval_key(spec, call, "tool"),
            "status": "approved",
        }
    ).execute()
    plane = ToolPlane()
    # command blocklisted so we can confirm it reached execution (blocked, not pending)
    result = await plane.execute(call, _ctx())
    assert result.is_error
    assert "blocked" in result.output.lower()  # executed and hit the blocklist


@pytest.mark.asyncio
async def test_approval_is_input_scoped_for_dangerous_tools(db):
    """Audit H1 regression: approving drive_run("ls") must NOT approve
    drive_run("rm -rf /") — each distinct dangerous invocation is reviewed."""
    plane = ToolPlane()
    ls_call = ToolUseBlock(id="t1", name="cu.drive_run", input={"command": "ls"})

    # First call pends and files an approval; a human approves that exact call.
    first = await plane.execute(ls_call, _ctx())
    assert "APPROVAL_PENDING" in first.output
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    assert len(rows) == 1
    db.table("approvals").update({"status": "approved"}).eq("id", rows[0]["id"]).execute()

    # The approved call now executes (drive node runs `ls` for real).
    approved = await plane.execute(ls_call, _ctx())
    assert "APPROVAL_PENDING" not in str(approved.output)

    # A different command on the same tool goes back to pending, never executes.
    rm_call = ToolUseBlock(id="t2", name="cu.drive_run", input={"command": "rm -rf /"})
    second = await plane.execute(rm_call, _ctx())
    assert "APPROVAL_PENDING" in second.output
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    pending = [r for r in rows if r["status"] == "pending"]
    assert len(pending) == 1  # a fresh review for the new input


@pytest.mark.asyncio
async def test_caution_tool_approval_scope_is_a_policy_choice(db):
    """approve_scope="call" makes even caution tools input-scoped."""
    plane = ToolPlane()
    ctx = _ctx(approve_scope="call")
    w1 = ToolUseBlock(id="t1", name="workspace.write",
                      input={"path": "a.txt", "content": "one"})
    result = await plane.execute(w1, ctx)
    assert "APPROVAL_PENDING" in result.output
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    db.table("approvals").update({"status": "approved"}).eq("id", rows[0]["id"]).execute()

    # Same tool, different input → a new review under call scope.
    w2 = ToolUseBlock(id="t2", name="workspace.write",
                      input={"path": "b.txt", "content": "two"})
    result2 = await plane.execute(w2, ctx)
    assert "APPROVAL_PENDING" in result2.output

    # Default tool scope: the per-tool approval covers other inputs.
    ctx_tool = _ctx()
    result3 = await plane.execute(
        ToolUseBlock(id="t3", name="workspace.write",
                     input={"path": "c.txt", "content": "three"}),
        ctx_tool,
    )
    assert "APPROVAL_PENDING" in result3.output
    rows = db.table("approvals").select("*").eq("user_id", "u1").execute().data
    tool_scoped = [r for r in rows if r["node_id"] == "tool:workspace.write"]
    assert len(tool_scoped) == 1
    db.table("approvals").update({"status": "approved"}).eq("id", tool_scoped[0]["id"]).execute()
    result4 = await plane.execute(
        ToolUseBlock(id="t4", name="workspace.write",
                     input={"path": "d.txt", "content": "four"}),
        ctx_tool,
    )
    assert "APPROVAL_PENDING" not in str(result4.output)


@pytest.mark.asyncio
async def test_register_source_hook_adds_tools(db):
    plane = ToolPlane()
    from app.kernel.types import ToolSpec

    async def fake_source(ctx):
        async def run(args, c):
            return {"echo": args}

        return [(ToolSpec(name="mcp.demo.echo", description="echo", source="mcp"), run)]

    plane.register_source(fake_source)
    specs = {s.name for s in await plane.list_tools("u1", _ctx())}
    assert "mcp.demo.echo" in specs
    result = await plane.execute(
        ToolUseBlock(id="t", name="mcp.demo.echo", input={"x": 1}), _ctx()
    )
    # mcp source defaults to safe danger → allowed
    assert not result.is_error
