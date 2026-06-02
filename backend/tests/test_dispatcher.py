"""PR-3 — dispatcher service + /api/dispatch SSE (text routing)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.dispatch import CatalogEntry, Decision
from app.services import dispatcher

CATALOG = [
    CatalogEntry(type="agent", id="agent-1", name="Summarizer", description="Summarizes run failures"),
    CatalogEntry(type="blueprint", id="bp-1", name="Report", description="Builds a report"),
]


# --- build_catalog ------------------------------------------------------------


def test_build_catalog_merges_agents_and_blueprints():
    with patch("app.db._db") as mock_db:
        agents = MagicMock(data=[{"id": "a1", "name": "A", "description": "desc a"}])
        blueprints = MagicMock(data=[{"id": "b1", "name": "B", "description": "desc b"}])
        # Two different .table(...).select(...).eq(...).execute() chains.
        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [agents, blueprints]

        catalog = dispatcher.build_catalog("user-1")

    assert [e.id for e in catalog] == ["a1", "b1"]
    assert catalog[0].type == "agent"
    assert catalog[1].type == "blueprint"


# --- parse_decision -----------------------------------------------------------


def test_parse_decision_route_valid_target():
    raw = json.dumps({
        "action": "route", "target_type": "agent", "target_id": "agent-1",
        "input_text": "summarize the failures", "rationale": "it summarizes failures",
    })
    d = dispatcher.parse_decision(raw, CATALOG)
    assert d.action == "route"
    assert d.target_id == "agent-1"
    assert d.input_text == "summarize the failures"


def test_parse_decision_hallucinated_target_downgrades_to_clarify():
    raw = json.dumps({"action": "route", "target_type": "agent", "target_id": "does-not-exist"})
    d = dispatcher.parse_decision(raw, CATALOG)
    assert d.action == "clarify"
    assert d.clarifying_question


def test_parse_decision_clarify():
    raw = json.dumps({"action": "clarify", "clarifying_question": "Which report?"})
    d = dispatcher.parse_decision(raw, CATALOG)
    assert d.action == "clarify"
    assert d.clarifying_question == "Which report?"


def test_parse_decision_none():
    d = dispatcher.parse_decision(json.dumps({"action": "none"}), CATALOG)
    assert d.action == "none"


def test_parse_decision_strips_code_fences():
    raw = '```json\n{"action": "route", "target_type": "blueprint", "target_id": "bp-1", "input_text": "go"}\n```'
    d = dispatcher.parse_decision(raw, CATALOG)
    assert d.action == "route"
    assert d.target_id == "bp-1"


def test_parse_decision_unparseable_returns_none():
    d = dispatcher.parse_decision("I think you should use the summarizer agent.", CATALOG)
    assert d.action == "none"


# --- route --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_returns_none_with_empty_catalog():
    d = await dispatcher.route("user-1", "do something", catalog=[])
    assert d.action == "none"
    assert d.cold_start is True


@pytest.mark.asyncio
async def test_route_sets_routing_cost():
    raw = json.dumps({"action": "route", "target_type": "agent", "target_id": "agent-1", "input_text": "go"})
    with patch("app.services.dispatcher._invoke", new=AsyncMock(return_value=(raw, 1000, 500, "gpt-4o-mini"))), \
         patch("app.services.token_tracker.token_tracker"):
        d = await dispatcher.route("user-1", "summarize", catalog=CATALOG)
    # gpt-4o-mini: 0.15/1M in + 0.60/1M out → 1000*0.15/1e6 + 500*0.60/1e6.
    assert d.routing_cost > 0


def test_targets_endpoint_returns_catalog(auth_client):
    with patch("app.services.dispatcher.build_catalog", return_value=CATALOG):
        resp = auth_client.get("/api/dispatch/targets")
    assert resp.status_code == 200
    data = resp.json()
    assert {e["id"] for e in data} == {"agent-1", "bp-1"}


@pytest.mark.asyncio
async def test_route_calls_llm_and_parses():
    raw = json.dumps({
        "action": "route", "target_type": "agent", "target_id": "agent-1",
        "input_text": "summarize failures", "rationale": "fits",
    })
    with patch("app.services.dispatcher._invoke", new=AsyncMock(return_value=(raw, 100, 20, "gpt-4o-mini"))), \
         patch("app.services.token_tracker.token_tracker") as mock_tracker:
        d = await dispatcher.route("user-1", "summarize the latest run failures", catalog=CATALOG)

    assert d.action == "route"
    assert d.target_id == "agent-1"
    # Routing tokens are tracked under provider 'dispatcher'.
    mock_tracker.record.assert_called_once()
    assert mock_tracker.record.call_args.kwargs["provider"] == "dispatcher"


@pytest.mark.asyncio
async def test_route_tracks_tokens_with_null_run_and_agent():
    raw = json.dumps({"action": "none"})
    with patch("app.services.dispatcher._invoke", new=AsyncMock(return_value=(raw, 5, 5, "gpt-4o-mini"))), \
         patch("app.services.token_tracker.token_tracker") as mock_tracker:
        await dispatcher.route("user-1", "x", catalog=CATALOG)

    kwargs = mock_tracker.record.call_args.kwargs
    assert kwargs["run_id"] is None
    assert kwargs["agent_id"] is None
    assert kwargs["step_number"] == 0


# --- attachments summary (PR-5) -----------------------------------------------


@pytest.mark.asyncio
async def test_build_attachments_summary_includes_doc_preview():
    attachments = [
        {"url": "file:///r.pdf", "kind": "document", "name": "r.pdf", "mime": "application/pdf"},
        {"url": "data:image/png;base64,AAA", "kind": "image", "name": "shot.png", "mime": "image/png"},
    ]
    with patch("app.services.extract.extract_text", new=AsyncMock(return_value="Quarterly revenue grew 20%.")):
        summary = await dispatcher.build_attachments_summary(attachments)

    assert "r.pdf (document): Quarterly revenue grew 20%." in summary
    assert "shot.png (image)" in summary


@pytest.mark.asyncio
async def test_build_attachments_summary_empty():
    assert await dispatcher.build_attachments_summary([]) == ""


@pytest.mark.asyncio
async def test_build_attachments_summary_handles_unreadable_doc():
    attachments = [{"url": "file:///x.pdf", "kind": "document", "name": "x.pdf", "mime": "application/pdf"}]
    with patch("app.services.extract.extract_text", new=AsyncMock(side_effect=OSError("nope"))):
        summary = await dispatcher.build_attachments_summary(attachments)
    assert "x.pdf (document): <unreadable>" in summary


# --- /api/dispatch endpoint ---------------------------------------------------


def _auth(mock_db):
    mock_user = MagicMock()
    mock_user.user = MagicMock(id="user-1")
    mock_db.auth.get_user.return_value = mock_user


def test_dispatch_routes_and_streams_run_with_heartbeat(client):
    """End-to-end: dispatch a text task → routing + done, run row + heartbeat created."""
    decision = Decision(
        action="route", target_type="agent", target_id="agent-1",
        input_text="summarize failures", rationale="it summarizes failures",
    )

    with patch("app.db._db") as mock_db, \
         patch("app.services.dispatcher.route", new=AsyncMock(return_value=decision)), \
         patch("app.routers.dispatch.AgentRunner") as mock_runner_cls, \
         patch("app.services.heartbeat.heartbeat_service") as mock_hb:
        _auth(mock_db)
        # agent fetch + run insert
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "agent-1", "user_id": "user-1", "name": "Summarizer", "workflow_steps": ["do it"]}
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "run-9"}])
        mock_hb.start.return_value = "hb-1"

        mock_runner = MagicMock()

        async def fake_execute(agent_config, input_text, **kwargs):
            yield {"type": "step", "content": "Step 1: do it", "tokens": 0}
            yield {"type": "token", "content": "done summarizing", "tokens": 5}

        mock_runner.execute = fake_execute
        mock_runner_cls.return_value = mock_runner

        resp = client.post("/api/dispatch?token=t", json={"message": "summarize the latest run failures"})
        body = resp.text

    assert resp.status_code == 200
    assert '"type": "routing"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert '"run_id": "run-9"' in body
    # The run was routed through the normal path → a heartbeat was created.
    mock_hb.start.assert_called_once()


def test_dispatch_none_when_no_agents(client):
    with patch("app.db._db") as mock_db, \
         patch("app.services.dispatcher.route", new=AsyncMock(return_value=Decision(action="none", rationale="empty"))):
        _auth(mock_db)
        resp = client.post("/api/dispatch?token=t", json={"message": "anything"})

    assert resp.status_code == 200
    assert '"type": "none"' in resp.text


def test_dispatch_clarify(client):
    decision = Decision(action="clarify", clarifying_question="Which report?")
    with patch("app.db._db") as mock_db, \
         patch("app.services.dispatcher.route", new=AsyncMock(return_value=decision)):
        _auth(mock_db)
        resp = client.post("/api/dispatch?token=t", json={"message": "make a report", "thread_id": "th-1"})

    assert resp.status_code == 200
    assert '"type": "clarify"' in resp.text
    assert "Which report?" in resp.text


def test_dispatch_rejects_bad_token(client):
    with patch("app.db._db") as mock_db:
        mock_db.auth.get_user.side_effect = Exception("nope")
        resp = client.post("/api/dispatch?token=bad", json={"message": "hi"})
    assert resp.status_code == 401
