"""
Integration tests for rate limiting in LLM client methods.
Tests that rate limits are enforced across all LLM operations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from crypto_news_aggregator.llm.anthropic import AnthropicProvider
from crypto_news_aggregator.services.rate_limiter import RateLimiter


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def incr(self, key: str) -> int:
        current = self.data.get(key, 0)
        new_value = int(current) + 1
        self.data[key] = str(new_value)
        return new_value

    def expire(self, key: str, seconds: int) -> bool:
        return True

    def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            return 1
        return 0


@pytest.fixture
def mock_redis():
    """Provide mock Redis client."""
    return MockRedis()


@pytest.fixture
def rate_limiter(mock_redis):
    """Create rate limiter with test limits."""
    limits = {
        "sentiment_analysis": 10,
        "theme_extraction": 10,
        "entity_extraction": 10,
        "relevance_scoring": 10,
    }
    return RateLimiter(limits=limits, redis=mock_redis)


@pytest.fixture
def llm_provider(rate_limiter):
    """Create LLM provider with mocked rate limiter."""
    provider = AnthropicProvider(api_key="test-key")
    return provider


@pytest.mark.asyncio
class TestRateLimitIntegration:
    """Test rate limiting integration with LLM methods."""

    async def test_analyze_sentiment_tracked_checks_limit(self, llm_provider, rate_limiter):
        """analyze_sentiment_tracked should check rate limit before calling API."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("0.5", {"input_tokens": 10, "output_tokens": 5})

                # First call should succeed
                result = await llm_provider.analyze_sentiment_tracked("Test text")
                assert result == 0.5
                assert mock_api.call_count == 1

                # Verify rate limiter was incremented
                remaining = await rate_limiter.get_remaining("sentiment_analysis")
                assert remaining == 9

    async def test_analyze_sentiment_tracked_blocks_at_limit(self, llm_provider, rate_limiter):
        """analyze_sentiment_tracked should block when limit is hit."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("0.5", {"input_tokens": 10, "output_tokens": 5})

                # Hit the limit (limit is 10)
                for i in range(10):
                    await llm_provider.analyze_sentiment_tracked("Test text")

                # Next call should be blocked
                result = await llm_provider.analyze_sentiment_tracked("Test text")
                assert result == 0.0  # Returns 0.0 when blocked
                assert mock_api.call_count == 10  # No additional API call

    async def test_extract_themes_tracked_checks_limit(self, llm_provider, rate_limiter):
        """extract_themes_tracked should check rate limit before calling API."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("DeFi, Bitcoin, Regulation", {"input_tokens": 15, "output_tokens": 8})

                # First call should succeed
                result = await llm_provider.extract_themes_tracked(["Text about Bitcoin"])
                assert "DeFi" in result
                assert mock_api.call_count == 1

                # Verify rate limiter was incremented
                remaining = await rate_limiter.get_remaining("theme_extraction")
                assert remaining == 9

    async def test_extract_themes_tracked_blocks_at_limit(self, llm_provider, rate_limiter):
        """extract_themes_tracked should block when limit is hit."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("DeFi, Bitcoin", {"input_tokens": 15, "output_tokens": 8})

                # Hit the limit (limit is 10)
                for i in range(10):
                    await llm_provider.extract_themes_tracked(["Text about Bitcoin"])

                # Next call should be blocked
                result = await llm_provider.extract_themes_tracked(["Text about Bitcoin"])
                assert result == []  # Returns empty list when blocked
                assert mock_api.call_count == 10  # No additional API call

    async def test_score_relevance_tracked_checks_limit(self, llm_provider, rate_limiter):
        """score_relevance_tracked should check rate limit before calling API."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("0.8", {"input_tokens": 12, "output_tokens": 6})

                # First call should succeed
                result = await llm_provider.score_relevance_tracked("Crypto market news")
                assert result == 0.8
                assert mock_api.call_count == 1

                # Verify rate limiter was incremented
                remaining = await rate_limiter.get_remaining("relevance_scoring")
                assert remaining == 9

    async def test_enrich_articles_batch_checks_limits(self, llm_provider, rate_limiter):
        """enrich_articles_batch should check both sentiment_analysis and theme_extraction limits."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = (
                    '[{"article_id": "1", "relevance_score": 0.8, "sentiment_score": 0.5, "themes": ["Bitcoin"]}]',
                    {"input_tokens": 100, "output_tokens": 50}
                )

                # First call should succeed
                result = await llm_provider.enrich_articles_batch([{"id": "1", "text": "Test article"}])
                assert len(result) == 1
                assert mock_api.call_count == 1

                # Verify both rate limiters were incremented
                sentiment_remaining = await rate_limiter.get_remaining("sentiment_analysis")
                theme_remaining = await rate_limiter.get_remaining("theme_extraction")
                assert sentiment_remaining == 9
                assert theme_remaining == 9

    async def test_enrich_articles_batch_blocks_when_sentiment_limit_hit(self, llm_provider, rate_limiter):
        """enrich_articles_batch should block when sentiment_analysis limit is hit."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = (
                    '[{"article_id": "1", "relevance_score": 0.8, "sentiment_score": 0.5, "themes": ["Bitcoin"]}]',
                    {"input_tokens": 100, "output_tokens": 50}
                )

                # Hit sentiment_analysis limit
                for i in range(10):
                    await rate_limiter.increment("sentiment_analysis")

                # Next enrich call should be blocked
                result = await llm_provider.enrich_articles_batch([{"id": "1", "text": "Test article"}])
                assert result == []  # Returns empty list when blocked
                assert mock_api.call_count == 0  # No API call

    async def test_rate_limits_independent_per_system(self, llm_provider, rate_limiter):
        """Rate limits should be independent per system."""
        with patch.object(llm_provider, "_get_completion_with_usage") as mock_api:
            with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
                mock_api.return_value = ("0.5", {"input_tokens": 10, "output_tokens": 5})

                # Hit sentiment_analysis limit
                for i in range(10):
                    await llm_provider.analyze_sentiment_tracked("Test")

                # sentiment_analysis should be blocked
                sentiment_result = await llm_provider.analyze_sentiment_tracked("Test")
                assert sentiment_result == 0.0

                # But relevance_scoring should still work (limit not hit)
                relevance_result = await llm_provider.score_relevance_tracked("Test")
                assert relevance_result == 0.5
                assert mock_api.call_count == 11  # 10 sentiment + 1 relevance


class TestExtractEntitiesBatchRateLimit:
    """Test rate limiting for extract_entities_batch (synchronous method)."""

    def test_extract_entities_batch_checks_limit(self):
        """extract_entities_batch should check entity_extraction limit."""
        mock_redis = MockRedis()
        rate_limiter = RateLimiter(
            limits={"entity_extraction": 5},
            redis=mock_redis
        )

        provider = AnthropicProvider(api_key="test-key")

        with patch("crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter):
            with patch("httpx.Client") as mock_client:
                mock_response = Mock()
                mock_response.json.return_value = {
                    "content": [{"text": '[{"article_index": 0, "article_id": "1", "primary_entities": [], "context_entities": []}]'}],
                    "usage": {"input_tokens": 100, "output_tokens": 50}
                }
                mock_response.raise_for_status = Mock()
                mock_client.return_value.__enter__.return_value.post.return_value = mock_response

                # Make calls up to limit
                for i in range(5):
                    result = provider.extract_entities_batch([{"id": "1", "title": "Test", "text": "Test"}])
                    if i < 5:
                        assert result.get("results") is not None

                # Next call should be blocked
                result = provider.extract_entities_batch([{"id": "1", "title": "Test", "text": "Test"}])
                assert result == {"results": [], "usage": {}}
