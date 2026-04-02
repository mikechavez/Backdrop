import pytest
import json
from unittest.mock import patch, MagicMock
from src.crypto_news_aggregator.core.redis_rest_client import RedisClient


def test_redis_client_initialization():
    """Test that the Redis client initializes with correct URL."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        client = RedisClient(url="redis://localhost:6379/0")

        assert client.url == "redis://localhost:6379/0"
        assert client.enabled is True
        mock_redis.assert_called_once_with("redis://localhost:6379/0", decode_responses=True)


def test_redis_client_initialization_disabled_on_error():
    """Test that the Redis client disables gracefully on connection error."""
    with patch("redis.from_url") as mock_redis:
        mock_redis.side_effect = Exception("Connection failed")

        client = RedisClient(url="redis://localhost:6379/0")

        assert client.enabled is False
        assert client.client is None


def test_redis_client_ping():
    """Test the ping method of Redis client."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.ping()

        assert result is True
        mock_client.ping.assert_called()


def test_redis_client_ping_disabled():
    """Test ping returns False when Redis is disabled."""
    with patch("redis.from_url") as mock_redis:
        mock_redis.side_effect = Exception("Connection failed")
        client = RedisClient(url="redis://invalid:6379/0")
        result = client.ping()
        assert result is False


def test_redis_client_set_get():
    """Test set and get operations of Redis client."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.set.return_value = True
        mock_client.get.return_value = "test-value"

        client = RedisClient(url="redis://localhost:6379/0")
        set_result = client.set("test-key", "test-value")
        get_result = client.get("test-key")

        assert set_result is True
        assert get_result == "test-value"
        mock_client.set.assert_called_with("test-key", "test-value", ex=None)
        mock_client.get.assert_called_with("test-key")


def test_redis_client_set_with_ttl():
    """Test set with TTL (expiration)."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.set.return_value = True

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.set("test-key", "test-value", ex=3600)

        assert result is True
        mock_client.set.assert_called_with("test-key", "test-value", ex=3600)


def test_redis_client_set_json_serialization():
    """Test that non-string values are JSON serialized."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.set.return_value = True

        client = RedisClient(url="redis://localhost:6379/0")
        data = {"key": "value", "count": 42}
        client.set("test-key", data)

        # Verify JSON was serialized
        call_args = mock_client.set.call_args
        assert call_args[0][0] == "test-key"
        assert json.loads(call_args[0][1]) == data


def test_redis_client_get_json_deserialization():
    """Test that JSON strings are automatically deserialized on get."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        data = {"key": "value", "count": 42}
        mock_client.get.return_value = json.dumps(data)

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.get("test-key")

        assert result == data


def test_redis_client_delete():
    """Test delete operation of Redis client."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.delete.return_value = 1

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.delete("test-key")

        assert result == 1
        mock_client.delete.assert_called_with("test-key")


def test_redis_client_delete_multiple_keys():
    """Test deleting multiple keys at once."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.delete.return_value = 2

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.delete("key1", "key2")

        assert result == 2
        mock_client.delete.assert_called_with("key1", "key2")


def test_redis_client_incr():
    """Test increment operation."""
    with patch("redis.from_url") as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        mock_client.incr.return_value = 5

        client = RedisClient(url="redis://localhost:6379/0")
        result = client.incr("counter-key")

        assert result == 5
        mock_client.incr.assert_called_with("counter-key")
