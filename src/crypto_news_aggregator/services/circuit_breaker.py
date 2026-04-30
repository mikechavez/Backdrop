"""
Circuit breaker service for LLM API calls.

Implements per-system circuit breaker to prevent retry storms when services are down.
Uses Redis with TTL-based state management.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase
from crypto_news_aggregator.core.redis_rest_client import redis_client

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker state enum."""
    CLOSED = "closed"          # Normal operation, calls allowed
    OPEN = "open"              # Service is down, calls blocked
    HALF_OPEN = "half_open"    # Service may be recovering, single test call allowed


class CircuitBreaker:
    """
    Tracks consecutive failures per system and opens circuit to prevent retry storms.

    Features:
    - Per-system failure tracking (briefing, entity_extraction, sentiment_analysis, etc.)
    - Auto-open after N consecutive failures
    - Half-open state for recovery testing
    - Redis-backed with configurable cooldown
    - Clear error messages when circuit open
    """

    # Default configuration (can be overridden)
    DEFAULT_CONFIG = {
        "failure_threshold": 3,      # Open after 3 consecutive failures
        "cooldown_seconds": 300,     # Half-open retry after 5 minutes
        "success_threshold": 1,      # Close after 1 success in half-open (1 successful call)
    }

    def __init__(
        self,
        db: Optional[AsyncIOMotorDatabase] = None,
        config: Optional[dict] = None,
        redis: Optional[object] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            db: MongoDB database instance (for metrics/logging)
            config: Dict with failure_threshold, cooldown_seconds, success_threshold
            redis: Redis client (for dependency injection in tests)
        """
        self.db = db
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.redis = redis or redis_client

        # Systems to track (same as rate limiter)
        self.systems = [
            "briefing_generation",
            "entity_extraction",
            "sentiment_analysis",
            "theme_extraction",
            "article_enrichment_batch",
            "narrative_detection",
            "relevance_scoring",
        ]

    def _get_failure_key(self, system: str) -> str:
        """Get Redis key for failure counter."""
        return f"circuit_breaker:failures:{system}"

    def _get_state_key(self, system: str) -> str:
        """Get Redis key for circuit state."""
        return f"circuit_breaker:state:{system}"

    def _get_last_failure_key(self, system: str) -> str:
        """Get Redis key for last failure timestamp."""
        return f"circuit_breaker:last_failure:{system}"

    def _get_state(self, system: str) -> CircuitState:
        """
        Get current circuit state.

        Returns:
            CircuitState.CLOSED, OPEN, or HALF_OPEN
        """
        state_val = self.redis.get(self._get_state_key(system))
        if state_val:
            try:
                return CircuitState(state_val.decode() if isinstance(state_val, bytes) else state_val)
            except ValueError:
                # Invalid state, assume closed
                return CircuitState.CLOSED
        return CircuitState.CLOSED

    def _set_state(self, system: str, state: CircuitState, ttl: Optional[int] = None):
        """
        Set circuit state in Redis.

        Args:
            system: System name
            state: New state
            ttl: TTL in seconds (optional, for time-limited states)
        """
        key = self._get_state_key(system)
        self.redis.set(key, state.value)
        if ttl:
            self.redis.expire(key, ttl)

    async def check_circuit(self, system: str) -> tuple[bool, str]:
        """
        Check if circuit allows a call for this system.

        Args:
            system: System name

        Returns:
            (allowed: bool, message: str)
            - allowed=True: call is allowed (circuit CLOSED or HALF_OPEN for test)
            - allowed=False: call blocked (circuit OPEN), message explains why
        """
        if system not in self.systems:
            logger.warning(f"System '{system}' not tracked by circuit breaker, allowing call")
            return True, "System not tracked"

        state = self._get_state(system)

        if state == CircuitState.OPEN:
            message = (
                f"Circuit breaker OPEN for '{system}' due to repeated failures. "
                f"Service unavailable, retrying in {self.config['cooldown_seconds']}s."
            )
            logger.warning(message)
            return False, message

        if state == CircuitState.HALF_OPEN:
            message = f"Circuit HALF_OPEN for '{system}', attempting recovery..."
            logger.info(message)
            # Allow one test call in half-open state
            return True, message

        # CLOSED - normal operation
        return True, f"Circuit CLOSED for '{system}', calls allowed"

    def record_success(self, system: str):
        """
        Record a successful API call for this system.

        Should be called immediately after a successful API call (before any processing).
        Resets failure counter and closes circuit if in half-open state.

        Args:
            system: System name
        """
        if system not in self.systems:
            logger.warning(f"System '{system}' not tracked by circuit breaker, skipping success")
            return

        state = self._get_state(system)

        # Reset failure counter
        failure_key = self._get_failure_key(system)
        self.redis.delete(failure_key)

        # If in half-open, close the circuit
        if state == CircuitState.HALF_OPEN:
            self._set_state(system, CircuitState.CLOSED)
            logger.info(f"Circuit breaker CLOSED for '{system}' after successful recovery test")

        # Clean up last failure timestamp
        self.redis.delete(self._get_last_failure_key(system))

    def record_failure(self, system: str):
        """
        Record a failed API call for this system.

        Should be called immediately when an API call fails (before any retry logic).
        Increments failure counter and opens circuit if threshold exceeded.

        Args:
            system: System name
        """
        if system not in self.systems:
            logger.warning(f"System '{system}' not tracked by circuit breaker, skipping failure")
            return

        # Increment failure counter
        failure_key = self._get_failure_key(system)
        count = self.redis.incr(failure_key)

        # Set TTL on failure counter (1 day) to auto-reset
        ttl_seconds = 24 * 60 * 60
        self.redis.expire(failure_key, ttl_seconds)

        # Store last failure timestamp
        timestamp = datetime.now(timezone.utc).isoformat()
        self.redis.set(self._get_last_failure_key(system), timestamp, ex=ttl_seconds)

        threshold = self.config["failure_threshold"]

        if count >= threshold:
            # Trip the circuit
            self._set_state(system, CircuitState.OPEN, ttl=self.config["cooldown_seconds"])
            logger.error(
                f"Circuit breaker OPEN for '{system}' after {count} consecutive failures. "
                f"Cooldown: {self.config['cooldown_seconds']}s"
            )
        else:
            # Still in CLOSED state, but log the failure
            logger.warning(
                f"Failure recorded for '{system}' ({count}/{threshold}). "
                f"Circuit will open at {threshold} failures."
            )

    def get_state_for_system(self, system: str) -> dict:
        """
        Get full circuit state for a system (for monitoring/debugging).

        Args:
            system: System name

        Returns:
            Dict with state, failure_count, and last_failure_time
        """
        if system not in self.systems:
            return {"error": f"System '{system}' not tracked"}

        state = self._get_state(system)
        failure_key = self._get_failure_key(system)
        failure_count_val = self.redis.get(failure_key)
        failure_count = int(failure_count_val) if failure_count_val else 0

        last_failure_key = self._get_last_failure_key(system)
        last_failure = self.redis.get(last_failure_key)
        if last_failure:
            last_failure = last_failure.decode() if isinstance(last_failure, bytes) else last_failure

        return {
            "system": system,
            "state": state.value,
            "failure_count": failure_count,
            "failure_threshold": self.config["failure_threshold"],
            "last_failure": last_failure,
        }

    def get_all_states(self) -> dict:
        """Get circuit state for all tracked systems."""
        return {system: self.get_state_for_system(system) for system in self.systems}

    async def reset_circuit(self, system: Optional[str] = None):
        """
        Manually reset circuit state (mainly for testing).

        Args:
            system: Specific system to reset, or None to reset all
        """
        if system:
            self.redis.delete(self._get_failure_key(system))
            self.redis.delete(self._get_state_key(system))
            self.redis.delete(self._get_last_failure_key(system))
            logger.info(f"Reset circuit breaker for '{system}'")
        else:
            # Reset all systems
            for sys in self.systems:
                self.redis.delete(self._get_failure_key(sys))
                self.redis.delete(self._get_state_key(sys))
                self.redis.delete(self._get_last_failure_key(sys))
            logger.info("Reset all circuit breakers")


# Global instance (initialized by dependency injection)
_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker(
    db: Optional[AsyncIOMotorDatabase] = None,
    config: Optional[dict] = None,
) -> CircuitBreaker:
    """
    Get or create circuit breaker instance.

    Args:
        db: MongoDB database instance
        config: Custom config dict

    Returns:
        CircuitBreaker instance
    """
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(db, config)
    return _circuit_breaker
