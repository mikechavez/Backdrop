"""
Rate limiting service for LLM API calls.

Implements per-system daily call limits to prevent runaway spend.
Uses Redis with daily TTL for tracking.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from crypto_news_aggregator.core.redis_rest_client import redis_client

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Tracks daily API call counts per system with configurable limits.

    Features:
    - Per-system daily call tracking (briefing, entity_extraction, sentiment_analysis, etc.)
    - Redis-backed with automatic daily TTL expiry
    - Configurable limits via environment or constructor
    - Clear error messages when limits hit
    """

    # Default daily limits per system (can be overridden)
    DEFAULT_LIMITS = {
        "briefing_generation": 1000,
        "entity_extraction": 5000,
        "sentiment_analysis": 5000,
        "theme_extraction": 5000,
        "narrative_detection": 2000,
    }

    def __init__(
        self,
        db: Optional[AsyncIOMotorDatabase] = None,
        limits: Optional[dict] = None,
        redis: Optional[object] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            db: MongoDB database instance (for metrics/logging)
            limits: Dict of system -> daily limit. Uses DEFAULT_LIMITS if not provided.
            redis: Redis client (for dependency injection in tests)
        """
        self.db = db
        self.limits = limits or self.DEFAULT_LIMITS.copy()
        self.redis = redis or redis_client

    def _get_daily_key(self, system: str, date: Optional[datetime] = None) -> str:
        """
        Get Redis key for daily call count.

        Args:
            system: System name (e.g., "entity_extraction")
            date: Date to use (defaults to today)

        Returns:
            Redis key like "rate_limit:entity_extraction:2026-03-31"
        """
        if date is None:
            date = datetime.now(timezone.utc)

        date_str = date.strftime("%Y-%m-%d")
        return f"rate_limit:{system}:{date_str}"

    async def get_remaining(self, system: str) -> int:
        """
        Get remaining calls for a system today.

        Args:
            system: System name

        Returns:
            Remaining calls, or -1 if system not tracked
        """
        if system not in self.limits:
            logger.warning(f"System '{system}' not in rate limit config")
            return -1

        key = self._get_daily_key(system)
        count = self.redis.get(key)

        if count is None:
            return self.limits[system]

        return max(0, self.limits[system] - int(count))

    async def check_limit(self, system: str) -> tuple[bool, str]:
        """
        Check if a system has remaining calls today.

        Args:
            system: System name

        Returns:
            (allowed: bool, message: str)
            - allowed=True: call is allowed
            - allowed=False: limit hit, message explains why
        """
        if system not in self.limits:
            logger.warning(f"System '{system}' not in rate limit config, allowing call")
            return True, "System not tracked"

        key = self._get_daily_key(system)
        count = self.redis.get(key)

        current_count = int(count) if count else 0
        limit = self.limits[system]

        if current_count >= limit:
            remaining = 0
            message = (
                f"Daily limit for '{system}' hit ({limit} calls). "
                f"Resets tomorrow at midnight UTC."
            )
            logger.warning(message)
            return False, message

        return True, f"{limit - current_count - 1} calls remaining"

    async def increment(self, system: str) -> int:
        """
        Increment call count for a system.

        Should be called AFTER check_limit() passes and the API call succeeds.

        Args:
            system: System name

        Returns:
            New count for the day
        """
        if system not in self.limits:
            logger.warning(f"System '{system}' not in rate limit config, skipping increment")
            return -1

        key = self._get_daily_key(system)

        # Increment and set TTL if needed
        count = self.redis.incr(key)

        # Set TTL to ensure it expires tomorrow (24 hours)
        ttl_seconds = 24 * 60 * 60
        self.redis.expire(key, ttl_seconds)

        # Log on milestones (25%, 50%, 75%, 90%, 100%)
        limit = self.limits[system]
        pct = (count / limit) * 100

        if pct in [25, 50, 75, 90, 100]:
            logger.info(
                f"Rate limit milestone: {system} at {pct:.0f}% "
                f"({count}/{limit} calls)"
            )

        return count

    def set_limit(self, system: str, limit: int):
        """
        Update daily limit for a system.

        Args:
            system: System name
            limit: New daily limit
        """
        self.limits[system] = limit
        logger.info(f"Updated rate limit for '{system}' to {limit} calls/day")

    async def reset_daily_counts(self, system: Optional[str] = None):
        """
        Reset daily call counts (mainly for testing).

        Args:
            system: Specific system to reset, or None to reset all
        """
        if system:
            key = self._get_daily_key(system)
            self.redis.delete(key)
            logger.info(f"Reset daily count for '{system}'")
        else:
            # Reset all systems
            for sys in self.limits:
                key = self._get_daily_key(sys)
                self.redis.delete(key)
            logger.info("Reset all daily counts")


# Global instance (initialized by dependency injection)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(
    db: Optional[AsyncIOMotorDatabase] = None,
    limits: Optional[dict] = None,
) -> RateLimiter:
    """
    Get or create rate limiter instance.

    Args:
        db: MongoDB database instance
        limits: Custom limits dict

    Returns:
        RateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(db, limits)
    return _rate_limiter
