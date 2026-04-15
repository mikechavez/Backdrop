"""
Integration tests for LLM cost tracking.

Tests verify that:
1. LLM calls are properly tracked to the database
2. Token counts are extracted and recorded
3. Cost calculations are accurate
4. Cache hits are tracked separately
5. Different operation types are labeled correctly

NOTE: Tests write to llm_traces (the single source of truth for budget enforcement after BUG-079).
"""

import pytest
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import Mock, patch, AsyncMock

from crypto_news_aggregator.services.cost_tracker import CostTracker
from crypto_news_aggregator.llm.optimized_anthropic import OptimizedAnthropicLLM


async def _insert_trace_record(mongo_db, operation, model, input_tokens, output_tokens, cost):
    """Helper to insert a record into llm_traces (source of truth after BUG-079)."""
    await mongo_db.llm_traces.insert_one({
        "timestamp": datetime.now(timezone.utc),
        "operation": operation,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    })


@pytest.fixture
async def test_db():
    """Create test database connection."""
    client = AsyncIOMotorClient("mongodb://localhost:27017", tz_aware=True)
    db = client.test_llm_cost_tracking

    # Clear collections before test
    await db.api_costs.delete_many({})
    await db.llm_cache.delete_many({})
    await db.llm_traces.delete_many({})

    yield db

    # Cleanup after test
    await db.api_costs.delete_many({})
    await db.llm_cache.delete_many({})
    await db.llm_traces.delete_many({})
    client.close()


@pytest.mark.asyncio
async def test_cost_tracker_tracks_api_call(test_db):
    """Test that cost tracker properly records API calls."""
    tracker = CostTracker(test_db)

    # Track a call
    cost = await tracker.track_call(
        operation="entity_extraction",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cached=False
    )

    # Verify cost calculation
    assert cost > 0
    assert cost < 0.01  # Should be very cheap for Haiku

    # Verify database entry
    doc = await test_db.api_costs.find_one({"operation": "entity_extraction"})
    assert doc is not None
    assert doc["model"] == "claude-haiku-4-5-20251001"
    assert doc["input_tokens"] == 100
    assert doc["output_tokens"] == 50
    assert doc["cost"] == cost
    assert doc["cached"] is False


@pytest.mark.asyncio
async def test_cost_tracker_tracks_cached_call(test_db):
    """Test that cached calls are tracked with zero cost."""
    tracker = CostTracker(test_db)

    # Track a cached call
    cost = await tracker.track_call(
        operation="entity_extraction",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cached=True
    )

    # Cached calls should have zero cost
    assert cost == 0.0

    # Verify database entry
    doc = await test_db.api_costs.find_one({"cached": True})
    assert doc is not None
    assert doc["cost"] == 0.0
    assert doc["cached"] is True


@pytest.mark.asyncio
async def test_cost_tracker_different_models(test_db):
    """Test that different models are priced correctly."""
    tracker = CostTracker(test_db)

    # Haiku call
    haiku_cost = await tracker.track_call(
        operation="test",
        model="claude-haiku-4-5-20251001",
        input_tokens=1000,
        output_tokens=1000,
        cached=False
    )

    # Sonnet call (more expensive)
    sonnet_cost = await tracker.track_call(
        operation="test",
        model="claude-sonnet-4-5-20250929",
        input_tokens=1000,
        output_tokens=1000,
        cached=False
    )

    # Opus call (most expensive)
    opus_cost = await tracker.track_call(
        operation="test",
        model="claude-opus-4-6",
        input_tokens=1000,
        output_tokens=1000,
        cached=False
    )

    # Verify pricing hierarchy
    assert haiku_cost < sonnet_cost < opus_cost


@pytest.mark.asyncio
async def test_optimized_llm_no_manual_tracking(test_db):
    """Test that OptimizedAnthropicLLM does NOT manually track (gateway handles it)."""
    api_key = "test-key"
    llm = OptimizedAnthropicLLM(test_db, api_key)

    # Mock the HTTP call
    mock_response = {
        "content": [{"text": '{"entities": [{"name": "Bitcoin", "type": "cryptocurrency"}]}'}],
        "usage": {
            "input_tokens": 200,
            "output_tokens": 100
        }
    }

    with patch.object(llm, '_make_api_call', return_value={
        "content": '{"entities": [{"name": "Bitcoin", "type": "cryptocurrency"}]}',
        "input_tokens": 200,
        "output_tokens": 100
    }):
        # Call entity extraction
        result = await llm.extract_entities_batch([
            {"title": "Bitcoin News", "text": "Bitcoin is up 10%"}
        ])

        # Give async tracking task time to complete
        await asyncio.sleep(0.1)

        # Verify NO tracking in api_costs (gateway handles tracking instead)
        doc = await test_db.api_costs.find_one({"operation": "entity_extraction"})
        assert doc is None, "OptimizedAnthropicLLM should NOT manually track to api_costs"

        # Verify result was still returned correctly
        assert len(result) == 1
        assert result[0]["entities"][0]["name"] == "Bitcoin"


@pytest.mark.asyncio
async def test_optimized_llm_no_manual_tracking_narrative(test_db):
    """Test that OptimizedAnthropicLLM does NOT manually track narrative extraction."""
    api_key = "test-key"
    llm = OptimizedAnthropicLLM(test_db, api_key)

    with patch.object(llm, '_make_api_call', return_value={
        "content": '{"nucleus_entity": "Bitcoin", "actors": ["Bitcoin"], "tensions": []}',
        "input_tokens": 250,
        "output_tokens": 150
    }):
        # Call narrative extraction
        result = await llm.extract_narrative_elements({
            "title": "Bitcoin News",
            "text": "Bitcoin is trending"
        })

        # Give async tracking task time to complete
        await asyncio.sleep(0.1)

        # Verify NO tracking in api_costs (gateway handles tracking instead)
        doc = await test_db.api_costs.find_one({"operation": "narrative_extraction"})
        assert doc is None, "OptimizedAnthropicLLM should NOT manually track to api_costs"

        # Verify result was still returned correctly
        assert result["nucleus_entity"] == "Bitcoin"
        assert "Bitcoin" in result["actors"]


@pytest.mark.asyncio
async def test_optimized_llm_no_manual_tracking_summary(test_db):
    """Test that OptimizedAnthropicLLM does NOT manually track narrative summary."""
    api_key = "test-key"
    llm = OptimizedAnthropicLLM(test_db, api_key)

    with patch.object(llm, '_make_api_call', return_value={
        "content": "Bitcoin is trending due to institutional interest.",
        "input_tokens": 300,
        "output_tokens": 200
    }):
        # Call narrative summary
        result = await llm.generate_narrative_summary([
            {"title": "Bitcoin News", "text": "Bitcoin is up"},
            {"title": "More Bitcoin News", "text": "Bitcoin continues up"}
        ])

        # Give async tracking task time to complete
        await asyncio.sleep(0.1)

        # Verify NO tracking in api_costs (gateway handles tracking instead)
        doc = await test_db.api_costs.find_one({"operation": "narrative_summary"})
        assert doc is None, "OptimizedAnthropicLLM should NOT manually track to api_costs"

        # Verify result was still returned correctly
        assert "Bitcoin" in result
        assert "trending" in result


@pytest.mark.asyncio
async def test_cost_tracker_multiple_operations(test_db):
    """Test that multiple operation types are tracked separately."""
    tracker = CostTracker(test_db)

    # Track different operations
    await tracker.track_call(
        operation="entity_extraction",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cached=False
    )

    await tracker.track_call(
        operation="briefing_generation",
        model="claude-sonnet-4-5-20250929",
        input_tokens=2000,
        output_tokens=1000,
        cached=False
    )

    await tracker.track_call(
        operation="narrative_summary",
        model="claude-sonnet-4-5-20250929",
        input_tokens=500,
        output_tokens=300,
        cached=False
    )

    # Verify all operations were tracked
    entity_doc = await test_db.api_costs.find_one({"operation": "entity_extraction"})
    briefing_doc = await test_db.api_costs.find_one({"operation": "briefing_generation"})
    narrative_doc = await test_db.api_costs.find_one({"operation": "narrative_summary"})

    assert entity_doc is not None
    assert briefing_doc is not None
    assert narrative_doc is not None

    # Verify models
    assert entity_doc["model"] == "claude-haiku-4-5-20251001"
    assert briefing_doc["model"] == "claude-sonnet-4-5-20250929"
    assert narrative_doc["model"] == "claude-sonnet-4-5-20250929"


@pytest.mark.asyncio
async def test_cost_tracker_monthly_cost(test_db):
    """Test monthly cost aggregation (from llm_traces - BUG-079)."""
    tracker = CostTracker(test_db)

    # Insert trace records for multiple calls
    for i in range(5):
        input_tokens = 100 + i * 10
        output_tokens = 50 + i * 5
        cost = tracker.calculate_cost("claude-haiku-4-5-20251001", input_tokens, output_tokens)
        await _insert_trace_record(test_db, "entity_extraction", "claude-haiku-4-5-20251001", input_tokens, output_tokens, cost)

    # Get monthly cost
    total_cost = await tracker.get_monthly_cost()

    assert total_cost > 0
    assert total_cost < 0.01  # Should be very cheap


@pytest.mark.asyncio
async def test_cost_tracker_timestamp_recorded(test_db):
    """Test that timestamps are properly recorded."""
    tracker = CostTracker(test_db)

    before = datetime.now(timezone.utc)

    await tracker.track_call(
        operation="test_operation",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cached=False
    )

    after = datetime.now(timezone.utc)

    # Verify timestamp
    doc = await test_db.api_costs.find_one({"operation": "test_operation"})
    assert doc is not None
    # MongoDB may store with slight precision differences, so use a 1-second window
    assert doc["timestamp"].replace(microsecond=0) >= before.replace(microsecond=0)
    assert doc["timestamp"].replace(microsecond=0) <= after.replace(microsecond=0)
