"""
Tests for rate limiting service.
"""

import pytest
from datetime import datetime, timezone
from crypto_news_aggregator.services.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create rate limiter instance with test limits."""
    limits = {
        "entity_extraction": 100,
        "sentiment_analysis": 50,
        "briefing_generation": 10,
    }
    return RateLimiter(limits=limits)


@pytest.mark.asyncio
class TestRateLimiter:
    """Test rate limiting functionality."""

    async def test_get_remaining_returns_full_limit_initially(self, rate_limiter):
        """First call should show full limit available."""
        remaining = await rate_limiter.get_remaining("entity_extraction")
        assert remaining == 100

    async def test_check_limit_allows_first_call(self, rate_limiter):
        """First call should be allowed."""
        allowed, message = await rate_limiter.check_limit("entity_extraction")
        assert allowed is True
        assert "remaining" in message.lower()

    async def test_increment_increases_count(self, rate_limiter):
        """Increment should increase the count."""
        # First increment
        count1 = await rate_limiter.increment("entity_extraction")
        assert count1 == 1

        # Second increment
        count2 = await rate_limiter.increment("entity_extraction")
        assert count2 == 2

    async def test_get_remaining_decreases_after_increment(self, rate_limiter):
        """Remaining count should decrease after increment."""
        initial = await rate_limiter.get_remaining("entity_extraction")
        assert initial == 100

        await rate_limiter.increment("entity_extraction")
        after_one = await rate_limiter.get_remaining("entity_extraction")
        assert after_one == 99

        await rate_limiter.increment("entity_extraction")
        after_two = await rate_limiter.get_remaining("entity_extraction")
        assert after_two == 98

    async def test_limit_hit_blocks_calls(self, rate_limiter):
        """When limit is hit, check_limit should return False."""
        # Use briefing_generation which has limit of 10
        limit = 10

        # Use up the limit
        for i in range(limit):
            await rate_limiter.increment("briefing_generation")

        # Next check should fail
        allowed, message = await rate_limiter.check_limit("briefing_generation")
        assert allowed is False
        assert "limit" in message.lower()

    async def test_unknown_system_allowed(self, rate_limiter):
        """Unknown systems should be allowed (fail-open)."""
        allowed, message = await rate_limiter.check_limit("unknown_system")
        assert allowed is True

    async def test_set_limit_updates_limit(self, rate_limiter):
        """set_limit should update the limit."""
        rate_limiter.set_limit("sentiment_analysis", 200)
        remaining = await rate_limiter.get_remaining("sentiment_analysis")
        assert remaining == 200

    async def test_reset_daily_counts_specific_system(self, rate_limiter):
        """Reset should clear count for specific system."""
        # Use up some calls
        await rate_limiter.increment("entity_extraction")
        await rate_limiter.increment("entity_extraction")

        remaining_before = await rate_limiter.get_remaining("entity_extraction")
        assert remaining_before == 98

        # Reset
        await rate_limiter.reset_daily_counts("entity_extraction")

        # Should be back to full
        remaining_after = await rate_limiter.get_remaining("entity_extraction")
        assert remaining_after == 100

    async def test_reset_daily_counts_all_systems(self, rate_limiter):
        """Reset without system param should reset all."""
        # Use up calls in multiple systems
        await rate_limiter.increment("entity_extraction")
        await rate_limiter.increment("sentiment_analysis")

        # Reset all
        await rate_limiter.reset_daily_counts()

        # All should be back to full
        assert await rate_limiter.get_remaining("entity_extraction") == 100
        assert await rate_limiter.get_remaining("sentiment_analysis") == 50

    async def test_different_systems_independent(self, rate_limiter):
        """Call counts for different systems should be independent."""
        # Use entity_extraction
        await rate_limiter.increment("entity_extraction")
        await rate_limiter.increment("entity_extraction")

        # sentiment_analysis should still be at full
        remaining_sentiment = await rate_limiter.get_remaining("sentiment_analysis")
        assert remaining_sentiment == 50

        remaining_entity = await rate_limiter.get_remaining("entity_extraction")
        assert remaining_entity == 98
