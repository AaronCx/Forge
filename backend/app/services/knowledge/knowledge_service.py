"""Knowledge base service — manages collections, documents, chunks, and search."""

from __future__ import annotations

import logging
from typing import Any

from app.database import supabase
from app.services.knowledge.chunker import chunk_text
from app.services.knowledge.embeddings import (
    cosine_similarity,
    generate_embeddings,
)

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Manages knowledge collections, document ingestion, and semantic search."""

    # === Collection CRUD ===

    async def create_collection(
        self,
        *,
        user_id: str,
        name: str,
        description: str = "",
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> dict[str, Any]:
        """Create a new knowledge collection."""
        result = supabase.table("knowledge_collections").insert({
            "user_id": user_id,
            "name": name,
            "description": description,
            "embedding_model": embedding_model,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }).execute()
        data = result.data
        row: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row

    async def list_collections(self, user_id: str) -> list[dict[str, Any]]:
        """List all collections for a user."""
        result = (
            supabase.table("knowledge_collections")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_collection(self, collection_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a single collection."""
        result = (
            supabase.table("knowledge_collections")
            .select("*")
            .eq("id", collection_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        col: dict[str, Any] | None = result.data
        return col

    async def delete_collection(self, collection_id: str, user_id: str) -> bool:
        """Delete a collection and all its documents/chunks."""
        supabase.table("knowledge_collections").delete().eq(
            "id", collection_id
        ).eq("user_id", user_id).execute()
        return True

    # === Document management ===

    def _get_user_openai_key(self, user_id: str) -> str | None:
        """Fetch user's OpenAI API key from provider_configs."""
        try:
            result = (
                supabase.table("provider_configs")
                .select("api_key_encrypted")
                .eq("user_id", user_id)
                .eq("provider", "openai")
                .eq("is_enabled", True)
                .single()
                .execute()
            )
            if result.data and result.data.get("api_key_encrypted"):
                return result.data["api_key_encrypted"]
        except Exception:
            pass
        return None

    async def add_document(
        self,
        *,
        user_id: str,
        collection_id: str,
        filename: str,
        raw_text: str,
        content_type: str = "text/plain",
    ) -> dict[str, Any]:
        """Add a document to a collection and process it (chunk + embed)."""
        # Create document record
        doc_result = supabase.table("knowledge_documents").insert({
            "user_id": user_id,
            "collection_id": collection_id,
            "filename": filename,
            "content_type": content_type,
            "file_size": len(raw_text.encode()),
            "raw_text": raw_text,
            "status": "processing",
        }).execute()
        doc_data = doc_result.data
        doc: dict[str, Any] = doc_data[0] if isinstance(doc_data, list) else doc_data
        doc_id = doc["id"]

        try:
            # Get collection config
            collection = await self.get_collection(collection_id, user_id)
            if not collection:
                raise ValueError("Collection not found")

            c_size = collection.get("chunk_size", 1000)
            c_overlap = collection.get("chunk_overlap", 200)
            embed_model = collection.get("embedding_model", "text-embedding-3-small")

            # Chunk the document
            chunks = chunk_text(raw_text, chunk_size=c_size, chunk_overlap=c_overlap)

            if not chunks:
                chunks = [raw_text[:c_size]] if raw_text else [""]

            # Generate embeddings in batches
            user_key = self._get_user_openai_key(user_id)
            batch_size = 100
            all_embeddings: list[list[float]] = []
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                embeddings = await generate_embeddings(batch, model=embed_model, api_key=user_key)
                all_embeddings.extend(embeddings)

            # Store chunks
            chunk_rows = []
            for idx, (chunk_content, embedding) in enumerate(zip(chunks, all_embeddings, strict=True)):
                chunk_rows.append({
                    "user_id": user_id,
                    "document_id": doc_id,
                    "collection_id": collection_id,
                    "chunk_index": idx,
                    "content": chunk_content,
                    "embedding": embedding,
                    "token_count": len(chunk_content) // 4,  # rough estimate
                })

            if chunk_rows:
                supabase.table("knowledge_chunks").insert(chunk_rows).execute()

            # Update document status
            supabase.table("knowledge_documents").update({
                "status": "ready",
                "chunk_count": len(chunks),
            }).eq("id", doc_id).execute()

            # Update collection counts
            try:
                self._update_collection_counts(collection_id)
            except Exception:
                logger.warning("Failed to update collection counts", exc_info=True)

            # Re-fetch document
            doc_refresh = (
                supabase.table("knowledge_documents")
                .select("*")
                .eq("id", doc_id)
                .single()
                .execute()
            )
            final: dict[str, Any] = doc_refresh.data or doc
            return final

        except Exception as e:
            logger.error("Failed to process document %s: %s", doc_id, e)
            supabase.table("knowledge_documents").update({
                "status": "error",
                "error_message": str(e),
            }).eq("id", doc_id).execute()
            doc["status"] = "error"
            doc["error_message"] = str(e)
            return doc

    def _update_collection_counts(self, collection_id: str) -> None:
        """Update document and chunk counts on a collection."""
        docs = supabase.table("knowledge_documents").select(
            "id", count="exact"  # type: ignore[arg-type]
        ).eq("collection_id", collection_id).eq("status", "ready").execute()
        chunks = supabase.table("knowledge_chunks").select(
            "id", count="exact"  # type: ignore[arg-type]
        ).eq("collection_id", collection_id).execute()

        doc_count = docs.count if hasattr(docs, "count") and docs.count else 0
        chunk_count = chunks.count if hasattr(chunks, "count") and chunks.count else 0

        supabase.table("knowledge_collections").update({
            "document_count": doc_count,
            "chunk_count": chunk_count,
        }).eq("id", collection_id).execute()

    async def list_documents(
        self, collection_id: str, user_id: str
    ) -> list[dict[str, Any]]:
        """List documents in a collection."""
        result = (
            supabase.table("knowledge_documents")
            .select("id,collection_id,filename,content_type,file_size,chunk_count,status,created_at")
            .eq("collection_id", collection_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Delete a document and its chunks."""
        doc = (
            supabase.table("knowledge_documents")
            .select("collection_id")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        ).data
        if not doc:
            return False

        supabase.table("knowledge_documents").delete().eq(
            "id", document_id
        ).eq("user_id", user_id).execute()

        import contextlib

        with contextlib.suppress(Exception):
            self._update_collection_counts(doc["collection_id"])

        return True

    # === Semantic Search ===

    async def search(
        self,
        *,
        user_id: str,
        collection_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for relevant chunks using embedding similarity."""
        collection = await self.get_collection(collection_id, user_id)
        if not collection:
            return []

        embed_model = collection.get("embedding_model", "text-embedding-3-small")

        # Generate query embedding
        user_key = self._get_user_openai_key(user_id)
        query_embeddings = await generate_embeddings([query], model=embed_model, api_key=user_key)
        query_embedding = query_embeddings[0]

        # Fetch all chunks for this collection (for small collections)
        # For production, use pgvector extension
        chunks = (
            supabase.table("knowledge_chunks")
            .select("id,content,embedding,chunk_index,document_id,metadata")
            .eq("collection_id", collection_id)
            .eq("user_id", user_id)
            .execute()
        ).data or []

        # Compute similarities
        scored = []
        for chunk in chunks:
            embedding = chunk.get("embedding")
            if not embedding:
                continue
            sim = cosine_similarity(query_embedding, embedding)
            scored.append({
                "chunk_id": chunk["id"],
                "document_id": chunk["document_id"],
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "similarity": round(sim, 4),
                "metadata": chunk.get("metadata", {}),
            })

        # Sort by similarity descending
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def search_multi(
        self,
        *,
        user_id: str,
        collection_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search across multiple collections."""
        all_results: list[dict[str, Any]] = []
        for cid in collection_ids:
            results = await self.search(
                user_id=user_id, collection_id=cid, query=query, top_k=top_k,
            )
            for r in results:
                r["collection_id"] = cid
            all_results.extend(results)

        all_results.sort(key=lambda x: x["similarity"], reverse=True)
        return all_results[:top_k]


# Global singleton
knowledge_service = KnowledgeService()
