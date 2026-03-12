"""Tests for knowledge base: chunking, embeddings, service, API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.knowledge.chunker import chunk_text
from app.services.knowledge.embeddings import cosine_similarity
from app.services.knowledge.knowledge_service import KnowledgeService

# === Chunker tests ===


def test_chunk_text_basic():
    text = "Hello world. " * 100  # ~1300 chars
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)  # allow slight overshoot


def test_chunk_text_short():
    text = "Short text."
    chunks = chunk_text(text, chunk_size=1000, chunk_overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == "Short text."


def test_chunk_text_empty():
    chunks = chunk_text("", chunk_size=1000, chunk_overlap=100)
    assert chunks == []


# === Embeddings tests ===


def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    assert cosine_similarity(a, b) == 0.0


# === Knowledge Service tests ===


@pytest.mark.asyncio
async def test_create_collection():
    service = KnowledgeService()
    mock_result = MagicMock()
    mock_result.data = [{
        "id": "c1", "user_id": "u1", "name": "Test KB",
        "document_count": 0, "chunk_count": 0,
    }]

    with patch("app.services.knowledge.knowledge_service.supabase") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_result
        result = await service.create_collection(
            user_id="u1", name="Test KB",
        )

    assert result["name"] == "Test KB"


@pytest.mark.asyncio
async def test_list_collections():
    service = KnowledgeService()
    mock_result = MagicMock()
    mock_result.data = [
        {"id": "c1", "name": "KB 1"},
        {"id": "c2", "name": "KB 2"},
    ]

    with patch("app.services.knowledge.knowledge_service.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result
        result = await service.list_collections("u1")

    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_collection():
    service = KnowledgeService()
    mock_result = MagicMock()
    mock_result.data = {"id": "c1", "name": "Test KB", "user_id": "u1"}

    with patch("app.services.knowledge.knowledge_service.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_result
        result = await service.get_collection("c1", "u1")

    assert result is not None
    assert result["name"] == "Test KB"


@pytest.mark.asyncio
async def test_delete_collection():
    service = KnowledgeService()
    mock_result = MagicMock()
    mock_result.data = []

    with patch("app.services.knowledge.knowledge_service.supabase") as mock_sb:
        mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result
        result = await service.delete_collection("c1", "u1")

    assert result is True


@pytest.mark.asyncio
async def test_search():
    service = KnowledgeService()

    # Mock get_collection
    mock_collection = MagicMock()
    mock_collection.data = {
        "id": "c1", "user_id": "u1", "embedding_model": "text-embedding-3-small",
    }

    # Mock chunks
    mock_chunks = MagicMock()
    mock_chunks.data = [
        {"id": "ch1", "content": "Python is great", "embedding": [1.0, 0.0, 0.0],
         "chunk_index": 0, "document_id": "d1", "metadata": {}},
        {"id": "ch2", "content": "Java is fine", "embedding": [0.0, 1.0, 0.0],
         "chunk_index": 1, "document_id": "d1", "metadata": {}},
    ]

    with (
        patch("app.services.knowledge.knowledge_service.supabase") as mock_sb,
        patch("app.services.knowledge.knowledge_service.generate_embeddings") as mock_embed,
    ):
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_collection
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_chunks
        mock_embed.return_value = [[0.9, 0.1, 0.0]]  # query embedding close to ch1

        results = await service.search(
            user_id="u1", collection_id="c1", query="Python", top_k=2,
        )

    assert len(results) == 2
    assert results[0]["chunk_id"] == "ch1"  # highest similarity
    assert results[0]["similarity"] > results[1]["similarity"]


# === API Route tests ===


def test_collections_list_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.knowledge.knowledge_service") as mock_svc:
            mock_svc.list_collections = AsyncMock(return_value=[
                {"id": "c1", "name": "Test KB", "document_count": 3, "chunk_count": 15},
            ])

            test_client = TestClient(app)
            resp = test_client.get("/api/knowledge/collections")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test KB"
    finally:
        app.dependency_overrides.clear()


def test_create_collection_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.knowledge.knowledge_service") as mock_svc:
            mock_svc.create_collection = AsyncMock(return_value={
                "id": "c1", "name": "My KB", "document_count": 0, "chunk_count": 0,
            })

            test_client = TestClient(app)
            resp = test_client.post("/api/knowledge/collections", json={
                "name": "My KB", "description": "Test collection",
            })

        assert resp.status_code == 200
        assert resp.json()["name"] == "My KB"
    finally:
        app.dependency_overrides.clear()


def test_search_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.knowledge.knowledge_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=[
                {"chunk_id": "ch1", "content": "Relevant text", "similarity": 0.95,
                 "document_id": "d1", "chunk_index": 0, "metadata": {}},
            ])

            test_client = TestClient(app)
            resp = test_client.post("/api/knowledge/collections/c1/search", json={
                "query": "test query",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["similarity"] == 0.95
    finally:
        app.dependency_overrides.clear()


def test_collection_not_found():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.knowledge.knowledge_service") as mock_svc:
            mock_svc.get_collection = AsyncMock(return_value=None)

            test_client = TestClient(app)
            resp = test_client.get("/api/knowledge/collections/nonexistent")

        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
