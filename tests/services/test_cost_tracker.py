"""
Tests for cost tracking service.
"""

import pytest
import time
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from crypto_news_aggregator.services.cost_tracker import CostTracker, _budget_cache, check_llm_budget
from unittest.mock import patch, AsyncMock


@pytest.fixture
async def db():
    """Create test database connection."""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_cost_tracking
    yield db
    # Cleanup (both api_costs and llm_traces for test compatibility)
    await db.api_costs.delete_many({})
    await db.llm_traces.delete_many({})
    client.close()


@pytest.fixture
async def tracker(db):
    """Create cost tracker instance."""
    return CostTracker(db)


class TestCostCalculation:
    """Test cost calculation logic."""

    def test_haiku_pricing(self, tracker):
        """Test Haiku model pricing."""
        cost = tracker.calculate_cost(
            "claude-haiku-4-5-20251001",
            input_tokens=1000,
            output_tokens=1000
        )
        # 1K input @ $1.00/1M = $0.001
        # 1K output @ $5.00/1M = $0.005
        # Total = $0.006
        assert cost == pytest.approx(0.006, abs=0.0001)

    def test_sonnet_pricing(self, tracker):
        """Test Sonnet model pricing."""
        cost = tracker.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=1000
        )
        # 1K input @ $3.00/1M = $0.003
        # 1K output @ $15.00/1M = $0.015
        # Total = $0.018
        assert cost == pytest.approx(0.018, abs=0.0001)

    def test_opus_pricing(self, tracker):
        """Test Opus model pricing."""
        cost = tracker.calculate_cost(
            "claude-opus-4-6",
            input_tokens=1000,
            output_tokens=1000
        )
        # 1K input @ $15.00/1M = $0.015
        # 1K output @ $75.00/1M = $0.075
        # Total = $0.090
        assert cost == pytest.approx(0.090, abs=0.0001)

    def test_unknown_model_defaults_to_haiku(self, tracker):
        """Unknown models default to Haiku pricing."""
        cost = tracker.calculate_cost(
            "unknown-model",
            input_tokens=1000,
            output_tokens=1000
        )
        # Should use Haiku pricing: $1.00 input + $5.00 output = $0.006
        assert cost == pytest.approx(0.006, abs=0.0001)


@pytest.mark.asyncio
class TestCostTracking:
    """Test cost tracking to database."""

    async def test_track_call_writes_to_db(self, tracker, db):
        """Test that track_call writes to database."""
        cost = await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=200,
            cached=False
        )

        # Verify cost calculation
        assert cost > 0

        # Verify database write
        doc = await db.api_costs.find_one({"operation": "entity_extraction"})
        assert doc is not None
        assert doc["model"] == "claude-haiku-4-5-20251001"
        assert doc["input_tokens"] == 500
        assert doc["output_tokens"] == 200
        assert doc["cost"] == pytest.approx(cost, abs=0.0001)
        assert doc["cached"] is False

    async def test_cache_hit_has_zero_cost(self, tracker, db):
        """Test that cache hits have zero cost."""
        cost = await tracker.track_call(
            operation="entity_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=200,
            cached=True,
            cache_key="test_cache_key"
        )

        # Cache hits are free
        assert cost == 0.0

        # Verify database write
        doc = await db.api_costs.find_one({"cache_key": "test_cache_key"})
        assert doc is not None
        assert doc["cost"] == 0.0
        assert doc["cached"] is True

    async def test_get_daily_cost(self, tracker, db):
        """Test daily cost aggregation from llm_traces (BUG-079: single source of truth)."""
        # Insert test data directly into llm_traces
        # (This is where get_daily_cost() now queries from after BUG-079)
        now = datetime.now(timezone.utc)
        for _ in range(2):
            await db.llm_traces.insert_one({
                "timestamp": now,
                "operation": "test_op",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 1000,
                "output_tokens": 1000,
                "cost": 0.006,
            })

        daily_cost = await tracker.get_daily_cost(days=1)

        # Should be 2 × $0.006 = $0.012
        assert daily_cost == pytest.approx(0.012, abs=0.0001)

    async def test_get_monthly_cost(self, tracker, db):
        """Test monthly cost aggregation from llm_traces (BUG-079: single source of truth)."""
        # Insert test data directly into llm_traces
        now = datetime.now(timezone.utc)
        await db.llm_traces.insert_one({
            "timestamp": now,
            "operation": "test_op",
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 1000,
            "output_tokens": 1000,
            "cost": 0.006,
        })

        monthly_cost = await tracker.get_monthly_cost()

        # Should be $0.006
        assert monthly_cost == pytest.approx(0.006, abs=0.0001)


class TestCriticalOperations:
    """Test critical operations classification."""

    def test_briefing_operations_are_critical(self, tracker):
        """Verify all briefing operations are marked as critical (BUG-065 regression)."""
        critical_ops = [
            "briefing_generation",
            "briefing_generate",
            "briefing_critique",
            "briefing_refine",
        ]
        for op in critical_ops:
            assert tracker.is_critical_operation(op), f"{op} should be critical"

    def test_entity_extraction_is_critical(self, tracker):
        """Entity extraction is critical for pipeline continuity."""
        assert tracker.is_critical_operation("entity_extraction")

    def test_non_critical_operations(self, tracker):
        """Verify non-critical operations are not marked as critical."""
        non_critical_ops = [
            "health_check",
            "theme_extraction",
            "sentiment_analysis",
            "relevance_scoring",
            "article_enrichment_batch",
            "narrative_enrichment",
        ]
        for op in non_critical_ops:
            assert not tracker.is_critical_operation(op), f"{op} should not be critical"


@pytest.mark.asyncio
class TestMonthlyBudgetGuard:
    """Test FEATURE-013: Monthly cumulative API spend guard."""

    async def test_monthly_hard_limit_blocks_all_operations(self, tracker, db):
        """Monthly hard limit reached: all operations blocked including critical ones."""
        # Insert cost data: $10.01 (exceeds the test limit of 100.00 * 1.0)
        # Use a very high value to ensure hard limit is hit
        now = datetime.now(timezone.utc)
        for _ in range(2):
            await db.llm_traces.insert_one({
                "timestamp": now,
                "operation": "test_op",
                "model": "claude-opus-4-6",
                "input_tokens": 500000,
                "output_tokens": 500000,
                "cost": 52.50,  # $52.50 * 2 = $105.00 (exceeds $100 default test limit)
            })

        # Refresh cache - with the test settings, ANTHROPIC_MONTHLY_API_LIMIT=100.00
        await tracker.refresh_budget_cache()

        # Verify monthly_status is hard_limit
        assert _budget_cache["monthly_status"] == "hard_limit"
        assert _budget_cache["monthly_cost"] >= 100.00

        # Check that all operations are blocked
        allowed_critical, reason_critical = check_llm_budget("briefing_generation")
        assert allowed_critical is False
        assert reason_critical == "monthly_hard_limit"

        allowed_noncrit, reason_noncrit = check_llm_budget("theme_extraction")
        assert allowed_noncrit is False
        assert reason_noncrit == "monthly_hard_limit"

    async def test_monthly_soft_limit_detected(self, tracker, db):
        """Test that monthly soft limit (75%) status is detected correctly."""
        now = datetime.now(timezone.utc)
        # Insert many small records totaling $75.50 (75.5% of $100)
        for _ in range(77):
            await db.llm_traces.insert_one({
                "timestamp": now,
                "operation": "test_op",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 10000,
                "output_tokens": 100000,
                "cost": 0.98,
            })

        await tracker.refresh_budget_cache()

        # Monthly should be degraded at 75.5%
        assert _budget_cache["monthly_status"] == "degraded"
        assert _budget_cache["monthly_cost"] >= 75.00

    async def test_monthly_alert_month_tracking(self, tracker, db):
        """Test that monthly alert month is tracked for idempotency."""
        now = datetime.now(timezone.utc)
        # Insert enough for 75%+ monthly
        for _ in range(100):
            await db.llm_traces.insert_one({
                "timestamp": now,
                "operation": "test_op",
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 1000,
                "output_tokens": 10000,
                "cost": 0.76,
            })

        await tracker.refresh_budget_cache()

        # Monthly should be degraded
        assert _budget_cache["monthly_status"] == "degraded"

        # Alert month should be tracked
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        assert _budget_cache["monthly_alert_month"] == current_month

    async def test_daily_enforcement_unchanged_with_monthly_guard(self, tracker, db):
        """Daily soft/hard limits work independently with monthly guard present."""
        # Test 1: Daily soft limit hit
        now = datetime.now(timezone.utc)
        await db.llm_traces.insert_one({
            "timestamp": now,
            "operation": "test_op",
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 10000,
            "output_tokens": 400000,
            "cost": 3.50,  # Exceeds daily soft ($3.00) but under hard ($15.00)
        })

        await tracker.refresh_budget_cache()

        # Daily should be degraded
        assert _budget_cache["status"] == "degraded"
        # Monthly should be ok (well below $100)
        assert _budget_cache["monthly_status"] == "ok"

        # Critical operations allowed in daily degraded
        allowed_critical, reason_critical = check_llm_budget("briefing_generation")
        assert allowed_critical is True
        assert reason_critical == "degraded"

        # Non-critical blocked (daily soft limit)
        allowed_noncrit, reason_noncrit = check_llm_budget("theme_extraction")
        assert allowed_noncrit is False
        assert reason_noncrit == "soft_limit"

        # Test 2: Daily hard limit hit
        await db.llm_traces.delete_many({})
        await db.llm_traces.insert_one({
            "timestamp": now,
            "operation": "test_op",
            "model": "claude-opus-4-6",
            "input_tokens": 500000,
            "output_tokens": 500000,
            "cost": 15.50,  # Exceeds daily hard ($15.00)
        })

        await tracker.refresh_budget_cache()

        # Daily hard limit hit
        assert _budget_cache["status"] == "hard_limit"
        # Monthly still ok
        assert _budget_cache["monthly_status"] == "ok"

        # All operations blocked (daily hard)
        allowed_critical, reason_critical = check_llm_budget("briefing_generation")
        assert allowed_critical is False
        assert reason_critical == "hard_limit"

        allowed_noncrit, reason_noncrit = check_llm_budget("theme_extraction")
        assert allowed_noncrit is False
        assert reason_noncrit == "hard_limit"

    async def test_monthly_overrides_daily_hard_limit(self, tracker, db):
        """Monthly hard limit overrides everything, including daily status."""
        now = datetime.now(timezone.utc)
        # Insert $105 to exceed monthly hard limit (100.00)
        for _ in range(2):
            await db.llm_traces.insert_one({
                "timestamp": now,
                "operation": "test_op",
                "model": "claude-opus-4-6",
                "input_tokens": 500000,
                "output_tokens": 500000,
                "cost": 52.50,
            })

        await tracker.refresh_budget_cache()

        # Both should be hard limit
        assert _budget_cache["status"] in ["ok", "degraded", "hard_limit"]  # Daily doesn't matter
        assert _budget_cache["monthly_status"] == "hard_limit"

        # Monthly hard limit blocks everything
        allowed, reason = check_llm_budget("briefing_generation")
        assert allowed is False
        assert reason == "monthly_hard_limit"
