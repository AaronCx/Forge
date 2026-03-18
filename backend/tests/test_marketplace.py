"""Tests for Marketplace + Teams (v1.7.0)."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --- Org service unit tests ---


@pytest.mark.asyncio
async def test_slug_generation():
    """Verify slug is generated from org name."""
    name = "My Cool Team!"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    assert slug == "my-cool-team"


@pytest.mark.asyncio
async def test_slug_generation_special_chars():
    name = "  Test & Demo (v2)  "
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    assert slug == "test-demo-v2"


@pytest.mark.asyncio
async def test_org_create():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        org_data = {"id": "org-1", "name": "Team A", "slug": "team-a", "owner_id": "u1"}
        mock_result = MagicMock()
        mock_result.data = [org_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        result = await svc.create_org(owner_id="u1", name="Team A")
        assert result["name"] == "Team A"
        assert result["owner_id"] == "u1"


@pytest.mark.asyncio
async def test_org_list_empty():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result

        result = await svc.list_orgs("u1")
        assert result == []


@pytest.mark.asyncio
async def test_org_get():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        org_data = {"id": "org-1", "name": "Team A", "slug": "team-a", "owner_id": "u1"}
        mock_result = MagicMock()
        mock_result.data = org_data
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        result = await svc.get_org("org-1")
        assert result is not None
        assert result["name"] == "Team A"


@pytest.mark.asyncio
async def test_org_delete_not_owner():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = {"id": "org-1", "owner_id": "other-user"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        result = await svc.delete_org("org-1", "u1")
        assert result is False


@pytest.mark.asyncio
async def test_get_user_role():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = {"role": "admin"}
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        role = await svc.get_user_role("org-1", "u1")
        assert role == "admin"


@pytest.mark.asyncio
async def test_get_user_role_not_member():
    from app.services.marketplace.org_service import OrgService

    svc = OrgService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = None
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        role = await svc.get_user_role("org-1", "u1")
        assert role is None


# --- Marketplace service unit tests ---


@pytest.mark.asyncio
async def test_marketplace_publish():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        listing_data = {
            "id": "listing-1",
            "blueprint_id": "bp-1",
            "user_id": "u1",
            "title": "My Workflow",
            "status": "published",
        }
        mock_result = MagicMock()
        mock_result.data = [listing_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_result

        result = await svc.publish_listing(
            user_id="u1",
            blueprint_id="bp-1",
            title="My Workflow",
        )
        assert result["title"] == "My Workflow"
        assert result["status"] == "published"


@pytest.mark.asyncio
async def test_marketplace_list_empty():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        result = await svc.list_listings()
        assert result == []


@pytest.mark.asyncio
async def test_marketplace_get_listing():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        listing_data = {"id": "listing-1", "title": "Test", "user_id": "u1"}
        mock_result = MagicMock()
        mock_result.data = listing_data
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        result = await svc.get_listing("listing-1")
        assert result is not None
        assert result["title"] == "Test"


@pytest.mark.asyncio
async def test_marketplace_delete_not_owner():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = {"id": "listing-1", "user_id": "other-user"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_result

        result = await svc.delete_listing("listing-1", "u1")
        assert result is False


@pytest.mark.asyncio
async def test_marketplace_rate():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        rating_data = {"id": "r-1", "listing_id": "listing-1", "user_id": "u1", "rating": 4}
        mock_upsert = MagicMock()
        mock_upsert.data = [rating_data]
        mock_db.table.return_value.upsert.return_value.execute.return_value = mock_upsert

        # Mock rating stats update
        mock_ratings = MagicMock()
        mock_ratings.data = [{"rating": 4}, {"rating": 5}]
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ratings
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await svc.rate_listing(listing_id="listing-1", user_id="u1", rating=4)
        assert result["rating"] == 4


@pytest.mark.asyncio
async def test_marketplace_fork():
    from app.services.marketplace.marketplace_service import MarketplaceService

    svc = MarketplaceService()
    with patch("app.db._db") as mock_db:
        # Mock get_listing
        listing_data = {"id": "listing-1", "blueprint_id": "bp-1", "user_id": "u1", "fork_count": 0}
        mock_listing = MagicMock()
        mock_listing.data = listing_data
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_listing

        # Mock fork insert
        fork_data = {"id": "f-1", "listing_id": "listing-1", "user_id": "u2"}
        mock_fork = MagicMock()
        mock_fork.data = [fork_data]
        mock_db.table.return_value.insert.return_value.execute.return_value = mock_fork

        # Mock fork count update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await svc.fork_listing(
            listing_id="listing-1", user_id="u2", forked_blueprint_id="bp-2"
        )
        assert result["listing_id"] == "listing-1"


# --- API endpoint tests ---


def test_list_marketplace_listings(client):
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.list_listings = AsyncMock(return_value=[])
        response = client.get("/api/marketplace/listings")
        assert response.status_code == 200
        assert response.json() == []


def test_get_marketplace_listing_not_found(client):
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.get_listing = AsyncMock(return_value=None)
        response = client.get("/api/marketplace/listings/nonexistent")
        assert response.status_code == 404


def test_publish_listing(auth_client):
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.publish_listing = AsyncMock(return_value={
            "id": "listing-1",
            "title": "Test",
            "status": "published",
        })
        response = auth_client.post(
            "/api/marketplace/listings",
            json={
                "blueprint_id": "bp-1",
                "title": "Test",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Test"


def test_rate_listing_invalid(auth_client):
    with patch("app.routers.marketplace.marketplace_service") as mock_svc:
        mock_svc.rate_listing = AsyncMock()
        response = auth_client.post(
            "/api/marketplace/listings/listing-1/rate",
            json={"rating": 6},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 400


def test_list_orgs(auth_client):
    with patch("app.routers.organizations.org_service") as mock_svc:
        mock_svc.list_orgs = AsyncMock(return_value=[])
        response = auth_client.get(
            "/api/organizations",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert response.json() == []


def test_create_org(auth_client):
    with patch("app.routers.organizations.org_service") as mock_svc:
        mock_svc.create_org = AsyncMock(return_value={
            "id": "org-1",
            "name": "Team A",
            "slug": "team-a",
        })
        response = auth_client.post(
            "/api/organizations",
            json={"name": "Team A"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Team A"


def test_get_org_not_found(auth_client):
    with patch("app.routers.organizations.org_service") as mock_svc:
        mock_svc.get_org = AsyncMock(return_value=None)
        response = auth_client.get(
            "/api/organizations/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 404


def test_add_member_forbidden(auth_client):
    with patch("app.routers.organizations.org_service") as mock_svc:
        mock_svc.get_user_role = AsyncMock(return_value="member")
        response = auth_client.post(
            "/api/organizations/org-1/members",
            json={"user_id": "u2", "role": "member"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 403
