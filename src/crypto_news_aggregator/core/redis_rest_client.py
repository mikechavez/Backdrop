import json
from typing import Any, Optional
import redis
from .config import get_settings

logger_import = True
try:
    import logging
    logger = logging.getLogger(__name__)
except ImportError:
    logger_import = False


class RedisClient:
    """
    A Redis client that uses redis-py for direct protocol communication.
    Supports both Railway Redis and local Redis instances.
    Provides a simple key-value interface compatible with previous REST client.
    """

    def __init__(self, url: str = None):
        """
        Initialize the Redis client.

        Args:
            url: Redis URL (e.g., redis://localhost:6379/0 or redis://default:...@redis.railway.internal:6379)
        """
        settings = get_settings()
        self.url = url or settings.REDIS_URL

        self.enabled = bool(self.url)
        self.client = None

        if self.enabled:
            try:
                # Decode URL to handle connection strings properly
                self.client = redis.from_url(self.url, decode_responses=True)
                # Test connection with ping
                self.client.ping()
            except Exception as e:
                if logger_import:
                    logger.error(f"Failed to connect to Redis: {e}")
                self.enabled = False
                self.client = None

    def get(self, key: str) -> Optional[Any]:
        """Get the value of a key."""
        if not self.enabled or not self.client:
            return None

        try:
            value = self.client.get(key)
            # Try to deserialize JSON if it looks like JSON
            if value and isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    return value
            return value
        except Exception as e:
            if logger_import:
                logger.error(f"Redis GET error for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set the value of a key."""
        if not self.enabled or not self.client:
            return False

        try:
            # Serialize non-string values to JSON
            if not isinstance(value, (str, int, float, bool)):
                value = json.dumps(value)

            self.client.set(key, value, ex=ex)
            return True
        except Exception as e:
            if logger_import:
                logger.error(f"Redis SET error for {key}: {e}")
            return False

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        if not self.enabled or not self.client:
            return 0

        try:
            return self.client.delete(*keys)
        except Exception as e:
            if logger_import:
                logger.error(f"Redis DELETE error for {keys}: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if not self.enabled or not self.client:
            return False

        try:
            return bool(self.client.exists(key))
        except Exception as e:
            if logger_import:
                logger.error(f"Redis EXISTS error for {key}: {e}")
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """Set a key's time to live in seconds."""
        if not self.enabled or not self.client:
            return False

        try:
            return bool(self.client.expire(key, seconds))
        except Exception as e:
            if logger_import:
                logger.error(f"Redis EXPIRE error for {key}: {e}")
            return False

    def ttl(self, key: str) -> int:
        """Get the time to live for a key in seconds."""
        if not self.enabled or not self.client:
            return -2

        try:
            ttl_value = self.client.ttl(key)
            return ttl_value  # -2 if key doesn't exist, -1 if no TTL
        except Exception as e:
            if logger_import:
                logger.error(f"Redis TTL error for {key}: {e}")
            return -2

    def incr(self, key: str) -> int:
        """Increment a key's value by 1."""
        if not self.enabled or not self.client:
            return 0

        try:
            result = self.client.incr(key)
            return int(result)
        except Exception as e:
            if logger_import:
                logger.error(f"Redis INCR error for {key}: {e}")
            return 0

    def ping(self) -> bool:
        """Ping the Redis server."""
        if not self.enabled or not self.client:
            return False

        try:
            response = self.client.ping()
            return bool(response)
        except Exception as e:
            if logger_import:
                logger.error(f"Redis PING error: {e}")
            return False


# Create a singleton instance
redis_client = RedisClient()
