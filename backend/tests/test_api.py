from unittest.mock import MagicMock, patch

# --- Health & Root ---


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Forge API"
    assert data["status"] == "running"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_has_version(client):
    response = client.get("/")
    data = response.json()
    assert "version" in data


# --- Auth Guards (no Authorization header → 422) ---


def test_agents_requires_auth(client):
    response = client.get("/api/agents")
    assert response.status_code == 422


def test_runs_requires_auth(client):
    response = client.get("/api/runs")
    assert response.status_code == 422


def test_keys_requires_auth(client):
    response = client.get("/api/keys")
    assert response.status_code == 422


def test_stats_requires_auth(client):
    response = client.get("/api/stats")
    assert response.status_code == 422


def test_invalid_bearer_token(client):
    with patch("app.db._db") as mock_sb:
        mock_sb.auth.get_user.side_effect = Exception("Invalid token")
        response = client.get(
            "/api/agents", headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401


def test_missing_bearer_prefix(client):
    response = client.get(
        "/api/agents", headers={"Authorization": "not-a-bearer-token"}
    )
    assert response.status_code == 401


# --- Agents CRUD (auth_client has mocked auth) ---


def test_list_agents(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/agents", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json() == []


def test_list_templates(client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result

        response = client.get("/api/agents/templates")
        assert response.status_code == 200


def test_create_agent(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        agent_data = {
            "id": "agent-1",
            "user_id": "test-user-id-123",
            "name": "Test Agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent.",
            "tools": ["web_search"],
            "workflow_steps": ["Step 1"],
            "is_template": False,
            "created_at": "2026-03-10T00:00:00Z",
            "updated_at": "2026-03-10T00:00:00Z",
        }
        mock_result = MagicMock()
        mock_result.data = [agent_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        response = auth_client.post(
            "/api/agents",
            json={
                "name": "Test Agent",
                "description": "A test agent",
                "system_prompt": "You are a test agent.",
                "tools": ["web_search"],
                "workflow_steps": ["Step 1"],
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test Agent"


def test_get_agent(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        agent_data = {
            "id": "agent-1",
            "user_id": "test-user-id-123",
            "name": "Test Agent",
            "description": "",
            "system_prompt": "test",
            "tools": [],
            "workflow_steps": [],
            "is_template": False,
            "created_at": "2026-03-10T00:00:00Z",
            "updated_at": "2026-03-10T00:00:00Z",
        }
        mock_result = MagicMock()
        mock_result.data = agent_data
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/agents/agent-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == "agent-1"


def test_get_agent_not_found(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/agents/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


def test_delete_agent(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "test-user-id-123"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        response = auth_client.delete(
            "/api/agents/agent-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 204


def test_delete_agent_not_owner(auth_client):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "other-user-id"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing

        response = auth_client.delete(
            "/api/agents/agent-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


# --- Runs ---


def test_list_runs(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/runs", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json() == []


def test_get_run_not_found(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/runs/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


# --- API Keys ---


def test_list_keys(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/keys", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200


def test_create_key(auth_client):
    with patch("app.db._db") as mock_db:
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

        response = auth_client.post(
            "/api/keys",
            json={"name": "Test Key"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["key"].startswith("af_")


def test_delete_key(auth_client, mock_user):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "test-user-id-123"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        response = auth_client.delete(
            "/api/keys/key-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 204


def test_delete_key_not_owner(auth_client):
    with patch("app.db._db") as mock_db:
        mock_existing = MagicMock()
        mock_existing.data = {"user_id": "other-user-id"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_existing

        response = auth_client.delete(
            "/api/keys/key-1",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


# --- Stats ---


def test_stats(auth_client):
    with patch("app.db._db") as mock_db:
        mock_agents = MagicMock()
        mock_agents.count = 5
        mock_agents.data = []
        mock_runs = MagicMock()
        mock_runs.count = 10
        mock_runs.data = [{"tokens_used": 100}, {"tokens_used": 200}]
        mock_recent = MagicMock()
        mock_recent.count = 2
        mock_recent.data = []

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "agents":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_agents
            elif name == "runs":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_runs
                mock_table.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_recent
                mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_runs
            return mock_table

        mock_db.table.side_effect = table_side_effect

        response = auth_client.get(
            "/api/stats", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_agents" in data
        assert "total_runs" in data
        assert "total_tokens" in data
        assert "runs_this_hour" in data
