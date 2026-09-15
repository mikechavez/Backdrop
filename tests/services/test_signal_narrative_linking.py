"""
Tests for signal-to-narrative linking functionality.
"""

import pytest
from datetime import datetime, timezone
from crypto_news_aggregator.services.signal_service import calculate_signal_score
from crypto_news_aggregator.db.mongodb import mongo_manager


@pytest.mark.asyncio
async def test_signal_score_includes_narrative_fields():
    """Test that signal score includes narrative_ids and is_emerging fields."""
    db = await mongo_manager.get_async_database()
    entity_mentions = db.entity_mentions
    
    test_entity = "TestEntity"
    mention = await entity_mentions.insert_one({
        "entity": test_entity,
        "is_primary": True,
        "sentiment": "neutral",
        "source": "test",
        "created_at": datetime.now(timezone.utc),
        "published_at": datetime.now(timezone.utc),
    })
    
    try:
        signal_data = await calculate_signal_score(test_entity)
        
        # Verify new fields exist
        assert "narrative_ids" in signal_data
        assert "is_emerging" in signal_data
        assert isinstance(signal_data["narrative_ids"], list)
        assert isinstance(signal_data["is_emerging"], bool)
        
    finally:
        await entity_mentions.delete_one({"_id": mention.inserted_id})


