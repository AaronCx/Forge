"""API routes for knowledge base and RAG."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.services.knowledge.knowledge_service import knowledge_service

router = APIRouter(tags=["knowledge"])


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 1000
    chunk_overlap: int = 200


class AddDocumentRequest(BaseModel):
    filename: str
    raw_text: str
    content_type: str = "text/plain"


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class MultiSearchRequest(BaseModel):
    collection_ids: list[str]
    query: str
    top_k: int = 5


# === Collections ===


@router.post("/knowledge/collections")
async def create_collection(
    body: CreateCollectionRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Create a new knowledge collection."""
    return await knowledge_service.create_collection(
        user_id=user.id,
        name=body.name,
        description=body.description,
        embedding_model=body.embedding_model,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )


@router.get("/knowledge/collections")
async def list_collections(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List all knowledge collections."""
    return await knowledge_service.list_collections(user.id)


@router.get("/knowledge/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get a knowledge collection."""
    col = await knowledge_service.get_collection(collection_id, user.id)
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col


@router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Delete a knowledge collection."""
    await knowledge_service.delete_collection(collection_id, user.id)
    return {"status": "deleted"}


# === Documents ===


@router.post("/knowledge/collections/{collection_id}/documents")
async def add_document(
    collection_id: str,
    body: AddDocumentRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Add a document to a collection (chunking + embedding happens automatically)."""
    return await knowledge_service.add_document(
        user_id=user.id,
        collection_id=collection_id,
        filename=body.filename,
        raw_text=body.raw_text,
        content_type=body.content_type,
    )


@router.get("/knowledge/collections/{collection_id}/documents")
async def list_documents(
    collection_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List documents in a collection."""
    return await knowledge_service.list_documents(collection_id, user.id)


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Delete a document and its chunks."""
    deleted = await knowledge_service.delete_document(document_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


# === Search ===


@router.post("/knowledge/collections/{collection_id}/search")
async def search_collection(
    collection_id: str,
    body: SearchRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """Semantic search within a collection."""
    return await knowledge_service.search(
        user_id=user.id,
        collection_id=collection_id,
        query=body.query,
        top_k=body.top_k,
    )


@router.post("/knowledge/search")
async def search_multi(
    body: MultiSearchRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """Search across multiple collections."""
    return await knowledge_service.search_multi(
        user_id=user.id,
        collection_ids=body.collection_ids,
        query=body.query,
        top_k=body.top_k,
    )
