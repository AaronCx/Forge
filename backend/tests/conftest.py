"""Shared test fixtures. Initializes mock database backend for tests."""

import os
from unittest.mock import MagicMock, patch

import pytest

# Set required env vars before any app imports
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing")
os.environ.setdefault("SERPAPI_KEY", "test-serpapi-key")

# Patch create_client to avoid real Supabase connection, then import app
_mock_supabase_client = MagicMock()
with patch("supabase.create_client", return_value=_mock_supabase_client):
    from app.db import init_db  # noqa: E402
    from app.db.interface import DatabaseBackend  # noqa: E402
    from app.main import app  # noqa: E402
    from app.routers.auth import get_current_user  # noqa: E402

    # Initialize a mock database backend so get_db() never raises
    _mock_db = MagicMock(spec=DatabaseBackend)
    _mock_db.auth = MagicMock()
    init_db(_mock_db)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_user():
    user = MagicMock(id="test-user-id-123")
    return user


@pytest.fixture
def auth_client(client, mock_user):
    """Client with FastAPI dependency override for auth."""

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()
