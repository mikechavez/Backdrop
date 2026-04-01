"""
Integration tests for CircuitBreaker with LLM methods.

Tests that circuit breaker correctly blocks and unblocks LLM calls.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from crypto_news_aggregator.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
)
from crypto_news_aggregator.services.rate_limiter import RateLimiter
from crypto_news_aggregator.llm.anthropic import AnthropicProvider


class MockRedis:
    """Mock Redis for testing."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value

    def delete(self, key):
        if key in self.data:
            del self.data[key]

    def incr(self, key):
        current = self.data.get(key)
        if current is None:
            self.data[key] = 1
            return 1
        else:
            try:
                current_int = int(current) if isinstance(current, bytes) else int(current)
                new_val = current_int + 1
                self.data[key] = str(new_val)
                return new_val
            except (ValueError, TypeError):
                return None

    def expire(self, key, ttl):
        pass


@pytest.fixture
def mock_redis():
    return MockRedis()


@pytest.fixture
def circuit_breaker(mock_redis):
    """Create circuit breaker with mock Redis."""
    cb = CircuitBreaker(redis=mock_redis)
    return cb


@pytest.fixture
def rate_limiter(mock_redis):
    """Create rate limiter with mock Redis."""
    limits = {
        "briefing_generation": 1000,
        "entity_extraction": 5000,
        "sentiment_analysis": 5000,
        "theme_extraction": 5000,
        "narrative_detection": 2000,
        "relevance_scoring": 5000,
    }
    rl = RateLimiter(limits=limits, redis=mock_redis)
    return rl


@pytest.fixture
def anthropic_provider():
    """Create Anthropic provider with mock API key."""
    return AnthropicProvider(api_key="test-key", model_name="claude-haiku-4-5-20251001")


@pytest.mark.asyncio
class TestCircuitBreakerWithLLMClient:
    """Test circuit breaker integration with LLM client."""

    async def test_sentiment_blocked_when_circuit_open(self, circuit_breaker, anthropic_provider):
        """analyze_sentiment_tracked should return 0.0 when circuit is open."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Patch get_circuit_breaker to return our instance
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ):
            result = await anthropic_provider.analyze_sentiment_tracked("Bitcoin is up")
            assert result == 0.0

    async def test_themes_blocked_when_circuit_open(self, circuit_breaker, anthropic_provider):
        """extract_themes_tracked should return [] when circuit is open."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("theme_extraction")

        # Patch get_circuit_breaker to return our instance
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ):
            result = await anthropic_provider.extract_themes_tracked(["Bitcoin"])
            assert result == []

    async def test_relevance_blocked_when_circuit_open(self, circuit_breaker, anthropic_provider):
        """score_relevance_tracked should return 0.0 when circuit is open."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("relevance_scoring")

        # Patch get_circuit_breaker to return our instance
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ):
            result = await anthropic_provider.score_relevance_tracked("Bitcoin price up")
            assert result == 0.0

    async def test_batch_enrichment_blocked_when_circuit_open(
        self, circuit_breaker, anthropic_provider
    ):
        """enrich_articles_batch should return [] when circuit is open."""
        # Trip sentiment circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Patch get_circuit_breaker to return our instance
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ):
            result = await anthropic_provider.enrich_articles_batch([
                {"id": "1", "text": "Bitcoin"}
            ])
            assert result == []

    async def test_sentiment_allowed_when_circuit_closed(
        self, circuit_breaker, rate_limiter, anthropic_provider
    ):
        """Circuit should allow call when closed (not actually make API call though)."""
        # Patch both get_circuit_breaker and get_rate_limiter
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ), patch(
            "crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter
        ), patch.object(
            anthropic_provider, "_get_completion_with_usage", return_value=("0.5", {})
        ):
            # Mock successful API response
            result = await anthropic_provider.analyze_sentiment_tracked("Bitcoin")
            # Result should be parsed (0.5 -> 0.5), not 0.0 (blocked)
            assert result == 0.5


@pytest.mark.asyncio
class TestCircuitBreakerRecovery:
    """Test circuit breaker recovery flow."""

    async def test_records_success_after_api_call(
        self, circuit_breaker, rate_limiter, anthropic_provider
    ):
        """Circuit breaker should record success after successful API call."""
        # Patch dependencies
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ), patch(
            "crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter
        ), patch.object(
            anthropic_provider, "_get_completion_with_usage", return_value=("0.7", {})
        ):
            await anthropic_provider.analyze_sentiment_tracked("Bitcoin")

            # Failure counter should be reset
            failure_key = circuit_breaker._get_failure_key("sentiment_analysis")
            assert circuit_breaker.redis.get(failure_key) is None

    async def test_records_failure_on_exception(
        self, circuit_breaker, rate_limiter, anthropic_provider
    ):
        """Circuit breaker should record failure on API exception."""
        # Patch dependencies with exception
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ), patch(
            "crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter
        ), patch.object(
            anthropic_provider, "_get_completion_with_usage", side_effect=Exception("API error")
        ):
            result = await anthropic_provider.analyze_sentiment_tracked("Bitcoin")
            assert result == 0.0

            # Failure should be recorded
            failure_key = circuit_breaker._get_failure_key("sentiment_analysis")
            failure_count = circuit_breaker.redis.get(failure_key)
            assert failure_count is not None
            assert int(failure_count) >= 1


@pytest.mark.asyncio
class TestCircuitBreakerHalfOpenBehavior:
    """Test half-open state behavior."""

    async def test_half_open_allows_one_test_call(self, circuit_breaker, anthropic_provider):
        """Half-open should allow a single test call."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Set to half-open
        circuit_breaker._set_state("sentiment_analysis", CircuitState.HALF_OPEN)

        # Should allow the call
        allowed, _ = await circuit_breaker.check_circuit("sentiment_analysis")
        assert allowed is True

    async def test_half_open_closes_on_success(self, circuit_breaker, rate_limiter, anthropic_provider):
        """Half-open should close on successful test call."""
        # Trip and set to half-open
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")
        circuit_breaker._set_state("sentiment_analysis", CircuitState.HALF_OPEN)

        # Patch and make successful call
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ), patch(
            "crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter
        ), patch.object(
            anthropic_provider, "_get_completion_with_usage", return_value=("0.5", {})
        ):
            await anthropic_provider.analyze_sentiment_tracked("Bitcoin")

            # Circuit should be CLOSED now
            state = circuit_breaker._get_state("sentiment_analysis")
            assert state == CircuitState.CLOSED

    async def test_half_open_opens_on_failure(self, circuit_breaker, rate_limiter, anthropic_provider):
        """Half-open should reopen on failure during test call."""
        # Trip and set to half-open
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")
        circuit_breaker._set_state("sentiment_analysis", CircuitState.HALF_OPEN)

        # Patch with failure
        with patch(
            "crypto_news_aggregator.llm.anthropic.get_circuit_breaker", return_value=circuit_breaker
        ), patch(
            "crypto_news_aggregator.llm.anthropic.get_rate_limiter", return_value=rate_limiter
        ), patch.object(
            anthropic_provider, "_get_completion_with_usage", side_effect=Exception("API error")
        ):
            result = await anthropic_provider.analyze_sentiment_tracked("Bitcoin")
            assert result == 0.0

            # Circuit should be OPEN again
            state = circuit_breaker._get_state("sentiment_analysis")
            assert state == CircuitState.OPEN


@pytest.mark.asyncio
class TestMultipleSystemIndependence:
    """Test that circuit breakers for different systems are independent."""

    async def test_sentiment_trip_doesnt_affect_theme(self, circuit_breaker):
        """Tripping sentiment circuit should not affect theme circuit."""
        # Trip sentiment
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # sentiment should be open
        state_sentiment = circuit_breaker._get_state("sentiment_analysis")
        assert state_sentiment == CircuitState.OPEN

        # theme should be closed
        state_theme = circuit_breaker._get_state("theme_extraction")
        assert state_theme == CircuitState.CLOSED

    async def test_entity_trip_doesnt_affect_others(self, circuit_breaker):
        """Tripping entity circuit should not affect other circuits."""
        # Trip entity
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("entity_extraction")

        # entity should be open
        assert circuit_breaker._get_state("entity_extraction") == CircuitState.OPEN

        # others should be closed
        assert circuit_breaker._get_state("sentiment_analysis") == CircuitState.CLOSED
        assert circuit_breaker._get_state("theme_extraction") == CircuitState.CLOSED
        assert circuit_breaker._get_state("relevance_scoring") == CircuitState.CLOSED
