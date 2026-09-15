"""
Tests for signal detection service.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.services.signal_service import (
    calculate_velocity,
    calculate_source_diversity,
    calculate_sentiment_metrics,
    calculate_signal_score,
    calculate_mentions_and_velocity,
    calculate_recency_factor,
)
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.db.operations.entity_mentions import create_entity_mention


@pytest.mark.asyncio
async def test_calculate_velocity_no_mentions(mongo_db):
    """Test velocity calculation with no mentions."""
    velocity = await calculate_velocity("NONEXISTENT_ENTITY")
    assert velocity == 0.0


@pytest.mark.asyncio
async def test_calculate_velocity_with_mentions(mongo_db):
    """Test velocity calculation with recent mentions."""
    collection = mongo_db.entity_mentions

    # Clean up test data
    await collection.delete_many({"entity": "TEST_VELOCITY"})

    now = datetime.now(timezone.utc)

    # Create mentions: 5 in last hour, 10 in last 24 hours
    for i in range(5):
        await create_entity_mention(
            entity="TEST_VELOCITY",
            entity_type="ticker",
            article_id=f"article_{i}",
            sentiment="neutral",
            is_primary=True,
            published_at=now,
        )

    # Create older mentions (2-24 hours ago)
    for i in range(5, 10):
        older_time = now - timedelta(hours=2 + i)
        await collection.insert_one({
            "entity": "TEST_VELOCITY",
            "entity_type": "ticker",
            "article_id": f"article_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "timestamp": older_time,
            "created_at": older_time,
            "published_at": older_time,
        })

    velocity = await calculate_velocity("TEST_VELOCITY")
    
    # Expected: 5 / (10 / 24) = 5 / 0.417 = ~12
    assert velocity > 0
    
    # Clean up
    await collection.delete_many({"entity": "TEST_VELOCITY"})


@pytest.mark.asyncio
async def test_calculate_source_diversity(mongo_db):
    """Test source diversity calculation.
    
    Note: After fix, source diversity is calculated directly from entity_mentions.source field,
    not by looking up articles. Entity mentions have 'source' field populated.
    """
    entity_mentions_collection = mongo_db.entity_mentions
    
    # Clean up test data
    await entity_mentions_collection.delete_many({"entity": "TEST_DIVERSITY"})
    
    # Create entity mentions with different sources
    # The 'source' field is set directly on entity mentions
    now = datetime.now(timezone.utc)
    await create_entity_mention(
        entity="TEST_DIVERSITY",
        entity_type="project",
        article_id="art1",
        sentiment="positive",
        is_primary=True,
        source="source_a",
        published_at=now,
    )
    await create_entity_mention(
        entity="TEST_DIVERSITY",
        entity_type="project",
        article_id="art2",
        sentiment="positive",
        is_primary=True,
        source="source_b",
        published_at=now,
    )
    await create_entity_mention(
        entity="TEST_DIVERSITY",
        entity_type="project",
        article_id="art3",
        sentiment="neutral",
        is_primary=True,
        source="source_a",  # Duplicate source
        published_at=now,
    )

    diversity = await calculate_source_diversity("TEST_DIVERSITY")
    
    # Should have 2 unique sources (source_a and source_b)
    assert diversity == 2
    
    # Clean up
    await entity_mentions_collection.delete_many({"entity": "TEST_DIVERSITY"})


@pytest.mark.asyncio
async def test_calculate_sentiment_metrics(mongo_db):
    """Test sentiment metrics calculation."""
    collection = mongo_db.entity_mentions
    
    # Clean up test data
    await collection.delete_many({"entity": "TEST_SENTIMENT"})
    
    # Create mentions with different sentiments
    await create_entity_mention(
        entity="TEST_SENTIMENT",
        entity_type="ticker",
        article_id="art1",
        sentiment="positive",
        is_primary=True,
    )
    await create_entity_mention(
        entity="TEST_SENTIMENT",
        entity_type="ticker",
        article_id="art2",
        sentiment="positive",
        is_primary=True,
    )
    await create_entity_mention(
        entity="TEST_SENTIMENT",
        entity_type="ticker",
        article_id="art3",
        sentiment="negative",
        is_primary=True,
    )
    await create_entity_mention(
        entity="TEST_SENTIMENT",
        entity_type="ticker",
        article_id="art4",
        sentiment="neutral",
        is_primary=True,
    )
    
    metrics = await calculate_sentiment_metrics("TEST_SENTIMENT")
    
    # Check structure
    assert "avg" in metrics
    assert "min" in metrics
    assert "max" in metrics
    assert "divergence" in metrics
    
    # Check values (2 positive, 1 negative, 1 neutral = avg of 0.5)
    # positive=1.0, negative=-1.0, neutral=0.0
    # avg = (1.0 + 1.0 + (-1.0) + 0.0) / 4 = 0.25
    assert metrics["avg"] == pytest.approx(0.25, abs=0.01)
    assert metrics["min"] == -1.0
    assert metrics["max"] == 1.0
    assert metrics["divergence"] > 0  # Should have some variance
    
    # Clean up
    await collection.delete_many({"entity": "TEST_SENTIMENT"})


@pytest.mark.asyncio
async def test_calculate_signal_score(mongo_db):
    """Test overall signal score calculation."""
    entity_mentions_collection = mongo_db.entity_mentions
    
    # Clean up test data
    await entity_mentions_collection.delete_many({"entity": "TEST_SIGNAL"})
    
    # Create entity mentions with different sources
    now = datetime.now(timezone.utc)
    for i in range(3):
        await create_entity_mention(
            entity="TEST_SIGNAL",
            entity_type="ticker",
            article_id=f"sig{i}",
            sentiment="positive",
            is_primary=True,
            source="source_x",
            published_at=now,
        )

    await create_entity_mention(
        entity="TEST_SIGNAL",
        entity_type="ticker",
        article_id="sig4",
        sentiment="positive",
        is_primary=True,
        source="source_y",
        published_at=now,
    )

    signal_data = await calculate_signal_score("TEST_SIGNAL")
    
    # Check structure
    assert "score" in signal_data
    assert "velocity" in signal_data
    assert "source_count" in signal_data
    assert "sentiment" in signal_data
    
    # Check score is in valid range
    assert 0 <= signal_data["score"] <= 10
    assert signal_data["source_count"] == 2
    assert signal_data["velocity"] > 0
    
    # Clean up
    await entity_mentions_collection.delete_many({"entity": "TEST_SIGNAL"})


@pytest.mark.asyncio
async def test_calculate_signal_score_no_data(mongo_db):
    """Test signal score calculation with no data."""
    signal_data = await calculate_signal_score("NONEXISTENT_SIGNAL")
    
    # Should return valid structure with zero values
    assert signal_data["score"] == 0.0
    assert signal_data["velocity"] == 0.0
    assert signal_data["source_count"] == 0
    assert signal_data["sentiment"]["avg"] == 0.0


@pytest.mark.asyncio
async def test_velocity_uses_created_at_field(mongo_db):
    """
    Regression test: Ensure velocity calculation uses 'created_at' field, not 'timestamp'.
    
    This test was added after fixing a bug where the service queried 'timestamp' field
    which doesn't exist on entity mentions (they use 'created_at').
    """
    collection = mongo_db.entity_mentions
    
    # Clean up
    await collection.delete_many({"entity": "TEST_FIELD_NAME"})
    
    # Create a recent mention with only 'created_at' field (no 'timestamp')
    now = datetime.now(timezone.utc)
    await collection.insert_one({
        "entity": "TEST_FIELD_NAME",
        "entity_type": "ticker",
        "article_id": "test_art",
        "sentiment": "neutral",
        "is_primary": True,
        "source": "test_source",
        "created_at": now,  # Only created_at, no timestamp field
        "published_at": now,
        "metadata": {},
    })
    
    # This should find the mention using created_at field
    velocity = await calculate_velocity("TEST_FIELD_NAME")
    
    # Should be > 0 since we have a recent mention
    assert velocity > 0, "Velocity should be > 0 when recent mentions exist with created_at field"
    
    # Clean up
    await collection.delete_many({"entity": "TEST_FIELD_NAME"})


@pytest.mark.asyncio
async def test_source_diversity_uses_source_field(mongo_db):
    """
    Regression test: Ensure source diversity uses 'source' field from entity_mentions directly.
    
    This test was added after fixing a bug where the service did complex aggregation
    through articles collection instead of using the 'source' field on entity mentions.
    """
    collection = mongo_db.entity_mentions
    
    # Clean up
    await collection.delete_many({"entity": "TEST_SOURCE_FIELD"})
    
    # Create mentions with source field directly (no articles needed)
    now = datetime.now(timezone.utc)
    await collection.insert_many([
        {
            "entity": "TEST_SOURCE_FIELD",
            "entity_type": "ticker",
            "article_id": "art1",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "source_a",
            "created_at": now,
            "published_at": now,
            "metadata": {},
        },
        {
            "entity": "TEST_SOURCE_FIELD",
            "entity_type": "ticker",
            "article_id": "art2",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "source_b",
            "created_at": now,
            "published_at": now,
            "metadata": {},
        },
        {
            "entity": "TEST_SOURCE_FIELD",
            "entity_type": "ticker",
            "article_id": "art3",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "source_a",  # Duplicate
            "created_at": now,
            "published_at": now,
            "metadata": {},
        },
    ])
    
    # Should count 2 unique sources without needing articles collection
    diversity = await calculate_source_diversity("TEST_SOURCE_FIELD")
    
    assert diversity == 2, "Should count unique sources from entity_mentions.source field"
    
    # Clean up
    await collection.delete_many({"entity": "TEST_SOURCE_FIELD"})


@pytest.mark.asyncio
async def test_calculate_mentions_and_velocity_growth(mongo_db):
    """Test multi-timeframe velocity calculation showing positive growth."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Current period: 50 mentions, Previous period: 30 mentions
    for i in range(50):
        await collection.insert_one({
            "entity": "TEST_MF_GROWTH",
            "entity_type": "ticker",
            "article_id": f"current_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=12),
            "published_at": now - timedelta(hours=12),
            "metadata": {},
        })

    for i in range(30):
        await collection.insert_one({
            "entity": "TEST_MF_GROWTH",
            "entity_type": "ticker",
            "article_id": f"previous_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=36),
            "published_at": now - timedelta(hours=36),
            "metadata": {},
        })
    
    result = await calculate_mentions_and_velocity("TEST_MF_GROWTH", timeframe_hours=24)
    
    # Expected: (50 - 30) / 30 * 100 = 66.67% growth
    assert result["mentions"] == 50.0
    assert result["velocity"] == pytest.approx(66.67, abs=0.1)
    
    await collection.delete_many({"entity": "TEST_MF_GROWTH"})


@pytest.mark.asyncio
async def test_calculate_recency_factor(mongo_db):
    """Test recency factor calculation for multi-timeframe scoring."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # All mentions in most recent 20% of timeframe
    for i in range(20):
        await collection.insert_one({
            "entity": "TEST_MF_RECENCY",
            "entity_type": "ticker",
            "article_id": f"recent_{i}",
            "sentiment": "neutral",
            "is_primary": True,
            "source": "test_source",
            "created_at": now - timedelta(hours=2),
            "published_at": now - timedelta(hours=2),
            "metadata": {},
        })
    
    recency = await calculate_recency_factor("TEST_MF_RECENCY", timeframe_hours=24)
    
    # Should be close to 1.0 since all mentions are recent
    assert recency == pytest.approx(1.0, abs=0.01)
    
    await collection.delete_many({"entity": "TEST_MF_RECENCY"})


@pytest.mark.asyncio
async def test_calculate_signal_score_with_timeframe(mongo_db):
    """Test signal score calculation with timeframe parameter."""
    collection = mongo_db.entity_mentions
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Create test data
    for i in range(50):
        await collection.insert_one({
            "entity": "TEST_MF_SIGNAL",
            "entity_type": "ticker",
            "article_id": f"current_{i}",
            "sentiment": "positive",
            "is_primary": True,
            "source": f"source_{i % 5}",
            "created_at": now - timedelta(hours=6),
            "published_at": now - timedelta(hours=6),
            "metadata": {},
        })
    
    signal = await calculate_signal_score("TEST_MF_SIGNAL", timeframe_hours=24)
    
    # Check structure includes new fields
    assert "score" in signal
    assert "velocity" in signal
    assert "mentions" in signal
    assert "source_count" in signal
    assert "recency_factor" in signal
    
    # Check values
    assert 0 <= signal["score"] <= 10
    assert signal["mentions"] == 50
    assert signal["source_count"] == 5
    
    await collection.delete_many({"entity": "TEST_MF_SIGNAL"})
