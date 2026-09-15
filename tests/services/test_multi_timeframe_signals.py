"""
Unit tests for multi-timeframe signal scoring.

Tests the new 24h, 7d, and 30d timeframe calculations.
"""

import pytest
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.services.signal_service import (
    calculate_mentions_and_velocity,
    calculate_recency_factor,
    calculate_signal_score,
)


@pytest.mark.asyncio
async def test_calculate_mentions_and_velocity_no_data(mongo_db):
    """Test velocity calculation with no mentions."""
    result = await calculate_mentions_and_velocity("NONEXISTENT", timeframe_hours=24)
    
    assert result["mentions"] == 0.0
    assert result["velocity"] == 0.0


@pytest.mark.asyncio
async def test_calculate_mentions_and_velocity_growth(mongo_db):
    """Test velocity calculation showing positive growth."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Current period (last 24 hours): 50 mentions
    for i in range(50):
        await collection.insert_one({
            "entity": "TEST_GROWTH",
            "entity_type": "ticker",
            "article_id": f"current_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=12),
            "published_at": now - timedelta(hours=12),
            "metadata": {},
        })

    # Previous period (24-48 hours ago): 30 mentions
    for i in range(30):
        await collection.insert_one({
            "entity": "TEST_GROWTH",
            "entity_type": "ticker",
            "article_id": f"previous_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=36),
            "published_at": now - timedelta(hours=36),
            "metadata": {},
        })
    
    result = await calculate_mentions_and_velocity("TEST_GROWTH", timeframe_hours=24)
    
    # Expected: (50 - 30) / 30 = 0.667 (67% growth)
    assert result["mentions"] == 50.0
    assert result["velocity"] == pytest.approx(0.667, abs=0.01)


@pytest.mark.asyncio
async def test_calculate_mentions_and_velocity_decline(mongo_db):
    """Test velocity calculation showing negative growth."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Current: 20, Previous: 50 = -60% decline
    for i in range(20):
        await collection.insert_one({
            "entity": "TEST_DECLINE",
            "entity_type": "ticker",
            "article_id": f"current_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=12),
            "published_at": now - timedelta(hours=12),
            "metadata": {},
        })

    for i in range(50):
        await collection.insert_one({
            "entity": "TEST_DECLINE",
            "entity_type": "ticker",
            "article_id": f"previous_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=36),
            "published_at": now - timedelta(hours=36),
            "metadata": {},
        })
    
    result = await calculate_mentions_and_velocity("TEST_DECLINE", timeframe_hours=24)
    
    assert result["mentions"] == 20.0
    assert result["velocity"] == pytest.approx(-0.6, abs=0.01)


@pytest.mark.asyncio
async def test_calculate_recency_factor_all_recent(mongo_db):
    """Test recency factor when all mentions are recent."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # All mentions in most recent 20% of timeframe
    for i in range(20):
        await collection.insert_one({
            "entity": "TEST_RECENCY_HIGH",
            "entity_type": "ticker",
            "article_id": f"recent_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=2),
            "published_at": now - timedelta(hours=2),
            "metadata": {},
        })
    
    recency = await calculate_recency_factor("TEST_RECENCY_HIGH", timeframe_hours=24)
    
    assert recency == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_calculate_signal_score_with_timeframe(mongo_db):
    """Test signal score calculation with timeframe parameter."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Create test data
    for i in range(50):
        await collection.insert_one({
            "entity": "TEST_SIGNAL_TF",
            "entity_type": "ticker",
            "article_id": f"current_{i}",
            "sentiment": "positive",
            "is_primary": True,
            "source": f"source_{i % 5}",
            "created_at": now - timedelta(hours=6),
            "published_at": now - timedelta(hours=6),
            "metadata": {},
        })
    
    signal = await calculate_signal_score("TEST_SIGNAL_TF", timeframe_hours=24)
    
    # Check structure
    assert "score" in signal
    assert "velocity" in signal
    assert "mentions" in signal
    assert "source_count" in signal
    assert "recency_factor" in signal
    
    # Check values
    assert 0 <= signal["score"] <= 10
    assert signal["mentions"] == 50
    assert signal["source_count"] == 5
