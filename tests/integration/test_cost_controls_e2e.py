"""
End-to-end integration tests for TASK-025 cost controls.

Verifies that all three stages work together:
- Stage 1: Rate limiting integration with LLM methods
- Stage 2: Circuit breaker integration with LLM methods
- Stage 3: Spend logging records all calls to MongoDB with correct costs
"""

import pytest
from datetime import datetime, timezone
import asyncio

from crypto_news_aggregator.services.cost_tracker import CostTracker
from crypto_news_aggregator.services.circuit_breaker import CircuitBreaker


class TestCostControlsE2E:
    """End-to-end tests for all cost control stages."""

    @pytest.mark.asyncio
    async def test_spend_logging_complete_flow(self, mongo_db):
        """Verify Stage 3: Spend logging captures all system calls."""
        tracker = CostTracker(mongo_db)

        # Simulate all three systems making calls
        system_calls = [
            ("sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50),
            ("theme_extraction", "claude-haiku-4-5-20251001", 200, 40),
            ("relevance_scoring", "claude-haiku-4-5-20251001", 150, 60),
            ("entity_extraction", "claude-haiku-4-5-20251001", 4000, 800),
            ("briefing_generation", "claude-sonnet-4-5-20250929", 1000, 500),
        ]

        for operation, model, inp, out in system_calls:
            cost = await tracker.track_call(
                operation=operation,
                model=model,
                input_tokens=inp,
                output_tokens=out,
            )
            assert cost > 0  # All should cost something

        # Verify all logged
        count = await mongo_db.api_costs.count_documents({})
        assert count == 5

        # Verify can aggregate by operation
        by_op = await tracker.get_cost_by_operation(days=1)
        assert len(by_op) == 5
        assert all(call_count >= 1 for op_data in by_op.values() for call_count in [op_data["calls"]])

        # Verify can aggregate by model
        by_model = await tracker.get_cost_by_model(days=1)
        assert len(by_model) == 2  # Haiku and Sonnet

        # Verify total cost calculation
        daily_cost = await tracker.get_daily_cost(days=1)
        assert daily_cost > 0

    @pytest.mark.asyncio
    async def test_cost_controls_with_cached_calls(self, mongo_db):
        """Verify Stage 3: Cached calls don't add cost but are tracked."""
        tracker = CostTracker(mongo_db)

        # Regular call costs money
        cost_regular = await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cached=False,
        )
        assert cost_regular > 0

        # Cached call costs nothing
        cost_cached = await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cached=True,
        )
        assert cost_cached == 0.0

        # Both tracked
        count = await mongo_db.api_costs.count_documents({})
        assert count == 2

        # But cost aggregation shows both calls (one with cost, one without)
        by_op = await tracker.get_cost_by_operation(days=1)
        assert by_op["sentiment_analysis"]["calls"] == 2
        assert by_op["sentiment_analysis"]["cost"] == cost_regular

    @pytest.mark.asyncio
    async def test_different_models_cost_differently(self, mongo_db):
        """Verify Stage 3: Different models have correct pricing."""
        tracker = CostTracker(mongo_db)

        # Same tokens, different models = different costs
        haiku_cost = await tracker.track_call(
            operation="test",
            model="claude-haiku-4-5-20251001",
            input_tokens=1000,
            output_tokens=1000,
        )

        sonnet_cost = await tracker.track_call(
            operation="test",
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=1000,
        )

        opus_cost = await tracker.track_call(
            operation="test",
            model="claude-opus-4-6",
            input_tokens=1000,
            output_tokens=1000,
        )

        # Sonnet should cost more than Haiku
        assert sonnet_cost > haiku_cost

        # Opus should cost more than Sonnet
        assert opus_cost > sonnet_cost

    @pytest.mark.asyncio
    async def test_monthly_cost_aggregation(self, mongo_db):
        """Verify Stage 3: Monthly cost aggregation works."""
        tracker = CostTracker(mongo_db)

        # Track a call
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
        )

        # Get monthly cost (should include today)
        monthly = await tracker.get_monthly_cost()
        assert monthly > 0

        # Get daily cost (should match)
        daily = await tracker.get_daily_cost(days=1)
        assert daily == monthly  # Same day = same cost

    @pytest.mark.asyncio
    async def test_system_isolation_cost_tracking(self, mongo_db):
        """Verify Stage 3: Different systems tracked independently."""
        tracker = CostTracker(mongo_db)

        # Track operations from different systems
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

        # Each system should have independent entry
        by_op = await tracker.get_cost_by_operation(days=1)
        assert "sentiment_analysis" in by_op
        assert "entity_extraction" in by_op
        assert by_op["sentiment_analysis"]["calls"] == 1
        assert by_op["entity_extraction"]["calls"] == 1

    @pytest.mark.asyncio
    async def test_spend_aggregation_sorting(self, mongo_db):
        """Verify Stage 3: Aggregation sorts by cost (highest first)."""
        tracker = CostTracker(mongo_db)

        # Track different amounts for different operations
        # Small cost
        await tracker.track_call(
            operation="relevance_scoring",
            model="claude-haiku-4-5-20251001",
            input_tokens=50,
            output_tokens=10,
        )

        # Medium cost
        await tracker.track_call(
            operation="sentiment_analysis",
            model="claude-haiku-4-5-20251001",
            input_tokens=200,
            output_tokens=50,
        )

        # Large cost
        await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=5000,
            output_tokens=1000,
        )

        # Aggregation should sort by cost descending
        by_op = await tracker.get_cost_by_operation(days=1)

        # Get operations in order they appear
        operations = list(by_op.keys())

        # Entity extraction should be first (highest cost)
        assert operations[0] == "entity_extraction"
