"""Tests for the eval-driven self-optimization loop.

These exercise the full pipeline against a real in-memory SQLite backend so that
lineage persistence is verified end to end. The LLM is mocked at two seams:

* agent output during eval — ``provider_registry.complete`` is patched so the
  produced text depends on the system prompt (baseline prompt fails, the
  "good" variant prompt passes).
* variant generation — an injected fake :class:`VariantGenerator` returns
  deterministic candidate prompts (no model call).
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.optimizer.service import OptimizerService
from app.services.optimizer.variant_generator import (
    LLMVariantGenerator,
    PromptVariant,
    VariantRequest,
)

GOOD_PROMPT = "Always answer with the magic word: banana"
BAD_PROMPT = "Be unhelpful and vague"


@pytest.fixture
def sqlite_backend(tmp_path):
    """Real, fully-initialized SQLite backend wired in as the global db.

    Restores the previously-installed backend (the conftest mock) afterwards so
    this real backend never leaks into other tests.
    """
    import app.db as db_mod
    from app.db import init_db
    from app.db.sqlite_backend import SQLiteBackend

    previous = db_mod._db
    db = SQLiteBackend(db_path=str(tmp_path / "optimizer.db"))
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(db.initialize())
    finally:
        loop.close()
    # Leave a fresh, open event loop installed: asyncio.run / loop.close above
    # would otherwise leave no current loop, breaking tests that call the
    # deprecated asyncio.get_event_loop().
    asyncio.set_event_loop(asyncio.new_event_loop())
    init_db(db)
    try:
        yield db
    finally:
        db_mod._db = previous


def _seed_agent_and_suite(db, *, user_id: str, system_prompt: str) -> tuple[str, str]:
    """Create an agent + an agent-targeted suite with one 'contains' case."""
    agent = (
        db.table("agents")
        .insert({"user_id": user_id, "name": "opt-agent", "system_prompt": system_prompt})
        .execute()
    ).data[0]
    agent_id = agent["id"]

    suite = (
        db.table("eval_suites")
        .insert({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": "magic-word-suite",
            "target_type": "agent",
            "target_id": agent_id,
        })
        .execute()
    ).data[0]
    suite_id = suite["id"]

    db.table("eval_cases").insert({
        "id": str(uuid.uuid4()),
        "suite_id": suite_id,
        "name": "must-say-banana",
        "input": {"text": "say the magic word"},
        "expected_output": {"text": "banana"},
        "grading_method": "contains",
        "grading_config": {"patterns": ["banana"]},
    }).execute()

    return agent_id, suite_id


def _patch_agent_output():
    """Patch the eval executor's LLM call so output depends on the system prompt."""

    async def fake_complete(*, messages, model=None, temperature=0, **kwargs):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        text = "banana" if "banana" in system else "i don't know"
        resp = MagicMock()
        resp.content = text
        resp.input_tokens = 1
        resp.output_tokens = 1
        resp.model = model or "test-model"
        return resp

    return patch(
        "app.services.evals.executor.provider_registry.complete",
        side_effect=fake_complete,
    )


class _FakeGenerator:
    """Deterministic variant generator — records the request, returns fixed variants."""

    def __init__(self, variants: list[PromptVariant]) -> None:
        self.variants = variants
        self.last_request: VariantRequest | None = None
        self.calls = 0

    async def __call__(self, request: VariantRequest) -> list[PromptVariant]:
        self.calls += 1
        self.last_request = request
        return list(self.variants)


@pytest.mark.asyncio
async def test_winner_is_highest_scoring_variant(sqlite_backend):
    """The variant whose prompt passes the suite must be selected as winner."""
    user_id = "user-1"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )

    gen = _FakeGenerator([
        PromptVariant(system_prompt="still vague and unhelpful", rationale="bad"),
        PromptVariant(system_prompt=GOOD_PROMPT, rationale="good"),
    ])
    svc = OptimizerService(variant_generator=gen)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    assert gen.calls == 1
    assert result["status"] == "awaiting_approval"
    # Winner score should be the perfect (1.0) GOOD_PROMPT variant.
    assert result["winner_score"] == pytest.approx(1.0)
    assert result["score_delta"] > 0

    lineage = await svc.get_lineage(result["id"], user_id)
    winners = [v for v in lineage["variants"] if v["is_winner"]]
    assert len(winners) == 1
    assert winners[0]["system_prompt"] == GOOD_PROMPT


@pytest.mark.asyncio
async def test_no_failures_short_circuits(sqlite_backend):
    """If the baseline eval has no failures, the loop does nothing further."""
    user_id = "user-2"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=GOOD_PROMPT
    )

    gen = _FakeGenerator([PromptVariant(system_prompt=GOOD_PROMPT)])
    svc = OptimizerService(variant_generator=gen)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    assert result["status"] == "no_failures"
    # Variant generator must not be invoked — nothing to optimize.
    assert gen.calls == 0
    lineage = await svc.get_lineage(result["id"], user_id)
    assert lineage["variants"] == []


@pytest.mark.asyncio
async def test_no_improvement_when_no_variant_beats_baseline(sqlite_backend):
    """If no candidate beats the baseline, status is no_improvement and no gate opens."""
    user_id = "user-3"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )

    gen = _FakeGenerator([
        PromptVariant(system_prompt="also unhelpful"),
        PromptVariant(system_prompt="equally vague"),
    ])
    approvals = MagicMock()
    approvals.create_approval = AsyncMock()
    svc = OptimizerService(variant_generator=gen, approvals=approvals)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    assert result["status"] == "no_improvement"
    approvals.create_approval.assert_not_called()


@pytest.mark.asyncio
async def test_winner_is_gated_not_auto_applied(sqlite_backend):
    """The winning prompt must NOT be written to the agent until approved."""
    user_id = "user-4"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )

    gen = _FakeGenerator([PromptVariant(system_prompt=GOOD_PROMPT, rationale="good")])
    svc = OptimizerService(variant_generator=gen)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    assert result["status"] == "awaiting_approval"
    assert result["approval_id"]

    # Agent's stored prompt is unchanged — promotion is gated.
    agent = (
        sqlite_backend.table("agents").select("*").eq("id", agent_id).single().execute()
    ).data
    assert agent["system_prompt"] == BAD_PROMPT

    # A pending approval exists carrying the candidate prompt.
    approval = (
        sqlite_backend.table("approvals").select("*").eq("id", result["approval_id"]).single().execute()
    ).data
    assert approval["status"] == "pending"
    assert approval["context"]["system_prompt"] == GOOD_PROMPT
    assert approval["context"]["kind"] == "prompt_optimization"


@pytest.mark.asyncio
async def test_apply_approved_promotes_winner(sqlite_backend):
    """After the approval is approved, apply_approved updates the live agent."""
    user_id = "user-5"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )

    gen = _FakeGenerator([PromptVariant(system_prompt=GOOD_PROMPT)])
    svc = OptimizerService(variant_generator=gen)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    approval_id = result["approval_id"]

    # Not yet approved → apply must refuse.
    assert await svc.apply_approved(approval_id=approval_id, user_id=user_id) is None

    # Approve it, then apply.
    from app.services.evals.approvals import approval_service

    await approval_service.approve(approval_id, user_id, "ship it")
    version = await svc.apply_approved(approval_id=approval_id, user_id=user_id)

    assert version is not None
    agent = (
        sqlite_backend.table("agents").select("*").eq("id", agent_id).single().execute()
    ).data
    assert agent["system_prompt"] == GOOD_PROMPT


@pytest.mark.asyncio
async def test_lineage_persisted_and_listable(sqlite_backend):
    """Lineage (run + per-variant scores) is persisted and retrievable."""
    user_id = "user-6"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )

    gen = _FakeGenerator([
        PromptVariant(system_prompt="vague one"),
        PromptVariant(system_prompt=GOOD_PROMPT),
    ])
    svc = OptimizerService(variant_generator=gen)

    with _patch_agent_output():
        result = await svc.optimize(user_id=user_id, agent_id=agent_id, suite_id=suite_id)

    lineage = await svc.get_lineage(result["id"], user_id)
    assert lineage["parent_prompt"] == BAD_PROMPT
    assert len(lineage["variants"]) == 2
    # Each variant carries its own eval run id and score.
    assert all(v["eval_run_id"] for v in lineage["variants"])
    assert any(v["score"] == pytest.approx(1.0) for v in lineage["variants"])

    runs = await svc.list_lineage(user_id, agent_id=agent_id)
    assert len(runs) == 1
    assert runs[0]["id"] == result["id"]


@pytest.mark.asyncio
async def test_suite_must_target_agent(sqlite_backend):
    """Optimizing against a suite that targets a different agent is rejected."""
    user_id = "user-7"
    agent_id, suite_id = _seed_agent_and_suite(
        sqlite_backend, user_id=user_id, system_prompt=BAD_PROMPT
    )
    other = (
        sqlite_backend.table("agents")
        .insert({"user_id": user_id, "name": "other", "system_prompt": "x"})
        .execute()
    ).data[0]

    svc = OptimizerService(variant_generator=_FakeGenerator([]))
    with pytest.raises(ValueError, match="must target the agent"):
        await svc.optimize(user_id=user_id, agent_id=other["id"], suite_id=suite_id)


# === Variant generator (LLM) parsing — model call mocked ===


@pytest.mark.asyncio
async def test_llm_variant_generator_parses_json():
    gen = LLMVariantGenerator()
    resp = MagicMock()
    resp.content = (
        '{"variants": [{"system_prompt": "p1", "rationale": "r1"}, '
        '{"system_prompt": "p2", "rationale": "r2"}]}'
    )
    resp.input_tokens = 1
    resp.output_tokens = 1

    with patch(
        "app.services.optimizer.variant_generator.provider_registry.complete",
        new=AsyncMock(return_value=resp),
    ):
        variants = await gen(VariantRequest(current_prompt="orig", failures=[], n=3))

    assert [v.system_prompt for v in variants] == ["p1", "p2"]
    assert variants[0].rationale == "r1"


@pytest.mark.asyncio
async def test_llm_variant_generator_handles_fenced_json():
    gen = LLMVariantGenerator()
    resp = MagicMock()
    resp.content = '```json\n{"variants": [{"system_prompt": "fenced"}]}\n```'
    resp.input_tokens = 1
    resp.output_tokens = 1

    with patch(
        "app.services.optimizer.variant_generator.provider_registry.complete",
        new=AsyncMock(return_value=resp),
    ):
        variants = await gen(VariantRequest(current_prompt="orig", failures=[], n=2))

    assert len(variants) == 1
    assert variants[0].system_prompt == "fenced"


# === API route ===


def test_optimizer_run_route_validates_target():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.routers.optimizer.optimizer_service") as mock_svc:
            mock_svc.optimize = AsyncMock(side_effect=ValueError("Eval suite must target the agent"))
            resp = TestClient(app).post(
                "/api/optimizer/runs",
                json={"agent_id": "a1", "suite_id": "s1", "n_variants": 2},
            )
        assert resp.status_code == 400
        assert "must target" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_optimizer_get_run_route():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.routers.optimizer.optimizer_service") as mock_svc:
            mock_svc.get_lineage = AsyncMock(return_value={
                "id": "opt1", "status": "awaiting_approval", "variants": [],
            })
            resp = TestClient(app).get("/api/optimizer/runs/opt1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_approval"
    finally:
        app.dependency_overrides.clear()


def test_optimizer_get_run_404():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.routers.optimizer.optimizer_service") as mock_svc:
            mock_svc.get_lineage = AsyncMock(return_value=None)
            resp = TestClient(app).get("/api/optimizer/runs/missing")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
