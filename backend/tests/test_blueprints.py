"""Tests for the Blueprint system — node executors, engine, and API endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest

# --- Node executor unit tests ---


@pytest.mark.asyncio
async def test_text_splitter():
    from app.services.blueprint_nodes.deterministic import execute_text_splitter

    result = await execute_text_splitter(
        {"chunk_size": 10, "overlap": 2},
        {"text": "Hello, this is a test of text splitting functionality."},
    )
    assert "chunks" in result
    assert result["chunk_count"] > 1
    assert all(isinstance(c, str) for c in result["chunks"])


@pytest.mark.asyncio
async def test_text_splitter_empty():
    from app.services.blueprint_nodes.deterministic import execute_text_splitter

    result = await execute_text_splitter({}, {"text": ""})
    assert result["chunks"] == []
    assert result["chunk_count"] == 0


@pytest.mark.asyncio
async def test_template_renderer():
    from app.services.blueprint_nodes.deterministic import execute_template_renderer

    result = await execute_template_renderer(
        {"template": "Hello {{name}}, you have {{count}} items."},
        {"name": "Alice", "count": "5"},
    )
    assert result["rendered"] == "Hello Alice, you have 5 items."


@pytest.mark.asyncio
async def test_json_validator_valid():
    from app.services.blueprint_nodes.deterministic import execute_json_validator

    data = json.dumps({"entities": ["Bob"], "dates": []})
    result = await execute_json_validator(
        {"data": data, "schema": {"required": ["entities"]}},
        {},
    )
    assert result["valid"] is True
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_json_validator_missing_field():
    from app.services.blueprint_nodes.deterministic import execute_json_validator

    data = json.dumps({"dates": []})
    result = await execute_json_validator(
        {"data": data, "schema": {"required": ["entities"]}},
        {},
    )
    assert result["valid"] is False
    assert len(result["errors"]) == 1


@pytest.mark.asyncio
async def test_json_validator_invalid_json():
    from app.services.blueprint_nodes.deterministic import execute_json_validator

    result = await execute_json_validator(
        {"data": "not json at all", "schema": {}},
        {},
    )
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_output_formatter_json():
    from app.services.blueprint_nodes.deterministic import execute_output_formatter

    result = await execute_output_formatter(
        {"format": "json"},
        {"text": '{"key": "value"}'},
    )
    assert "formatted" in result
    parsed = json.loads(result["formatted"])
    assert parsed["key"] == "value"


@pytest.mark.asyncio
async def test_output_formatter_plain():
    from app.services.blueprint_nodes.deterministic import execute_output_formatter

    result = await execute_output_formatter(
        {"format": "plain"},
        {"text": "**bold** and *italic*"},
    )
    assert "bold" in result["formatted"]
    assert "**" not in result["formatted"]


@pytest.mark.asyncio
async def test_output_formatter_markdown():
    from app.services.blueprint_nodes.deterministic import execute_output_formatter

    result = await execute_output_formatter(
        {"format": "markdown"},
        {"text": "# Hello"},
    )
    assert result["formatted"] == "# Hello"


# --- Registry tests ---


def test_registry_has_all_nodes():
    from app.services.blueprint_nodes.registry import NODE_REGISTRY

    # 10 det + 5 agent + 12 steer + 6 drive + 4 cu_agent + 6 agent_control + 1 recording = 44
    assert len(NODE_REGISTRY) == 44


def test_registry_list_by_category():
    from app.services.blueprint_nodes.registry import list_node_types

    agent_types = list_node_types(category="agent")
    assert len(agent_types) == 5
    assert all(t["node_class"] == "agent" for t in agent_types)


def test_registry_get_node_type():
    from app.services.blueprint_nodes.registry import get_node_type

    nt = get_node_type("fetch_url")
    assert nt is not None
    assert nt.category == "context"
    assert nt.node_class == "deterministic"


def test_registry_get_unknown_type():
    from app.services.blueprint_nodes.registry import get_node_type

    assert get_node_type("nonexistent") is None


# --- Execution engine tests ---


def test_topological_sort_linear():
    from app.services.blueprint_engine import _topological_sort

    nodes = [
        {"id": "a", "dependencies": []},
        {"id": "b", "dependencies": ["a"]},
        {"id": "c", "dependencies": ["b"]},
    ]
    layers = _topological_sort(nodes)
    assert len(layers) == 3
    assert layers[0] == [0]
    assert layers[1] == [1]
    assert layers[2] == [2]


def test_topological_sort_parallel():
    from app.services.blueprint_engine import _topological_sort

    nodes = [
        {"id": "a", "dependencies": []},
        {"id": "b", "dependencies": []},
        {"id": "c", "dependencies": ["a", "b"]},
    ]
    layers = _topological_sort(nodes)
    assert len(layers) == 2
    assert set(layers[0]) == {0, 1}
    assert layers[1] == [2]


def test_topological_sort_cycle():
    from app.services.blueprint_engine import _topological_sort

    nodes = [
        {"id": "a", "dependencies": ["b"]},
        {"id": "b", "dependencies": ["a"]},
    ]
    with pytest.raises(ValueError, match="cycle"):
        _topological_sort(nodes)


# --- Context assembly tests ---


def test_context_assembly_basic():
    from app.services.blueprint_nodes.context_assembly import assemble_context

    outputs = {
        "node_1": {"text": "Hello world"},
        "node_2": {"text": "Goodbye world"},
    }
    result = assemble_context(outputs, objective="Hello")
    assert "Hello world" in result
    assert "Goodbye world" in result


def test_context_assembly_respects_budget():
    from app.services.blueprint_nodes.context_assembly import assemble_context

    outputs = {
        "node_1": {"text": "A" * 10000},
        "node_2": {"text": "B" * 10000},
    }
    result = assemble_context(outputs, max_tokens=100)
    # Should be truncated to roughly 400 chars (100 tokens * 4 chars/token)
    assert len(result) < 2000


def test_context_assembly_relevance_scoring():
    from app.services.blueprint_nodes.context_assembly import assemble_context

    outputs = {
        "relevant": {"text": "Python programming language tutorial"},
        "irrelevant": {"text": "Recipe for chocolate cake"},
    }
    result = assemble_context(outputs, objective="Python programming")
    # Relevant content should appear first
    python_pos = result.find("Python")
    cake_pos = result.find("cake")
    assert python_pos < cake_pos


# --- API endpoint tests ---


def test_list_blueprints(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/blueprints", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json() == []


def test_list_blueprint_templates(client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = client.get("/api/blueprints/templates")
        assert response.status_code == 200


def test_get_node_types(client):
    response = client.get("/api/blueprints/node-types")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 44


def test_get_node_types_filtered(client):
    response = client.get("/api/blueprints/node-types?category=agent")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert all(d["node_class"] == "agent" for d in data)


def test_create_blueprint(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        bp_data = {
            "id": "bp-1",
            "user_id": "test-user-id-123",
            "name": "Test Blueprint",
            "description": "A test",
            "version": 1,
            "is_template": False,
            "nodes": [],
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
                "name": "Test Blueprint",
                "description": "A test",
                "nodes": [],
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test Blueprint"


def test_delete_blueprint(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "test-user-id-123"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        response = auth_client.delete(
            "/api/blueprints/bp-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 204


def test_delete_blueprint_not_owner(auth_client):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "other-user"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing

        response = auth_client.delete(
            "/api/blueprints/bp-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


def test_blueprints_require_auth(client):
    response = client.get("/api/blueprints")
    assert response.status_code == 422
