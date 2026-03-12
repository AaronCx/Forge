"""End-to-end tests covering all AgentForge features v1.0 through v1.7.

Tests API endpoints as a real user would exercise them, verifying routes exist,
return correct status codes, and handle auth correctly.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================
# Section 1: Authentication & User Management
# ============================================================


def test_protected_route_requires_auth(client):
    """1.3 — Protected routes reject unauthenticated requests."""
    response = client.get("/api/agents")
    assert response.status_code == 422  # Missing auth header


def test_protected_route_with_auth(auth_client):
    """1.3 — Protected routes accept authenticated requests."""
    with patch("app.routers.agents.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result
        response = auth_client.get(
            "/api/agents", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_api_key_crud(auth_client):
    """1.4 — API key management."""
    with patch("app.routers.api_keys.supabase") as mock_db:
        # Create
        key_data = {"id": "k1", "user_id": "test-user-id-123", "key_prefix": "af_test", "name": "test"}
        mock_result = MagicMock()
        mock_result.data = [key_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        response = auth_client.post(
            "/api/keys",
            json={"name": "test"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 201)


def test_health_endpoint(client):
    """0.2 — Health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_endpoint(client):
    """0.2 — Root endpoint returns version info."""
    response = client.get("/")
    data = response.json()
    assert data["name"] == "AgentForge API"
    assert data["version"] == "1.9.0"
    assert data["status"] == "running"


def test_openapi_docs(client):
    """0.2 — OpenAPI docs load."""
    response = client.get("/docs")
    assert response.status_code == 200


# ============================================================
# Section 2: Agent CRUD & Templates
# ============================================================


def test_create_agent(auth_client):
    """2.1 — Create agent."""
    with patch("app.routers.agents.supabase") as mock_db:
        agent_data = {
            "id": "a1",
            "user_id": "test-user-id-123",
            "name": "Test Agent",
            "description": "test",
            "system_prompt": "You are helpful.",
            "tools": ["web_search"],
            "workflow_steps": ["research", "write"],
            "model": None,
            "is_template": False,
            "created_at": "2026-03-12T00:00:00Z",
            "updated_at": "2026-03-12T00:00:00Z",
        }
        mock_result = MagicMock()
        mock_result.data = [agent_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        response = auth_client.post(
            "/api/agents",
            json={
                "name": "Test Agent",
                "description": "test",
                "system_prompt": "You are helpful.",
                "tools": ["web_search"],
                "workflow_steps": ["research", "write"],
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test Agent"


def test_list_agents(auth_client):
    """2.2 — List agents."""
    with patch("app.routers.agents.supabase") as mock_db:
        agent1 = {
            "id": "a1", "user_id": "test-user-id-123", "name": "Agent 1",
            "description": "", "system_prompt": "", "tools": [], "workflow_steps": [],
            "model": None, "is_template": False, "created_at": "2026-03-12T00:00:00Z",
            "updated_at": "2026-03-12T00:00:00Z",
        }
        agent2 = {**agent1, "id": "a2", "name": "Agent 2"}
        mock_result = MagicMock()
        mock_result.data = [agent1, agent2]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/agents", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2


def test_delete_agent(auth_client):
    """2.4 — Delete agent."""
    with patch("app.routers.agents.supabase") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "test-user-id-123"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        response = auth_client.delete(
            "/api/agents/a1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 204


def test_agent_templates(client):
    """2.5 — Templates exist."""
    with patch("app.routers.agents.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = [
            {"id": "t1", "name": "Document Analyzer", "is_template": True},
            {"id": "t2", "name": "Research Agent", "is_template": True},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = client.get("/api/agents/templates")
        assert response.status_code == 200


# ============================================================
# Section 3: Runs
# ============================================================


def test_list_runs(auth_client):
    """3.3 — Run history."""
    with patch("app.routers.runs.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/runs", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 4: Dashboard
# ============================================================


def test_dashboard_metrics(auth_client):
    """4.2 — Dashboard metrics endpoint."""
    with patch("app.routers.dashboard.supabase") as mock_db:
        # Mock agent count
        mock_agents = MagicMock()
        mock_agents.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_agents
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_agents

        response = auth_client.get(
            "/api/dashboard/metrics", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_dashboard_active(auth_client):
    """4.2 — Dashboard active agents."""
    with patch("app.routers.dashboard.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/dashboard/active", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 5: Cost Tracking
# ============================================================


def test_cost_summary(auth_client):
    """5.2 — Cost API."""
    with patch("app.routers.costs.token_tracker") as mock_tracker:
        mock_tracker.get_summary.return_value = {
            "total_cost": 0, "total_input_tokens": 0,
            "total_output_tokens": 0, "request_count": 0,
        }
        response = auth_client.get(
            "/api/costs/summary", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_cost_breakdown(auth_client):
    """5.2 — Cost breakdown."""
    with patch("app.routers.costs.token_tracker") as mock_tracker:
        mock_tracker.get_breakdown.return_value = []
        response = auth_client.get(
            "/api/costs/breakdown?group_by=model",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_cost_projection(auth_client):
    """5.2 — Cost projection."""
    with patch("app.routers.costs.token_tracker") as mock_tracker:
        mock_tracker.get_projection.return_value = {
            "daily_average": 0, "monthly_projection": 0,
        }
        response = auth_client.get(
            "/api/costs/projection", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 6: Multi-Model Providers
# ============================================================


def test_provider_models(auth_client):
    """6.2 — Model listing."""
    with patch("app.routers.providers.provider_registry") as mock_reg:
        mock_reg.list_all_models = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/providers/models",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_provider_health(auth_client):
    """6.3 — Provider health."""
    with patch("app.routers.providers.provider_registry") as mock_reg:
        mock_reg.health_check_all = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/providers/health",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# ============================================================
# Section 7: Blueprints
# ============================================================


def test_blueprint_crud(auth_client):
    """7.1 — Blueprint CRUD."""
    with patch("app.routers.blueprints.supabase") as mock_db:
        bp_data = {
            "id": "bp-1",
            "user_id": "test-user-id-123",
            "name": "Test BP",
            "description": "test",
            "version": 1,
            "is_template": False,
            "nodes": [{"id": "n1", "type": "llm_generate", "config": {}, "dependencies": []}],
            "context_config": {},
            "tool_scope": [],
            "retry_policy": {"max_retries": 2},
            "output_schema": None,
            "created_at": "2026-03-12T00:00:00Z",
            "updated_at": "2026-03-12T00:00:00Z",
        }
        mock_result = MagicMock()
        mock_result.data = [bp_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        response = auth_client.post(
            "/api/blueprints",
            json={
                "name": "Test BP",
                "description": "test",
                "nodes": [{"id": "n1", "type": "llm_generate", "config": {}, "dependencies": []}],
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201


def test_blueprint_node_types(client):
    """7.3 — Node type registry."""
    response = client.get("/api/blueprints/node-types")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 44  # 10 det + 5 agent + 12 steer + 6 drive + 4 cu_agent + 6 agent_control + 1 recording

    # Check categories
    categories = {d["category"] for d in data}
    assert "context" in categories
    assert "transform" in categories
    assert "validate" in categories
    assert "agent" in categories
    assert "output" in categories
    assert "computer_use_gui" in categories
    assert "computer_use_terminal" in categories
    assert "computer_use_agent" in categories
    assert "agent_control" in categories

    # Check specific nodes exist
    keys = {d["key"] for d in data}
    assert "fetch_url" in keys
    assert "llm_generate" in keys
    assert "agent_spawn" in keys
    assert "recording_control" in keys
    assert "approval_gate" in keys
    assert "knowledge_retrieval" in keys
    assert "steer_see" in keys
    assert "drive_run" in keys
    assert "cu_planner" in keys


def test_blueprint_node_types_filtered(client):
    """7.3 — Node types filtered by category."""
    response = client.get("/api/blueprints/node-types?category=agent")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert all(d["node_class"] == "agent" for d in data)


def test_blueprint_templates(client):
    """7.2 — Blueprint templates."""
    with patch("app.routers.blueprints.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = client.get("/api/blueprints/templates")
        assert response.status_code == 200


# ============================================================
# Section 8: MCP Integration
# ============================================================


def test_mcp_connections(auth_client):
    """8.1 — MCP connection listing."""
    with patch("app.routers.mcp.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/mcp/connections", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 9: Event Triggers
# ============================================================


def test_triggers_list(auth_client):
    """9.3 — Trigger listing."""
    with patch("app.routers.triggers.trigger_service") as mock_svc:
        mock_svc.list_triggers = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/triggers", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 10: Orchestration
# ============================================================


def test_orchestrate_groups(auth_client):
    """10.6 — Orchestration groups listing."""
    with patch("app.routers.orchestration.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/orchestrate/groups", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


# ============================================================
# Section 11: Inter-Agent Messaging
# ============================================================


def test_messages_list(auth_client):
    """11.1 — Message listing."""
    with patch("app.routers.messages.supabase") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/messages/group-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# ============================================================
# Section 12: Eval Framework
# ============================================================


def test_eval_suite_crud(auth_client):
    """12.1 — Eval suite CRUD."""
    with patch("app.routers.evals.supabase") as mock_db:
        # List suites
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/evals/suites", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_eval_grading_methods():
    """12.3 — Eval grading methods exist."""
    from app.services.evals.grading import (
        grade_contains,
        grade_exact_match,
        grade_json_schema,
    )

    # exact_match
    result = grade_exact_match("hello", "hello", {})
    assert result["passed"] is True

    result = grade_exact_match("hello", "world", {})
    assert result["passed"] is False

    # contains
    result = grade_contains("hello world", "hello", {"expected_strings": ["hello"]})
    assert result["passed"] is True

    # json_schema
    result = grade_json_schema(
        '{"name": "test"}',
        "",
        {"schema": {"required": ["name"]}},
    )
    assert result["passed"] is True


# ============================================================
# Section 13: Human-in-the-Loop
# ============================================================


def test_approvals_list(auth_client):
    """13.1 — Approvals listing."""
    with patch("app.routers.approvals.approval_service") as mock_svc:
        mock_svc.list_pending = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/approvals?status=pending",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_approval_gate_node_exists():
    """13.5 — Approval gate node in registry."""
    from app.services.blueprint_nodes.registry import get_node_type

    node = get_node_type("approval_gate")
    assert node is not None
    assert node.category == "validate"
    assert node.node_class == "deterministic"


# ============================================================
# Section 14: Observability Traces
# ============================================================


def test_traces_list(auth_client):
    """14.2 — Trace listing."""
    with patch("app.routers.traces.trace_service") as mock_svc:
        mock_svc.list_traces = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/traces", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_traces_stats(auth_client):
    """14.2 — Trace stats."""
    with patch("app.routers.traces.trace_service") as mock_svc:
        mock_svc.get_trace_stats = AsyncMock(return_value={
            "total_spans": 0,
            "error_count": 0,
            "error_rate": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0,
            "by_type": {},
        })
        response = auth_client.get(
            "/api/traces/stats", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_trace_not_found(auth_client):
    """14.2 — Trace 404."""
    with patch("app.routers.traces.trace_service") as mock_svc:
        mock_svc.get_trace = AsyncMock(return_value=None)
        response = auth_client.get(
            "/api/traces/nonexistent", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 404


# ============================================================
# Section 15: Prompt Versioning
# ============================================================


def test_prompt_versions_list(auth_client):
    """15.2 — Version history."""
    with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
        mock_svc.list_versions = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/agents/agent-1/prompts",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_prompt_version_create(auth_client):
    """15.1 — Version creation."""
    with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
        mock_svc.create_version = AsyncMock(return_value={
            "id": "pv-1",
            "agent_id": "agent-1",
            "version_number": 1,
            "system_prompt": "test",
            "change_summary": "initial",
            "is_active": True,
            "created_at": "2026-03-12T00:00:00Z",
        })
        response = auth_client.post(
            "/api/agents/agent-1/prompts",
            json={"system_prompt": "test", "change_summary": "initial"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_prompt_version_rollback(auth_client):
    """15.4 — Version rollback."""
    with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
        mock_svc.rollback = AsyncMock(return_value={
            "id": "pv-2",
            "agent_id": "agent-1",
            "version_number": 2,
            "is_active": True,
            "created_at": "2026-03-12T00:00:00Z",
        })
        response = auth_client.post(
            "/api/prompts/pv-1/rollback",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# ============================================================
# Section 16: Knowledge Base & RAG
# ============================================================


def test_knowledge_collections_list(auth_client):
    """16.1 — Knowledge base listing."""
    with patch("app.routers.knowledge.knowledge_service") as mock_svc:
        mock_svc.list_collections = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/knowledge/collections",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_knowledge_collection_create(auth_client):
    """16.1 — Knowledge base creation."""
    with patch("app.routers.knowledge.knowledge_service") as mock_svc:
        mock_svc.create_collection = AsyncMock(return_value={
            "id": "kc-1",
            "name": "Test KB",
            "description": "",
            "document_count": 0,
            "chunk_count": 0,
        })
        response = auth_client.post(
            "/api/knowledge/collections",
            json={"name": "Test KB"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_knowledge_search(auth_client):
    """16.3 — Semantic search."""
    with patch("app.routers.knowledge.knowledge_service") as mock_svc:
        mock_svc.search = AsyncMock(return_value=[
            {"chunk_id": "c1", "content": "test", "similarity": 0.95},
        ])
        response = auth_client.post(
            "/api/knowledge/collections/kc-1/search",
            json={"query": "test"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1


def test_knowledge_retrieval_node():
    """16.5 — Knowledge retrieval node exists."""
    from app.services.blueprint_nodes.registry import get_node_type

    node = get_node_type("knowledge_retrieval")
    assert node is not None
    assert node.category == "context"
    assert node.node_class == "deterministic"


# ============================================================
# Section 17: Marketplace & Teams
# ============================================================


def test_marketplace_listings(client):
    """17.2 — Browse marketplace."""
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.list_listings = AsyncMock(return_value=[])
        response = client.get("/api/marketplace/listings")
        assert response.status_code == 200


def test_marketplace_publish(auth_client):
    """17.1 — Publish listing."""
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.publish_listing = AsyncMock(return_value={
            "id": "l-1",
            "title": "My Workflow",
            "status": "published",
            "rating_avg": 0,
        })
        response = auth_client.post(
            "/api/marketplace/listings",
            json={"blueprint_id": "bp-1", "title": "My Workflow"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201


def test_marketplace_rate_invalid(auth_client):
    """17.4 — Rating validation."""
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.rate_listing = AsyncMock()
        # Rating too high
        response = auth_client.post(
            "/api/marketplace/listings/l-1/rate",
            json={"rating": 6},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 400

        # Rating too low
        response = auth_client.post(
            "/api/marketplace/listings/l-1/rate",
            json={"rating": 0},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 400


def test_marketplace_rate_valid(auth_client):
    """17.4 — Valid rating."""
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.rate_listing = AsyncMock(return_value={
            "id": "r-1", "rating": 4, "review": "Great!",
        })
        response = auth_client.post(
            "/api/marketplace/listings/l-1/rate",
            json={"rating": 4, "review": "Great!"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_marketplace_listing_not_found(client):
    """17.2 — Listing 404."""
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.get_listing = AsyncMock(return_value=None)
        response = client.get("/api/marketplace/listings/nonexistent")
        assert response.status_code == 404


def test_org_crud(auth_client):
    """17.5 — Organization CRUD."""
    with patch("app.routers.organizations.org_service") as mock_svc:
        # Create
        mock_svc.create_org = AsyncMock(return_value={
            "id": "org-1", "name": "Team A", "slug": "team-a",
        })
        response = auth_client.post(
            "/api/organizations",
            json={"name": "Team A"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Team A"

        # List
        mock_svc.list_orgs = AsyncMock(return_value=[
            {"id": "org-1", "name": "Team A", "slug": "team-a"},
        ])
        response = auth_client.get(
            "/api/organizations",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1


def test_org_member_rbac(auth_client):
    """17.5 — RBAC enforcement."""
    with patch("app.routers.organizations.org_service") as mock_svc:
        # Viewer cannot add members
        mock_svc.get_user_role = AsyncMock(return_value="viewer")
        response = auth_client.post(
            "/api/organizations/org-1/members",
            json={"user_id": "u2", "role": "member"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 403

        # Member cannot add members
        mock_svc.get_user_role = AsyncMock(return_value="member")
        response = auth_client.post(
            "/api/organizations/org-1/members",
            json={"user_id": "u2", "role": "member"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 403

        # Admin can add members
        mock_svc.get_user_role = AsyncMock(return_value="admin")
        mock_svc.add_member = AsyncMock(return_value={
            "id": "m-1", "org_id": "org-1", "user_id": "u2", "role": "member",
        })
        response = auth_client.post(
            "/api/organizations/org-1/members",
            json={"user_id": "u2", "role": "member"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201


def test_org_not_found(auth_client):
    """17.5 — Org 404."""
    with patch("app.routers.organizations.org_service") as mock_svc:
        mock_svc.get_org = AsyncMock(return_value=None)
        response = auth_client.get(
            "/api/organizations/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


# ============================================================
# Section 18: Cross-Feature — Input Validation
# ============================================================


def test_malformed_json(client):
    """19.2 — Malformed JSON returns 422."""
    response = client.post(
        "/api/agents",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_empty_required_fields(auth_client):
    """19.2 — Empty required fields validation."""
    response = auth_client.post(
        "/api/agents",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 422


# ============================================================
# Section 19: Node Executor Tests
# ============================================================


@pytest.mark.asyncio
async def test_text_splitter_e2e():
    """7.3 — text_splitter node works."""
    from app.services.blueprint_nodes.deterministic import execute_text_splitter

    result = await execute_text_splitter(
        {"chunk_size": 20, "overlap": 5},
        {"text": "This is a longer text that should be split into multiple chunks."},
    )
    assert "chunks" in result
    assert result["chunk_count"] >= 2


@pytest.mark.asyncio
async def test_template_renderer_e2e():
    """7.3 — template_renderer node works."""
    from app.services.blueprint_nodes.deterministic import execute_template_renderer

    result = await execute_template_renderer(
        {"template": "Hello {{name}}!"},
        {"name": "World"},
    )
    assert result["rendered"] == "Hello World!"


@pytest.mark.asyncio
async def test_json_validator_e2e():
    """7.3 — json_validator node works."""
    from app.services.blueprint_nodes.deterministic import execute_json_validator

    # Valid
    result = await execute_json_validator(
        {"data": '{"name": "test"}', "schema": {"required": ["name"]}},
        {},
    )
    assert result["valid"] is True

    # Invalid
    result = await execute_json_validator(
        {"data": '{"other": "test"}', "schema": {"required": ["name"]}},
        {},
    )
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_output_formatter_e2e():
    """7.3 — output_formatter node works."""
    from app.services.blueprint_nodes.deterministic import execute_output_formatter

    result = await execute_output_formatter(
        {"format": "json"},
        {"text": '{"key": "value"}'},
    )
    assert "formatted" in result
    parsed = json.loads(result["formatted"])
    assert parsed["key"] == "value"


# ============================================================
# Section 20: Topological Sort (Blueprint Engine)
# ============================================================


def test_topological_sort_e2e():
    """7.4 — Blueprint engine DAG sorting."""
    from app.services.blueprint_engine import _topological_sort

    # Linear
    nodes = [
        {"id": "a", "dependencies": []},
        {"id": "b", "dependencies": ["a"]},
        {"id": "c", "dependencies": ["b"]},
    ]
    layers = _topological_sort(nodes)
    assert len(layers) == 3

    # Parallel
    nodes = [
        {"id": "a", "dependencies": []},
        {"id": "b", "dependencies": []},
        {"id": "c", "dependencies": ["a", "b"]},
    ]
    layers = _topological_sort(nodes)
    assert len(layers) == 2
    assert set(layers[0]) == {0, 1}

    # Cycle detection
    nodes = [
        {"id": "a", "dependencies": ["b"]},
        {"id": "b", "dependencies": ["a"]},
    ]
    with pytest.raises(ValueError, match="cycle"):
        _topological_sort(nodes)


# ============================================================
# Context Assembly
# ============================================================


def test_context_assembly_e2e():
    """7.4 — Context assembly works."""
    from app.services.blueprint_nodes.context_assembly import assemble_context

    outputs = {
        "node_1": {"text": "Python is great"},
        "node_2": {"text": "JavaScript is popular"},
    }
    result = assemble_context(outputs, objective="programming")
    assert "Python" in result
    assert "JavaScript" in result


def test_context_assembly_budget():
    """7.4 — Context assembly respects budget."""
    from app.services.blueprint_nodes.context_assembly import assemble_context

    outputs = {"big": {"text": "X" * 50000}}
    result = assemble_context(outputs, max_tokens=100)
    assert len(result) < 5000


# ============================================================
# Knowledge chunker & embeddings
# ============================================================


def test_chunker_e2e():
    """16.2 — Document chunking."""
    from app.services.knowledge.chunker import chunk_text

    chunks = chunk_text("A" * 5000, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 600 for c in chunks)  # allow some overlap


def test_chunker_empty():
    """16.2 — Empty document."""
    from app.services.knowledge.chunker import chunk_text

    chunks = chunk_text("")
    assert chunks == []


def test_cosine_similarity_e2e():
    """16.3 — Cosine similarity."""
    from app.services.knowledge.embeddings import cosine_similarity

    # Identical
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    # Orthogonal
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    # Opposite
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)
