"""
Unit tests for CircuitBreaker service.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from crypto_news_aggregator.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
)


class MockRedis:
    """Mock Redis for testing circuit breaker without actual Redis."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        """Get value from mock storage."""
        return self.data.get(key)

    def set(self, key, value, ex=None):
        """Set value in mock storage."""
        self.data[key] = value

    def delete(self, key):
        """Delete key from mock storage."""
        if key in self.data:
            del self.data[key]

    def incr(self, key):
        """Increment value in mock storage."""
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
        """Mock expire (no-op for testing)."""
        pass


@pytest.fixture
def mock_redis():
    """Provide a mock Redis instance."""
    return MockRedis()


@pytest.fixture
def circuit_breaker(mock_redis):
    """Create a circuit breaker with mock Redis."""
    cb = CircuitBreaker(redis=mock_redis)
    return cb


@pytest.mark.asyncio
class TestCircuitBreakerBasics:
    """Test basic circuit breaker functionality."""

    async def test_circuit_starts_closed(self, circuit_breaker):
        """Circuit should start in CLOSED state."""
        allowed, message = await circuit_breaker.check_circuit("sentiment_analysis")
        assert allowed is True
        assert "CLOSED" in message

    async def test_check_circuit_unknown_system(self, circuit_breaker):
        """Unknown systems should be allowed with warning."""
        allowed, message = await circuit_breaker.check_circuit("unknown_system")
        assert allowed is True
        assert "not tracked" in message

    async def test_record_success_resets_failures(self, circuit_breaker):
        """Recording success should reset failure counter."""
        # Record some failures
        for _ in range(3):
            circuit_breaker.record_failure("sentiment_analysis")

        # Check state (should be OPEN now)
        state = circuit_breaker._get_state("sentiment_analysis")
        assert state == CircuitState.OPEN

        # Record success
        circuit_breaker.record_success("sentiment_analysis")

        # Failure counter should be reset
        failure_key = circuit_breaker._get_failure_key("sentiment_analysis")
        assert circuit_breaker.redis.get(failure_key) is None


@pytest.mark.asyncio
class TestCircuitBreakerTripping:
    """Test circuit breaker tripping behavior."""

    async def test_circuit_opens_at_threshold(self, circuit_breaker):
        """Circuit should open after N consecutive failures."""
        threshold = circuit_breaker.config["failure_threshold"]

        # Record failures up to threshold
        for i in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Circuit should be OPEN now
        state = circuit_breaker._get_state("sentiment_analysis")
        assert state == CircuitState.OPEN

    async def test_circuit_blocks_calls_when_open(self, circuit_breaker):
        """Open circuit should block API calls."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Check circuit
        allowed, message = await circuit_breaker.check_circuit("sentiment_analysis")
        assert allowed is False
        assert "OPEN" in message
        assert "unavailable" in message.lower()

    async def test_half_open_state_after_cooldown(self, circuit_breaker):
        """Circuit should transition to HALF_OPEN after cooldown (simulated by state)."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Manually set to HALF_OPEN to simulate cooldown expiry
        circuit_breaker._set_state("sentiment_analysis", CircuitState.HALF_OPEN)

        # Check circuit should allow one call
        allowed, message = await circuit_breaker.check_circuit("sentiment_analysis")
        assert allowed is True
        assert "HALF_OPEN" in message

    async def test_closes_after_success_in_half_open(self, circuit_breaker):
        """Circuit should close after successful recovery test."""
        # Trip the circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # Set to HALF_OPEN
        circuit_breaker._set_state("sentiment_analysis", CircuitState.HALF_OPEN)
        assert circuit_breaker._get_state("sentiment_analysis") == CircuitState.HALF_OPEN

        # Record success
        circuit_breaker.record_success("sentiment_analysis")

        # Should be CLOSED now
        state = circuit_breaker._get_state("sentiment_analysis")
        assert state == CircuitState.CLOSED


@pytest.mark.asyncio
class TestCircuitBreakerPerSystem:
    """Test circuit breaker isolation per system."""

    async def test_independent_per_system(self, circuit_breaker):
        """Each system should have independent state."""
        # Trip sentiment circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        # sentiment_analysis should be OPEN
        allowed_sentiment, _ = await circuit_breaker.check_circuit("sentiment_analysis")
        assert allowed_sentiment is False

        # theme_extraction should still be CLOSED
        allowed_theme, _ = await circuit_breaker.check_circuit("theme_extraction")
        assert allowed_theme is True

    async def test_reset_individual_system(self, circuit_breaker):
        """Should be able to reset individual circuit breakers."""
        # Trip sentiment circuit
        threshold = circuit_breaker.config["failure_threshold"]
        for _ in range(threshold):
            circuit_breaker.record_failure("sentiment_analysis")

        assert circuit_breaker._get_state("sentiment_analysis") == CircuitState.OPEN

        # Reset just sentiment
        await circuit_breaker.reset_circuit("sentiment_analysis")

        # Should be CLOSED again
        assert circuit_breaker._get_state("sentiment_analysis") == CircuitState.CLOSED


@pytest.mark.asyncio
class TestCircuitBreakerMonitoring:
    """Test circuit breaker monitoring/debugging."""

    async def test_get_state_for_system(self, circuit_breaker):
        """Should return full state for a system."""
        # Record a failure
        circuit_breaker.record_failure("sentiment_analysis")

        state = circuit_breaker.get_state_for_system("sentiment_analysis")
        assert state["system"] == "sentiment_analysis"
        assert state["state"] == "closed"  # Not yet open (below threshold)
        assert state["failure_count"] == 1
        assert state["failure_threshold"] == 3

    async def test_get_all_states(self, circuit_breaker):
        """Should return states for all systems."""
        # Record failures in sentiment
        circuit_breaker.record_failure("sentiment_analysis")

        states = circuit_breaker.get_all_states()
        assert "sentiment_analysis" in states
        assert "theme_extraction" in states
        assert "entity_extraction" in states

    async def test_get_state_unknown_system(self, circuit_breaker):
        """Should return error for unknown system."""
        state = circuit_breaker.get_state_for_system("unknown_system")
        assert "error" in state


@pytest.mark.asyncio
class TestCircuitBreakerConfiguration:
    """Test circuit breaker configuration."""

    async def test_custom_config(self):
        """Should accept custom configuration."""
        custom_config = {
            "failure_threshold": 5,
            "cooldown_seconds": 60,
            "success_threshold": 2,
        }
        cb = CircuitBreaker(config=custom_config, redis=MockRedis())
        assert cb.config["failure_threshold"] == 5
        assert cb.config["cooldown_seconds"] == 60

    async def test_uses_default_config_if_not_provided(self):
        """Should use defaults if not provided."""
        cb = CircuitBreaker(redis=MockRedis())
        assert cb.config["failure_threshold"] == 3
        assert cb.config["cooldown_seconds"] == 300


@pytest.mark.asyncio
class TestCircuitBreakerGlobalInstance:
    """Test global circuit breaker instance management."""

    async def test_get_circuit_breaker_singleton(self):
        """get_circuit_breaker should return singleton instance."""
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        assert cb1 is cb2

    async def test_reset_global_instance(self):
        """Should be able to reset global instance (for testing)."""
        # This would require a reset function or monkeypatching
        # For now, just verify the singleton works
        cb = get_circuit_breaker()
        assert cb is not None
