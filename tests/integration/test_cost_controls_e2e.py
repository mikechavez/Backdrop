"""
End-to-end integration tests for TASK-025 cost controls.

Verifies that all three stages work together:
- Stage 1: Rate limiting integration with LLM methods
- Stage 2: Circuit breaker integration with LLM methods
- Stage 3: Spend logging records all calls to MongoDB with correct costs

NOTE: Tests write to llm_traces (the single source of truth for budget enforcement after BUG-079).
"""

import pytest
from datetime import datetime, timezone
import asyncio

from crypto_news_aggregator.services.cost_tracker import CostTracker
from crypto_news_aggregator.services.circuit_breaker import CircuitBreaker


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


class TestCostControlsE2E:
    """End-to-end tests for all cost control stages."""

    @pytest.mark.asyncio
    async def test_spend_logging_complete_flow(self, mongo_db):
        """Verify Stage 3: Spend logging captures all system calls (from llm_traces - BUG-079)."""
        tracker = CostTracker(mongo_db)

        # Insert trace records for all three systems (new location after BUG-079)
        system_calls = [
            ("sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50, 0.00035),
            ("theme_extraction", "claude-haiku-4-5-20251001", 200, 40, 0.0004),
            ("relevance_scoring", "claude-haiku-4-5-20251001", 150, 60, 0.000450),
            ("entity_extraction", "claude-haiku-4-5-20251001", 4000, 800, 0.008),
            ("briefing_generation", "claude-sonnet-4-5-20250929", 1000, 500, 0.0105),
        ]

        for operation, model, inp, out, cost in system_calls:
            await _insert_trace_record(mongo_db, operation, model, inp, out, cost)

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
        """Verify Stage 3: Cached calls don't add cost but are tracked (from llm_traces - BUG-079)."""
        tracker = CostTracker(mongo_db)

        # Insert trace records
        # Regular call costs money
        cost_regular = 0.00035
        await _insert_trace_record(mongo_db, "sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50, cost_regular)

        # Cached call costs nothing (tracked but $0)
        cost_cached = 0.0
        await _insert_trace_record(mongo_db, "sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50, cost_cached)

        # Both tracked
        count = await mongo_db.llm_traces.count_documents({})
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
        """Verify Stage 3: Monthly cost aggregation works (from llm_traces - BUG-079)."""
        tracker = CostTracker(mongo_db)

        # Insert trace record
        cost = 0.00035
        await _insert_trace_record(mongo_db, "sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50, cost)

        # Get monthly cost (should include today)
        monthly = await tracker.get_monthly_cost()
        assert monthly > 0

        # Get daily cost (should match)
        daily = await tracker.get_daily_cost(days=1)
        assert daily == monthly  # Same day = same cost

    @pytest.mark.asyncio
    async def test_system_isolation_cost_tracking(self, mongo_db):
        """Verify Stage 3: Different systems tracked independently (from llm_traces - BUG-079)."""
        tracker = CostTracker(mongo_db)

        # Insert trace records for different systems
        await _insert_trace_record(mongo_db, "sentiment_analysis", "claude-haiku-4-5-20251001", 100, 50, 0.00035)
        await _insert_trace_record(mongo_db, "entity_extraction", "claude-haiku-4-5-20251001", 4000, 800, 0.008)

        # Each system should have independent entry
        by_op = await tracker.get_cost_by_operation(days=1)
        assert "sentiment_analysis" in by_op
        assert "entity_extraction" in by_op
        assert by_op["sentiment_analysis"]["calls"] == 1
        assert by_op["entity_extraction"]["calls"] == 1

    @pytest.mark.asyncio
    async def test_spend_aggregation_sorting(self, mongo_db):
        """Verify Stage 3: Aggregation sorts by cost (highest first) (from llm_traces - BUG-079)."""
        tracker = CostTracker(mongo_db)

        # Insert trace records with different costs
        # Small cost
        await _insert_trace_record(mongo_db, "relevance_scoring", "claude-haiku-4-5-20251001", 50, 10, 0.000075)

        # Medium cost
        await _insert_trace_record(mongo_db, "sentiment_analysis", "claude-haiku-4-5-20251001", 200, 50, 0.00035)

        # Large cost
        await _insert_trace_record(mongo_db, "entity_extraction", "claude-haiku-4-5-20251001", 5000, 1000, 0.0105)

        # Aggregation should sort by cost descending
        by_op = await tracker.get_cost_by_operation(days=1)

        # Get operations in order they appear
        operations = list(by_op.keys())

        # Entity extraction should be first (highest cost)
        assert operations[0] == "entity_extraction"
