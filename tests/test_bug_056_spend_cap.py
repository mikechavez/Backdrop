"""
Tests for BUG-056: LLM Spend Cap Enforcement.

Tests budget caching, soft/hard limits, critical operation classification,
and backlog throttle behavior.
"""

import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from motor.motor_asyncio import AsyncIOMotorDatabase

from crypto_news_aggregator.services.cost_tracker import (
    CostTracker,
    check_llm_budget,
    refresh_budget_if_stale,
    get_cost_tracker,
    _budget_cache,
)
from crypto_news_aggregator.core.config import get_settings
from crypto_news_aggregator.llm.anthropic import AnthropicProvider


class TestBudgetCacheState:
    """Test budget cache initialization and state transitions."""

    def test_budget_cache_initial_state(self):
        """Budget cache should start empty/unchecked."""
        # Reset cache to initial state
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["status"] = "ok"
        _budget_cache["last_checked"] = 0.0

        assert _budget_cache["status"] == "ok"
        assert _budget_cache["last_checked"] == 0.0
        assert _budget_cache["ttl"] == 30

    def test_budget_cache_ttl(self):
        """Budget cache should have 30s TTL."""
        assert _budget_cache["ttl"] == 30


class TestCriticalOperationClassification:
    """Test classification of critical vs non-critical operations."""

    def setup_method(self):
        """Create tracker instance for each test."""
        mock_db = MagicMock()
        self.tracker = CostTracker(mock_db)

    def test_briefing_generation_is_critical(self):
        """briefing_generation should be classified as critical."""
        assert self.tracker.is_critical_operation("briefing_generation") is True

    def test_briefing_generate_is_critical(self):
        """briefing_generate (task name variant) should be classified as critical."""
        assert self.tracker.is_critical_operation("briefing_generate") is True

    def test_entity_extraction_is_critical(self):
        """entity_extraction should be classified as critical."""
        assert self.tracker.is_critical_operation("entity_extraction") is True

    def test_theme_extraction_is_noncritical(self):
        """theme_extraction should be non-critical."""
        assert self.tracker.is_critical_operation("theme_extraction") is False

    def test_sentiment_analysis_is_noncritical(self):
        """sentiment_analysis should be non-critical."""
        assert self.tracker.is_critical_operation("sentiment_analysis") is False

    def test_relevance_scoring_is_noncritical(self):
        """relevance_scoring should be non-critical."""
        assert self.tracker.is_critical_operation("relevance_scoring") is False

    def test_article_enrichment_is_noncritical(self):
        """article_enrichment_batch should be non-critical."""
        assert self.tracker.is_critical_operation("article_enrichment_batch") is False


class TestCheckLLMBudget:
    """Test the synchronous budget check function."""

    def setup_method(self):
        """Reset cache before each test."""
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = time.time()

    def test_ok_status_allows_any_operation(self):
        """When status is 'ok', any operation should be allowed."""
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.10
        _budget_cache["last_checked"] = time.time()

        # Critical operation
        allowed, reason = check_llm_budget("briefing_generation")
        assert allowed is True
        assert reason == "ok"

        # Non-critical operation
        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is True
        assert reason == "ok"

    def test_soft_limit_allows_critical_operations(self):
        """Soft limit should allow critical operations with 'degraded' reason."""
        _budget_cache["status"] = "degraded"
        _budget_cache["daily_cost"] = 0.25
        _budget_cache["last_checked"] = time.time()

        allowed, reason = check_llm_budget("briefing_generation")
        assert allowed is True
        assert reason == "degraded"

        allowed, reason = check_llm_budget("entity_extraction")
        assert allowed is True
        assert reason == "degraded"

    def test_soft_limit_blocks_noncritical_operations(self):
        """Soft limit should block non-critical operations."""
        _budget_cache["status"] = "degraded"
        _budget_cache["daily_cost"] = 0.25
        _budget_cache["last_checked"] = time.time()

        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is False
        assert reason == "soft_limit"

        allowed, reason = check_llm_budget("theme_extraction")
        assert allowed is False
        assert reason == "soft_limit"

        allowed, reason = check_llm_budget("article_enrichment_batch")
        assert allowed is False
        assert reason == "soft_limit"

    def test_hard_limit_blocks_all_operations(self):
        """Hard limit should block both critical and non-critical operations."""
        _budget_cache["status"] = "hard_limit"
        _budget_cache["daily_cost"] = 0.33
        _budget_cache["last_checked"] = time.time()

        allowed, reason = check_llm_budget("briefing_generation")
        assert allowed is False
        assert reason == "hard_limit"

        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is False
        assert reason == "hard_limit"

    def test_unpopulated_cache_fails_open(self):
        """Unpopulated cache (last_checked=0) should fail open with warning."""
        _budget_cache["last_checked"] = 0.0

        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is True
        assert reason == "no_data"

    def test_stale_cache_treats_as_degraded(self):
        """Cache older than 5 min should be treated as degraded (fail toward caution)."""
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.10
        # Set last_checked to >5 min ago (301 seconds)
        _budget_cache["last_checked"] = time.time() - 301

        # Non-critical operation should be blocked (treated as degraded)
        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is False
        assert reason == "soft_limit"

        # Critical operation should still be allowed
        allowed, reason = check_llm_budget("briefing_generation")
        assert allowed is True
        assert reason == "degraded"

    def test_fresh_cache_not_treated_as_degraded(self):
        """Cache within TTL should not be treated as stale."""
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.10
        _budget_cache["last_checked"] = time.time()

        allowed, reason = check_llm_budget("sentiment_analysis")
        assert allowed is True
        assert reason == "ok"


@pytest.mark.asyncio
class TestRefreshBudgetCache:
    """Test the async budget cache refresh function."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock(spec=AsyncIOMotorDatabase)
        db.api_costs = MagicMock()
        return db

    async def test_refresh_cache_ok_status(self, mock_db):
        """Cache should be 'ok' when cost is below soft limit."""
        # Reset cache
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = 0.0

        # Mock cost query to return $0.10 (below soft limit of $0.25)
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.10}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        result = await tracker.refresh_budget_cache()

        assert result["status"] == "ok"
        assert result["daily_cost"] == 0.10
        assert result["last_checked"] > 0

    async def test_refresh_cache_degraded_status(self, mock_db):
        """Cache should be 'degraded' when cost is between soft and hard limits."""
        # Reset cache
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = 0.0

        # Mock cost query to return $0.28 (between soft $0.25 and hard $0.33)
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.28}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        result = await tracker.refresh_budget_cache()

        assert result["status"] == "degraded"
        assert result["daily_cost"] == 0.28

    async def test_refresh_cache_hard_limit_status(self, mock_db):
        """Cache should be 'hard_limit' when cost is at/above hard limit."""
        # Reset cache
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = 0.0

        # Mock cost query to return $0.35 (above hard limit of $0.33)
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.35}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        result = await tracker.refresh_budget_cache()

        assert result["status"] == "hard_limit"
        assert result["daily_cost"] == 0.35

    async def test_refresh_cache_no_costs(self, mock_db):
        """Cache should be 'ok' with 0 cost when no records exist."""
        # Reset cache
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = 0.0

        # Mock empty aggregation result
        async_mock = AsyncMock()
        async_mock.return_value = []
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        result = await tracker.refresh_budget_cache()

        assert result["status"] == "ok"
        assert result["daily_cost"] == 0.0

    async def test_refresh_cache_db_error_marks_degraded(self, mock_db):
        """DB error during refresh should mark cache as degraded (fail toward caution)."""
        # Reset cache
        _budget_cache["status"] = "ok"
        _budget_cache["daily_cost"] = 0.0
        _budget_cache["last_checked"] = 0.0

        # Mock DB error
        async_mock = AsyncMock()
        async_mock.side_effect = Exception("DB connection failed")
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        result = await tracker.refresh_budget_cache()

        assert result["status"] == "degraded"
        assert result["last_checked"] > 0


@pytest.mark.asyncio
class TestRefreshBudgetIfStale:
    """Test the async-safe cache refresh helper."""

    async def test_refresh_if_stale_does_not_refresh_fresh_cache(self):
        """Fresh cache should not trigger a refresh."""
        _budget_cache["last_checked"] = time.time()

        with patch("crypto_news_aggregator.db.mongodb.mongo_manager") as mock_mgr:
            # Should not be called if cache is fresh
            await refresh_budget_if_stale()
            mock_mgr.get_async_database.assert_not_called()

    async def test_refresh_if_stale_refreshes_stale_cache(self):
        """Stale cache should trigger a refresh."""
        _budget_cache["last_checked"] = time.time() - 31  # 31 seconds old

        mock_db = MagicMock()
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.10}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        with patch("crypto_news_aggregator.db.mongodb.mongo_manager") as mock_mgr:
            mock_mgr.get_async_database = AsyncMock(return_value=mock_db)
            await refresh_budget_if_stale()
            mock_mgr.get_async_database.assert_called_once()


class TestBacklogThrottle:
    """Test that enrichment batch throttle caps articles per cycle."""

    def test_enrichment_max_articles_config(self):
        """ENRICHMENT_MAX_ARTICLES_PER_CYCLE should be set to 5."""
        settings = get_settings()
        assert hasattr(settings, "ENRICHMENT_MAX_ARTICLES_PER_CYCLE")
        assert settings.ENRICHMENT_MAX_ARTICLES_PER_CYCLE == 5

    @pytest.mark.skip(reason="Integration test, requires full app setup")
    async def test_enrich_articles_batch_throttles_large_backlog(self):
        """
        enrich_articles_batch should cap input to ENRICHMENT_MAX_ARTICLES_PER_CYCLE.

        This is an integration test that requires full AnthropicProvider setup.
        """
        # Would test that a 50-article backlog gets capped to 5 articles
        pass


class TestCostCalculation:
    """Test LLM cost calculation."""

    def test_haiku_pricing(self):
        """Haiku cost should be calculated correctly."""
        mock_db = MagicMock()
        tracker = CostTracker(mock_db)

        # 1M input tokens, 1M output tokens
        cost = tracker.calculate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        # Input: 1M * $1.00/1M = $1.00
        # Output: 1M * $5.00/1M = $5.00
        # Total: $6.00
        assert cost == 6.0

    def test_sonnet_pricing(self):
        """Sonnet cost should be calculated correctly."""
        mock_db = MagicMock()
        tracker = CostTracker(mock_db)

        cost = tracker.calculate_cost("claude-sonnet-4-5-20250929", 1_000_000, 1_000_000)
        # Input: 1M * $3.00/1M = $3.00
        # Output: 1M * $15.00/1M = $15.00
        # Total: $18.00
        assert cost == 18.0

    def test_unknown_model_defaults_to_haiku(self):
        """Unknown model should default to Haiku pricing."""
        mock_db = MagicMock()
        tracker = CostTracker(mock_db)

        cost = tracker.calculate_cost("unknown-model", 1_000_000, 1_000_000)
        # Should use Haiku pricing
        assert cost == 6.0

    def test_fractional_tokens_rounded(self):
        """Costs should be rounded to 6 decimal places."""
        mock_db = MagicMock()
        tracker = CostTracker(mock_db)

        cost = tracker.calculate_cost("claude-haiku-4-5-20251001", 100, 200)
        # Input: 100/1M * $1 = $0.0001
        # Output: 200/1M * $5 = $0.001
        # Total: $0.0011
        assert cost == 0.0011


@pytest.mark.asyncio
class TestBudgetGateIntegration:
    """Integration tests for budget gate behavior."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock(spec=AsyncIOMotorDatabase)
        db.api_costs = MagicMock()
        return db

    async def test_hard_limit_blocks_all_llm_calls(self, mock_db):
        """
        When daily cost >= hard limit, all LLM operations should be blocked.

        This is a behavioral integration test.
        """
        # Setup: Insert cost records totaling $0.34 (above hard limit of $0.33)
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.34}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        await tracker.refresh_budget_cache()

        # All operations should be blocked
        assert check_llm_budget("briefing_generation")[0] is False
        assert check_llm_budget("entity_extraction")[0] is False
        assert check_llm_budget("sentiment_analysis")[0] is False

    async def test_soft_limit_allows_briefing_entity_only(self, mock_db):
        """
        When daily cost is between soft and hard limit, only critical ops allowed.

        Critical: briefing_generation, entity_extraction
        Non-critical: everything else
        """
        # Setup: Insert cost records totaling $0.30 (soft limit $0.25, hard limit $0.33)
        async_mock = AsyncMock()
        async_mock.return_value = [{"total": 0.30}]
        mock_db.api_costs.aggregate.return_value.to_list = async_mock

        tracker = CostTracker(mock_db)
        await tracker.refresh_budget_cache()

        # Critical operations allowed
        allowed, _ = check_llm_budget("briefing_generation")
        assert allowed is True

        allowed, _ = check_llm_budget("entity_extraction")
        assert allowed is True

        # Non-critical operations blocked
        allowed, _ = check_llm_budget("sentiment_analysis")
        assert allowed is False

        allowed, _ = check_llm_budget("theme_extraction")
        assert allowed is False

        allowed, _ = check_llm_budget("article_enrichment_batch")
        assert allowed is False


class TestBudgetLimitConstants:
    """Verify budget limit configuration values."""

    def test_soft_limit_is_0_25(self):
        """Soft limit should be $0.25 to allow ~2.5 hours of enrichment."""
        settings = get_settings()
        assert settings.LLM_DAILY_SOFT_LIMIT == 0.25

    def test_hard_limit_is_0_33(self):
        """Hard limit should be $0.33 to provide safety margin."""
        settings = get_settings()
        assert settings.LLM_DAILY_HARD_LIMIT == 0.33

    def test_soft_limit_less_than_hard_limit(self):
        """Soft limit should be less than hard limit."""
        settings = get_settings()
        assert settings.LLM_DAILY_SOFT_LIMIT < settings.LLM_DAILY_HARD_LIMIT
