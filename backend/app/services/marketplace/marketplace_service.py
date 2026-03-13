"""Marketplace service — publish, fork, rate, and search workflow listings."""

from __future__ import annotations

import logging
from typing import Any

from app.database import supabase

logger = logging.getLogger(__name__)


class MarketplaceService:
    """Manages marketplace listings, ratings, and forks."""

    # === Listing CRUD ===

    async def publish_listing(
        self,
        *,
        user_id: str,
        blueprint_id: str,
        title: str,
        description: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        version: str = "1.0.0",
        org_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish a blueprint to the marketplace."""
        row = {
            "user_id": user_id,
            "blueprint_id": blueprint_id,
            "title": title,
            "description": description,
            "category": category,
            "tags": tags or [],
            "version": version,
            "status": "published",
            "published_at": "now()",
        }
        if org_id:
            row["org_id"] = org_id

        result = supabase.table("marketplace_listings").insert(row).execute()
        data = result.data
        listing: dict[str, Any] = data[0] if isinstance(data, list) else data
        return listing

    # Allowed sort columns to prevent order-by injection
    _ALLOWED_SORT_COLUMNS = frozenset({
        "rating_avg", "install_count", "fork_count", "created_at", "title",
    })

    async def list_listings(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        sort_by: str = "rating_avg",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List published marketplace listings."""
        query = (
            supabase.table("marketplace_listings")
            .select("*")
            .eq("status", "published")
        )
        if category:
            query = query.eq("category", category)
        if search:
            # Escape ILIKE special characters to prevent pattern injection
            import re
            escaped_search = re.sub(r"([%_\\])", r"\\\1", search)
            query = query.ilike("title", f"%{escaped_search}%")

        # Validate sort column against allowlist
        if sort_by not in self._ALLOWED_SORT_COLUMNS:
            sort_by = "rating_avg"

        desc = sort_by in ("rating_avg", "install_count", "fork_count")
        limit = min(max(limit, 1), 100)  # Clamp limit
        query = query.order(sort_by, desc=desc).limit(limit)

        result = query.execute()
        return result.data or []

    async def get_listing(self, listing_id: str) -> dict[str, Any] | None:
        """Get a single marketplace listing."""
        result = (
            supabase.table("marketplace_listings")
            .select("*")
            .eq("id", listing_id)
            .single()
            .execute()
        )
        listing: dict[str, Any] | None = result.data
        return listing

    async def get_user_listings(self, user_id: str) -> list[dict[str, Any]]:
        """Get all listings by a user."""
        result = (
            supabase.table("marketplace_listings")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def update_listing(
        self, listing_id: str, user_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a listing (owner only)."""
        listing = await self.get_listing(listing_id)
        if not listing or listing["user_id"] != user_id:
            return None
        allowed = {
            k: v for k, v in updates.items()
            if k in ("title", "description", "category", "tags", "version", "status", "metadata")
        }
        if not allowed:
            return listing
        result = (
            supabase.table("marketplace_listings")
            .update(allowed)
            .eq("id", listing_id)
            .execute()
        )
        data = result.data
        row: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row

    async def delete_listing(self, listing_id: str, user_id: str) -> bool:
        """Delete a listing (owner only)."""
        listing = await self.get_listing(listing_id)
        if not listing or listing["user_id"] != user_id:
            return False
        supabase.table("marketplace_listings").delete().eq("id", listing_id).execute()
        return True

    # === Ratings ===

    async def rate_listing(
        self,
        *,
        listing_id: str,
        user_id: str,
        rating: int,
        review: str = "",
    ) -> dict[str, Any]:
        """Rate a marketplace listing (upsert)."""
        result = supabase.table("marketplace_ratings").upsert({
            "listing_id": listing_id,
            "user_id": user_id,
            "rating": rating,
            "review": review,
        }, on_conflict="listing_id,user_id").execute()
        data = result.data
        rating_row: dict[str, Any] = data[0] if isinstance(data, list) else data

        # Update listing aggregate
        await self._update_rating_stats(listing_id)
        return rating_row

    async def _update_rating_stats(self, listing_id: str) -> None:
        """Recalculate rating stats for a listing."""
        ratings = (
            supabase.table("marketplace_ratings")
            .select("rating")
            .eq("listing_id", listing_id)
            .execute()
        ).data or []

        if ratings:
            values = [r["rating"] for r in ratings]
            avg = sum(values) / len(values)
            supabase.table("marketplace_listings").update({
                "rating_avg": round(avg, 2),
                "rating_count": len(values),
            }).eq("id", listing_id).execute()

    async def get_ratings(self, listing_id: str) -> list[dict[str, Any]]:
        """Get all ratings for a listing."""
        result = (
            supabase.table("marketplace_ratings")
            .select("*")
            .eq("listing_id", listing_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    # === Forks ===

    async def fork_listing(
        self,
        *,
        listing_id: str,
        user_id: str,
        forked_blueprint_id: str,
    ) -> dict[str, Any]:
        """Record a fork of a marketplace listing."""
        listing = await self.get_listing(listing_id)
        if not listing:
            msg = "Listing not found"
            raise ValueError(msg)

        result = supabase.table("marketplace_forks").insert({
            "listing_id": listing_id,
            "source_blueprint_id": listing["blueprint_id"],
            "forked_blueprint_id": forked_blueprint_id,
            "user_id": user_id,
        }).execute()
        data = result.data
        fork: dict[str, Any] = data[0] if isinstance(data, list) else data

        # Increment fork count
        supabase.table("marketplace_listings").update({
            "fork_count": (listing.get("fork_count", 0) or 0) + 1,
        }).eq("id", listing_id).execute()

        return fork

    async def get_forks(self, listing_id: str) -> list[dict[str, Any]]:
        """Get all forks of a listing."""
        result = (
            supabase.table("marketplace_forks")
            .select("*")
            .eq("listing_id", listing_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []


# Global singleton
marketplace_service = MarketplaceService()
