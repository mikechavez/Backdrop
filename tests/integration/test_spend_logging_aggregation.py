"""
Integration tests for spend logging aggregation (TASK-025 Stage 3).

Tests verify that:
1. All LLM API calls are logged to MongoDB with complete cost data
2. Spend can be aggregated by operation type
3. Spend can be aggregated by model
4. Daily/monthly cost queries work correctly
"""

import pytest
from datetime import datetime, timezone, timedelta

from crypto_news_aggregator.services.cost_tracker import CostTracker


class TestSpendLoggingAggregation:
    """Tests for spend logging and aggregation (Stage 3)."""

    @pytest.mark.asyncio
    async def test_cost_tracker_logs_to_database(self, mongo_db):
        """Verify CostTracker writes complete records to MongoDB."""
        tracker = CostTracker(mongo_db)

        # Track a call
        cost = await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )

        # Verify cost calculated correctly
        # Input: 100 tokens * $1.00/1M = $0.0001
        # Output: 50 tokens * $5.00/1M = $0.00025
        # Total: $0.00035
        assert cost == pytest.approx(0.00035, rel=1e-6)

        # Verify document was written
        doc = await mongo_db.api_costs.find_one({"operation": "sentiment_analysis"})
        assert doc is not None
        assert doc["operation"] == "sentiment_analysis"
        assert doc["model"] == "claude-haiku-4-5-20251001"
        assert doc["input_tokens"] == 100
        assert doc["output_tokens"] == 50
        assert doc["cost"] == pytest.approx(0.00035, rel=1e-6)
        assert doc["cached"] is False
        assert "timestamp" in doc

    @pytest.mark.asyncio
    async def test_entity_extraction_cost_tracking(self, mongo_db):
        """Verify entity extraction costs are logged (Stage 3 addition)."""
        tracker = CostTracker(mongo_db)

        # Entity extraction typically uses more tokens
        cost = await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=4000,  # Batch of articles
            output_tokens=800,
        )

        # Input: 4000 tokens * $1.00/1M = $0.004
        # Output: 800 tokens * $5.00/1M = $0.004
        # Total: $0.008
        assert cost == pytest.approx(0.008, rel=1e-6)

        # Verify write
        doc = await mongo_db.api_costs.find_one({"operation": "entity_extraction"})
        assert doc is not None
        assert doc["operation"] == "entity_extraction"
        assert doc["cost"] == pytest.approx(0.008, rel=1e-6)

    @pytest.mark.asyncio
    async def test_get_cost_by_operation(self, mongo_db):
        """Verify cost aggregation by operation type."""
        tracker = CostTracker(mongo_db)

        # Track multiple operations
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=4000,
            output_tokens=800,
        )
        await tracker.track_call(
            operation="theme_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=200,
            output_tokens=40,
        )

        result = await tracker.get_cost_by_operation(days=1)

        # Verify structure
        assert "sentiment_analysis" in result
        assert "entity_extraction" in result
        assert "theme_extraction" in result

        # Verify sentiment analysis has 2 calls
        # Each call: (100 * $1/1M) + (50 * $5/1M) = $0.00035
        # Two calls: $0.00070
        assert result["sentiment_analysis"]["calls"] == 2
        assert result["sentiment_analysis"]["cost"] == pytest.approx(0.0007, rel=1e-6)

        # Verify entity extraction
        assert result["entity_extraction"]["calls"] == 1
        assert result["entity_extraction"]["cost"] == pytest.approx(0.008, rel=1e-6)

        # Verify theme extraction
        # 200 input * $1/1M + 40 output * $5/1M = $0.0002 + $0.0002 = $0.0004
        assert result["theme_extraction"]["calls"] == 1
        assert result["theme_extraction"]["cost"] == pytest.approx(0.0004, rel=1e-6)

    @pytest.mark.asyncio
    async def test_get_cost_by_model(self, mongo_db):
        """Verify cost aggregation by model."""
        tracker = CostTracker(mongo_db)

        # Track with different models
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        await tracker.track_call(
            operation="briefing_generation",
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )
        await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=4000,
            output_tokens=800,
        )

        result = await tracker.get_cost_by_model(days=1)

        # Verify structure
        assert "claude-haiku-4-5-20251001" in result
        assert "claude-sonnet-4-5-20250929" in result

        # Haiku: $0.00035 (sentiment) + $0.008 (entity) = $0.00835
        assert result["claude-haiku-4-5-20251001"]["calls"] == 2
        assert result["claude-haiku-4-5-20251001"]["cost"] == pytest.approx(0.00835, rel=1e-6)

        # Sonnet: Input 1000 * $3.0/1M = $0.003, Output 500 * $15.0/1M = $0.0075 = $0.0105
        assert result["claude-sonnet-4-5-20250929"]["calls"] == 1
        assert result["claude-sonnet-4-5-20250929"]["cost"] == pytest.approx(0.0105, rel=1e-6)

    @pytest.mark.asyncio
    async def test_multiple_systems_cost_tracking(self, mongo_db):
        """Verify costs from multiple systems are tracked independently."""
        tracker = CostTracker(mongo_db)

        # Track calls from different systems
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=100,
        )

        await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=2000,
            output_tokens=400,
        )

        await tracker.track_call(
            operation="briefing_generation",
            model="claude-sonnet-4-5-20250929",
            input_tokens=3000,
            output_tokens=800,
        )

        # Count documents
        count = await mongo_db.api_costs.count_documents({})
        assert count == 3

        # Verify each operation is logged
        ops = await mongo_db.api_costs.find({}).distinct("operation")
        assert set(ops) == {"sentiment_analysis", "entity_extraction", "briefing_generation"}

    @pytest.mark.asyncio
    async def test_cached_call_zero_cost(self, mongo_db):
        """Verify cached calls have zero cost."""
        tracker = CostTracker(mongo_db)

        cost = await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cached=True,
        )

        # Cache hit should cost $0
        assert cost == 0.0

        # Verify cached flag in document
        doc = await mongo_db.api_costs.find_one({"cached": True})
        assert doc is not None
        assert doc["cached"] is True
        assert doc["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_get_daily_cost_aggregation(self, mongo_db):
        """Verify daily cost aggregation works correctly."""
        tracker = CostTracker(mongo_db)

        # Track multiple calls
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )
        await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=4000,
            output_tokens=800,
        )

        daily_cost = await tracker.get_daily_cost(days=1)

        # $0.00035 + $0.008 = $0.00835
        assert daily_cost == pytest.approx(0.00835, rel=1e-6)

    @pytest.mark.asyncio
    async def test_get_monthly_cost_aggregation(self, mongo_db):
        """Verify monthly cost aggregation works correctly."""
        tracker = CostTracker(mongo_db)

        # Track a call
        await tracker.track_call(
            operation="briefing_generation",
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
        )

        monthly_cost = await tracker.get_monthly_cost()

        # Sonnet: $0.003 + $0.0075 = $0.0105
        assert monthly_cost == pytest.approx(0.0105, rel=1e-6)

    @pytest.mark.asyncio
    async def test_empty_cost_aggregation(self, mongo_db):
        """Verify empty aggregation returns zero/empty results."""
        # Create fresh tracker with no data
        tracker = CostTracker(mongo_db)

        # Clear collection
        await mongo_db.api_costs.delete_many({})

        result_by_op = await tracker.get_cost_by_operation(days=1)
        result_by_model = await tracker.get_cost_by_model(days=1)
        daily = await tracker.get_daily_cost(days=1)
        monthly = await tracker.get_monthly_cost()

        assert result_by_op == {}
        assert result_by_model == {}
        assert daily == 0.0
        assert monthly == 0.0
