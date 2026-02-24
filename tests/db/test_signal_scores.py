"""
Tests for signal_scores database operations.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.db.operations.signal_scores import (
    upsert_signal_score,
    get_trending_entities,
    get_entity_signal,
    delete_old_signals,
)
from crypto_news_aggregator.db.mongodb import mongo_manager


@pytest.mark.asyncio
async def test_upsert_signal_score_create(mongo_db):
    """Test creating a new signal score."""
    collection = mongo_db.signal_scores
    
    # Clean up
    await collection.delete_many({"entity": "TEST_CREATE"})
    
    # Create new signal score
    signal_id = await upsert_signal_score(
        entity="TEST_CREATE",
        entity_type="ticker",
        score=7.5,
        velocity=10.0,
        source_count=8,
        sentiment={"avg": 0.5, "min": 0.0, "max": 1.0, "divergence": 0.2},
    )
    
    assert signal_id is not None
    
    # Verify it was created
    signal = await collection.find_one({"entity": "TEST_CREATE"})
    assert signal is not None
    assert signal["entity_type"] == "ticker"
    assert signal["score"] == 7.5
    assert signal["velocity"] == 10.0
    assert signal["source_count"] == 8
    
    # Clean up
    await collection.delete_many({"entity": "TEST_CREATE"})


@pytest.mark.asyncio
async def test_upsert_signal_score_update(mongo_db):
    """Test updating an existing signal score."""
    collection = mongo_db.signal_scores
    
    # Clean up
    await collection.delete_many({"entity": "TEST_UPDATE"})
    
    # Create initial signal score
    await upsert_signal_score(
        entity="TEST_UPDATE",
        entity_type="ticker",
        score=5.0,
        velocity=5.0,
        source_count=3,
        sentiment={"avg": 0.2, "min": 0.0, "max": 0.5, "divergence": 0.1},
    )
    
    # Update with new values
    await upsert_signal_score(
        entity="TEST_UPDATE",
        entity_type="ticker",
        score=8.0,
        velocity=12.0,
        source_count=10,
        sentiment={"avg": 0.7, "min": 0.2, "max": 1.0, "divergence": 0.3},
    )
    
    # Verify it was updated (not duplicated)
    count = await collection.count_documents({"entity": "TEST_UPDATE"})
    assert count == 1
    
    signal = await collection.find_one({"entity": "TEST_UPDATE"})
    assert signal["score"] == 8.0
    assert signal["velocity"] == 12.0
    assert signal["source_count"] == 10
    
    # Clean up
    await collection.delete_many({"entity": "TEST_UPDATE"})


@pytest.mark.asyncio
async def test_get_trending_entities(mongo_db):
    """Test getting trending entities."""
    collection = mongo_db.signal_scores
    entity_mentions = mongo_db.entity_mentions

    # Clean up
    await collection.delete_many({"entity": {"$in": ["TREND1", "TREND2", "TREND3"]}})
    await entity_mentions.delete_many({"entity": {"$in": ["TREND1", "TREND2", "TREND3"]}})

    now = datetime.now(timezone.utc)

    # Create test data with timeframe-specific scores
    await upsert_signal_score(
        entity="TREND1",
        entity_type="ticker",
        score=9.0,
        velocity=15.0,
        source_count=12,
        sentiment={"avg": 0.8, "min": 0.5, "max": 1.0, "divergence": 0.2},
        score_7d=9.0,
    )

    await upsert_signal_score(
        entity="TREND2",
        entity_type="project",
        score=6.5,
        velocity=8.0,
        source_count=7,
        sentiment={"avg": 0.4, "min": 0.0, "max": 0.8, "divergence": 0.3},
        score_7d=6.5,
    )

    await upsert_signal_score(
        entity="TREND3",
        entity_type="ticker",
        score=7.8,
        velocity=11.0,
        source_count=9,
        sentiment={"avg": 0.6, "min": 0.2, "max": 1.0, "divergence": 0.25},
        score_7d=7.8,
    )

    # Create entity_mentions to validate recent activity (required by get_trending_entities)
    await entity_mentions.insert_many([
        {"entity": "TREND1", "is_primary": True, "created_at": now, "source": "test1", "article_id": "art1"},
        {"entity": "TREND2", "is_primary": True, "created_at": now, "source": "test2", "article_id": "art2"},
        {"entity": "TREND3", "is_primary": True, "created_at": now, "source": "test3", "article_id": "art3"},
    ])

    # Get trending entities
    trending = await get_trending_entities(limit=10, min_score=0.0, timeframe="7d")

    assert len(trending) >= 3

    # Should be sorted by score (descending)
    scores = [t["score"] for t in trending]
    assert scores == sorted(scores, reverse=True)

    # Top entity should be TREND1
    assert trending[0]["entity"] == "TREND1"
    assert trending[0]["score"] == 9.0

    # Clean up
    await collection.delete_many({"entity": {"$in": ["TREND1", "TREND2", "TREND3"]}})
    await entity_mentions.delete_many({"entity": {"$in": ["TREND1", "TREND2", "TREND3"]}})


@pytest.mark.asyncio
async def test_get_trending_entities_with_filters(mongo_db):
    """Test getting trending entities with filters."""
    collection = mongo_db.signal_scores
    entity_mentions = mongo_db.entity_mentions

    # Clean up
    await collection.delete_many({"entity": {"$in": ["FILT1", "FILT2", "FILT3"]}})
    await entity_mentions.delete_many({"entity": {"$in": ["FILT1", "FILT2", "FILT3"]}})

    now = datetime.now(timezone.utc)

    # Create test data with timeframe-specific scores
    await upsert_signal_score(
        entity="FILT1",
        entity_type="ticker",
        score=8.0,
        velocity=10.0,
        source_count=8,
        sentiment={"avg": 0.5, "min": 0.0, "max": 1.0, "divergence": 0.2},
        score_7d=8.0,
    )

    await upsert_signal_score(
        entity="FILT2",
        entity_type="project",
        score=9.0,
        velocity=12.0,
        source_count=10,
        sentiment={"avg": 0.7, "min": 0.3, "max": 1.0, "divergence": 0.25},
        score_7d=9.0,
    )

    await upsert_signal_score(
        entity="FILT3",
        entity_type="ticker",
        score=5.0,
        velocity=6.0,
        source_count=5,
        sentiment={"avg": 0.3, "min": 0.0, "max": 0.6, "divergence": 0.15},
        score_7d=5.0,
    )

    # Create entity_mentions to validate recent activity
    await entity_mentions.insert_many([
        {"entity": "FILT1", "is_primary": True, "created_at": now, "source": "test1", "article_id": "art1"},
        {"entity": "FILT2", "is_primary": True, "created_at": now, "source": "test2", "article_id": "art2"},
        {"entity": "FILT3", "is_primary": True, "created_at": now, "source": "test3", "article_id": "art3"},
    ])

    # Test min_score filter
    high_score = await get_trending_entities(limit=10, min_score=7.0, timeframe="7d")
    high_score_entities = [t["entity"] for t in high_score]
    assert "FILT1" in high_score_entities
    assert "FILT2" in high_score_entities
    assert "FILT3" not in high_score_entities

    # Test entity_type filter
    tickers_only = await get_trending_entities(limit=10, entity_type="ticker", timeframe="7d")
    ticker_entities = [t["entity"] for t in tickers_only if t["entity"] in ["FILT1", "FILT2", "FILT3"]]
    for entity in ticker_entities:
        assert entity in ["FILT1", "FILT3"]

    # Test limit
    limited = await get_trending_entities(limit=1, min_score=0.0, timeframe="7d")
    # Should return at most 1 result
    assert len([t for t in limited if t["entity"] in ["FILT1", "FILT2", "FILT3"]]) <= 1

    # Clean up
    await collection.delete_many({"entity": {"$in": ["FILT1", "FILT2", "FILT3"]}})
    await entity_mentions.delete_many({"entity": {"$in": ["FILT1", "FILT2", "FILT3"]}})


@pytest.mark.asyncio
async def test_get_entity_signal(mongo_db):
    """Test getting signal for a specific entity."""
    collection = mongo_db.signal_scores
    
    # Clean up
    await collection.delete_many({"entity": "SPECIFIC_ENTITY"})
    
    # Create signal score
    await upsert_signal_score(
        entity="SPECIFIC_ENTITY",
        entity_type="project",
        score=7.2,
        velocity=9.5,
        source_count=8,
        sentiment={"avg": 0.55, "min": 0.1, "max": 0.9, "divergence": 0.22},
    )
    
    # Get the signal
    signal = await get_entity_signal("SPECIFIC_ENTITY")
    
    assert signal is not None
    assert signal["entity"] == "SPECIFIC_ENTITY"
    assert signal["entity_type"] == "project"
    assert signal["score"] == 7.2
    
    # Test non-existent entity
    no_signal = await get_entity_signal("NONEXISTENT")
    assert no_signal is None
    
    # Clean up
    await collection.delete_many({"entity": "SPECIFIC_ENTITY"})


@pytest.mark.asyncio
async def test_delete_old_signals(mongo_db):
    """Test deleting old signal scores."""
    collection = mongo_db.signal_scores
    
    # Clean up
    await collection.delete_many({"entity": {"$in": ["OLD1", "OLD2", "RECENT"]}})
    
    # Create old signals
    old_time = datetime.now(timezone.utc) - timedelta(days=10)
    await collection.insert_one({
        "entity": "OLD1",
        "entity_type": "ticker",
        "score": 5.0,
        "velocity": 5.0,
        "source_count": 3,
        "sentiment": {},
        "last_updated": old_time,
        "created_at": old_time,
    })
    
    await collection.insert_one({
        "entity": "OLD2",
        "entity_type": "project",
        "score": 6.0,
        "velocity": 7.0,
        "source_count": 4,
        "sentiment": {},
        "last_updated": old_time,
        "created_at": old_time,
    })
    
    # Create recent signal
    await upsert_signal_score(
        entity="RECENT",
        entity_type="ticker",
        score=8.0,
        velocity=10.0,
        source_count=8,
        sentiment={"avg": 0.5, "min": 0.0, "max": 1.0, "divergence": 0.2},
    )
    
    # Delete signals older than 7 days
    deleted_count = await delete_old_signals(days=7)
    
    assert deleted_count >= 2
    
    # Verify old signals are gone
    old1 = await collection.find_one({"entity": "OLD1"})
    old2 = await collection.find_one({"entity": "OLD2"})
    assert old1 is None
    assert old2 is None
    
    # Verify recent signal still exists
    recent = await collection.find_one({"entity": "RECENT"})
    assert recent is not None
    
    # Clean up
    await collection.delete_many({"entity": "RECENT"})
