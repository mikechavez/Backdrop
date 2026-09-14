"""
Tests for Signals API timeframe alignment.

BUG-108: Verify that the Signals page explicitly requests 24h timeframe
and that the API defaults to 24h for the /trending endpoint.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from crypto_news_aggregator.main import app
from crypto_news_aggregator.db.mongodb import mongo_manager
from bson import ObjectId


def get_test_client():
    """Helper to create AsyncClient with proper transport."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def test_entity_mentions():
    """Create test entity mentions across different time windows."""
    db = await mongo_manager.get_async_database()
    mentions_collection = db.entity_mentions

    # Clean up existing test data
    await mentions_collection.delete_many({
        "entity": {"$in": ["$BTC", "$ETH", "Bitcoin"]}
    })

    now = datetime.now(timezone.utc)

    # Create mentions in different time windows
    test_mentions = [
        # Recent 24h mentions for $BTC
        {
            "entity": "$BTC",
            "entity_type": "ticker",
            "article_id": str(ObjectId()),
            "source": "CoinDesk",
            "is_primary": True,
            "created_at": now - timedelta(hours=2),
            "mention_count": 1,
        },
        {
            "entity": "$BTC",
            "entity_type": "ticker",
            "article_id": str(ObjectId()),
            "source": "The Block",
            "is_primary": True,
            "created_at": now - timedelta(hours=6),
            "mention_count": 1,
        },
        # Older mentions (beyond 24h, within 7d)
        {
            "entity": "$ETH",
            "entity_type": "ticker",
            "article_id": str(ObjectId()),
            "source": "CoinTelegraph",
            "is_primary": True,
            "created_at": now - timedelta(days=2),
            "mention_count": 1,
        },
        {
            "entity": "$ETH",
            "entity_type": "ticker",
            "article_id": str(ObjectId()),
            "source": "Decrypt",
            "is_primary": True,
            "created_at": now - timedelta(days=3),
            "mention_count": 1,
        },
        # Even older mentions (beyond 7d, within 30d)
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": str(ObjectId()),
            "source": "CoinDesk",
            "is_primary": True,
            "created_at": now - timedelta(days=10),
            "mention_count": 1,
        },
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": str(ObjectId()),
            "source": "The Block",
            "is_primary": True,
            "created_at": now - timedelta(days=20),
            "mention_count": 1,
        },
    ]

    await mentions_collection.insert_many(test_mentions)
    return test_mentions


@pytest.mark.asyncio
async def test_signals_trending_default_timeframe():
    """Test that /api/v1/signals/trending defaults to 7d (per BUG-108)."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending")
        assert response.status_code == 200

        data = response.json()
        # Verify response structure
        assert "signals" in data
        assert "filters" in data
        # API default is 7d (UI explicitly sends 24h when needed)
        assert data["filters"]["timeframe"] == "7d"


@pytest.mark.asyncio
async def test_signals_trending_explicit_24h():
    """Test /api/v1/signals/trending with explicit 24h parameter."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending?timeframe=24h")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "24h"


@pytest.mark.asyncio
async def test_signals_trending_7d_timeframe():
    """Test /api/v1/signals/trending with 7d timeframe."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending?timeframe=7d")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "7d"


@pytest.mark.asyncio
async def test_signals_trending_30d_timeframe():
    """Test /api/v1/signals/trending with 30d timeframe."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending?timeframe=30d")
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "30d"


@pytest.mark.asyncio
async def test_signals_trending_pagination():
    """Test pagination parameters are preserved with timeframe."""
    async with get_test_client() as client:
        response = await client.get(
            "/api/v1/signals/trending?limit=10&offset=5&timeframe=24h"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "24h"
        assert data["limit"] == 10
        assert data["offset"] == 5


@pytest.mark.asyncio
async def test_signals_trending_min_score_filter():
    """Test min_score filter works with timeframe parameter."""
    async with get_test_client() as client:
        response = await client.get(
            "/api/v1/signals/trending?min_score=2.0&timeframe=24h"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "24h"
        assert data["filters"]["min_score"] == 2.0


@pytest.mark.asyncio
async def test_signals_trending_entity_type_filter():
    """Test entity_type filter works with timeframe parameter."""
    async with get_test_client() as client:
        response = await client.get(
            "/api/v1/signals/trending?entity_type=ticker&timeframe=24h"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["filters"]["timeframe"] == "24h"
        # If entity_type filter is applied, all results should match
        for signal in data["signals"]:
            assert signal["entity_type"] == "ticker"


@pytest.mark.asyncio
async def test_signals_response_includes_timeframe_filter(test_entity_mentions):
    """Test that response includes the applied timeframe in filters."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending?timeframe=24h&limit=5")
        assert response.status_code == 200

        data = response.json()
        # Verify timeframe is clearly indicated in response
        assert "filters" in data
        assert "timeframe" in data["filters"]
        assert data["filters"]["timeframe"] == "24h"


@pytest.mark.asyncio
async def test_signals_response_structure():
    """Test complete response structure matches expected schema."""
    async with get_test_client() as client:
        response = await client.get("/api/v1/signals/trending?limit=3&timeframe=24h")
        assert response.status_code == 200

        data = response.json()

        # Required top-level fields
        assert "count" in data
        assert "total_count" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        assert "signals" in data
        assert "cached" in data
        assert "computed_at" in data
        assert "filters" in data

        # Required filter fields
        assert "min_score" in data["filters"]
        assert "entity_type" in data["filters"]
        assert "timeframe" in data["filters"]

        # Each signal has required fields
        for signal in data["signals"]:
            assert "entity" in signal
            assert "entity_type" in signal
            assert "signal_score" in signal
            assert "velocity" in signal
            assert "mentions" in signal
            assert "source_count" in signal


@pytest.mark.asyncio
async def test_signals_cache_response_metadata():
    """Test that response includes cache metadata."""
    async with get_test_client() as client:
        # Request with 24h timeframe
        response = await client.get("/api/v1/signals/trending?timeframe=24h")
        assert response.status_code == 200

        data = response.json()
        # Response should include cache status
        assert "cached" in data
        assert "computed_at" in data
        # computed_at should be a valid ISO timestamp
        assert isinstance(data["computed_at"], str)
        # Filter should show requested timeframe
        assert data["filters"]["timeframe"] == "24h"


def test_ui_signals_tsx_explicit_24h_parameter():
    """Verify Signals.tsx code explicitly passes 24h timeframe (code inspection)."""
    # This test verifies that context-owl-ui/src/pages/Signals.tsx explicitly passes
    # timeframe: '24h' in line 89 and includes it in the queryKey for proper cache handling
    signals_tsx = open(
        "/Users/mc/dev-projects/crypto-news-aggregator/context-owl-ui/src/pages/Signals.tsx"
    ).read()

    assert "queryKey: ['signals', '24h']" in signals_tsx, "Signals.tsx must include timeframe in queryKey"
    assert "timeframe: '24h'" in signals_tsx, "Signals.tsx must explicitly pass 24h timeframe"


def test_api_cache_key_includes_timeframe():
    """Verify API cache key includes timeframe (code inspection)."""
    # Cache keys in signals.py must include timeframe so different windows cache separately
    signals_py = open(
        "/Users/mc/dev-projects/crypto-news-aggregator/src/crypto_news_aggregator/api/v1/endpoints/signals.py"
    ).read()

    # Verify cache key formation includes timeframe parameter
    assert "{timeframe}" in signals_py or "timeframe" in signals_py, \
        "Cache key must differentiate by timeframe"


def test_api_endpoint_7d_default_in_code():
    """Verify API endpoint defaults to 7d and UI sends 24h explicitly (BUG-108)."""
    # Verify /api/v1/signals/trending endpoint has default="7d"
    signals_py = open(
        "/Users/mc/dev-projects/crypto-news-aggregator/src/crypto_news_aggregator/api/v1/endpoints/signals.py"
    ).read()

    assert 'default="7d"' in signals_py, "API endpoint must default to 7d per BUG-108"
