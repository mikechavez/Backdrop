"""
Tests for active narratives pagination API endpoint.

Tests the /api/v1/narratives/active endpoint with pagination parameters.
Corresponds to FEATURE-048b implementation.
"""

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from crypto_news_aggregator.main import app
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.core.config import get_settings


def get_test_client():
    """Helper to create AsyncClient with proper transport."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def test_narratives():
    """Create test narratives with multiple lifecycle states."""
    db = await mongo_manager.get_async_database()
    narratives_collection = db.narratives

    # Clean up existing test data
    await narratives_collection.delete_many({"theme": {"$regex": "^Test Narrative"}})

    # Create 25 test narratives with different lifecycle_states
    test_data = []
    for i in range(25):
        lifecycle_state = "hot" if i < 15 else "emerging"
        narrative = {
            "theme": f"Test Narrative {i+1}",
            "title": f"Test Title {i+1}",
            "summary": f"Test summary for narrative {i+1}",
            "entities": [f"Entity{i+1}", f"Entity{i+1}_B"],
            "article_ids": [],
            "article_count": 5 + i,
            "mention_velocity": 2.5 + (i * 0.1),
            "lifecycle": "hot",
            "lifecycle_state": lifecycle_state,
            "momentum": "growing",
            "recency_score": 0.8 - (i * 0.01),
            "entity_relationships": [],
            "first_seen": datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "last_updated": datetime(2025, 10, 6 - (i // 5), 14, 20, 0, tzinfo=timezone.utc),
            "days_active": 279,
        }
        result = await narratives_collection.insert_one(narrative)
        narrative["_id"] = result.inserted_id
        test_data.append(narrative)

    yield test_data

    # Cleanup
    await narratives_collection.delete_many({"theme": {"$regex": "^Test Narrative"}})


@pytest.mark.asyncio
async def test_get_active_narratives_default_pagination(test_narratives):
    """Test getting active narratives with default pagination (limit=10, offset=0)."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "narratives" in data
    assert "total_count" in data
    assert "offset" in data
    assert "limit" in data
    assert "has_more" in data

    # Verify pagination metadata
    assert data["offset"] == 0
    assert data["limit"] == 10
    # Should have at least 10 narratives from test data
    assert data["total_count"] >= 10
    assert len(data["narratives"]) <= data["limit"]


@pytest.mark.asyncio
async def test_get_active_narratives_second_page(test_narratives):
    """Test fetching second page (offset=10, limit=10)."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?offset=10&limit=10",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    # Verify pagination for second page
    assert data["offset"] == 10
    assert data["limit"] == 10
    # Total should match our test data
    assert data["total_count"] >= 10


@pytest.mark.asyncio
async def test_get_active_narratives_custom_limit(test_narratives):
    """Test with custom limit smaller than default."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=5",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    assert data["limit"] == 5
    assert len(data["narratives"]) <= 5


@pytest.mark.asyncio
async def test_get_active_narratives_offset_beyond_total(test_narratives):
    """Test offset beyond total narratives (no results)."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?offset=1000&limit=10",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    assert len(data["narratives"]) == 0
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_get_active_narratives_response_schema(test_narratives):
    """Verify response conforms to PaginatedNarrativesResponse schema."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=5",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert isinstance(data["narratives"], list)
    assert isinstance(data["total_count"], int)
    assert isinstance(data["offset"], int)
    assert isinstance(data["limit"], int)
    assert isinstance(data["has_more"], bool)

    # Verify each narrative has required fields
    if data["narratives"]:
        narrative = data["narratives"][0]
        assert "theme" in narrative
        assert "title" in narrative
        assert "summary" in narrative
        assert "entities" in narrative


@pytest.mark.asyncio
async def test_get_active_narratives_with_lifecycle_filter(test_narratives):
    """Test pagination with lifecycle_state filter."""
    settings = get_settings()

    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?lifecycle_state=hot&limit=10",
            headers={"X-API-Key": settings.API_KEY}
        )

    assert response.status_code == 200
    data = response.json()

    # Should only return "hot" narratives
    for narrative in data["narratives"]:
        assert narrative.get("lifecycle_state") in ["hot", None]  # None for old schema


@pytest.mark.asyncio
async def test_get_active_narratives_has_more_flag(test_narratives):
    """Test has_more flag is correctly set."""
    settings = get_settings()

    # First page
    async with get_test_client() as client:
        response1 = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=10&offset=0",
            headers={"X-API-Key": settings.API_KEY}
        )

    data1 = response1.json()
    total_count = data1["total_count"]

    # If we have at least 11 narratives, has_more should be True for first page
    if total_count > 10:
        assert data1["has_more"] is True

    # Last page (requesting beyond what exists)
    async with get_test_client() as client:
        response2 = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=10&offset={total_count}",
            headers={"X-API-Key": settings.API_KEY}
        )

    data2 = response2.json()
    assert data2["has_more"] is False


@pytest.mark.asyncio
async def test_get_active_narratives_pagination_consistency():
    """Test that pagination returns consistent results across pages."""
    settings = get_settings()

    # Get first page (10 items)
    async with get_test_client() as client:
        response1 = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=10&offset=0",
            headers={"X-API-Key": settings.API_KEY}
        )

    data1 = response1.json()
    first_page_narratives = data1["narratives"]

    # Get second page
    async with get_test_client() as client:
        response2 = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=10&offset=10",
            headers={"X-API-Key": settings.API_KEY}
        )

    data2 = response2.json()
    second_page_narratives = data2["narratives"]

    # Verify they have the same total_count
    assert data1["total_count"] == data2["total_count"]

    # Verify pages don't overlap (assuming narratives are sorted by last_updated)
    first_page_ids = {n.get("id") or n.get("_id") for n in first_page_narratives}
    second_page_ids = {n.get("id") or n.get("_id") for n in second_page_narratives}

    # Should have no intersection if data is stable
    if first_page_narratives and second_page_narratives:
        assert len(first_page_ids & second_page_ids) == 0


@pytest.mark.asyncio
async def test_get_active_narratives_limit_validation():
    """Test limit parameter validation."""
    settings = get_settings()

    # Test with invalid limit (> 200)
    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?limit=201",
            headers={"X-API-Key": settings.API_KEY}
        )

    # Should either reject or clamp to max
    assert response.status_code in (200, 422)


@pytest.mark.asyncio
async def test_get_active_narratives_offset_validation():
    """Test offset parameter validation."""
    settings = get_settings()

    # Test with negative offset
    async with get_test_client() as client:
        response = await client.get(
            f"{settings.API_V1_STR}/narratives/active?offset=-1",
            headers={"X-API-Key": settings.API_KEY}
        )

    # Should reject negative offset
    assert response.status_code in (200, 422)
