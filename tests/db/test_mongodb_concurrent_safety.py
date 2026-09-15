"""
Behavioral tests for MongoDB MongoManager concurrent initialization safety.

Verifies that concurrent callers:
1. Create only one Motor client (not multiple)
2. Both receive the same client instance
3. Client and loop are assigned together (no race between assignment and check)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class FakeMotorClient:
    """Minimal Motor client mock for testing."""
    def __init__(self):
        self.admin = MagicMock()
        self.admin.command = AsyncMock(return_value=None)
        self._closed = False

    def close(self):
        self._closed = True


@pytest.mark.asyncio
async def test_concurrent_initialization_creates_one_client():
    """Verify only one Motor client created for concurrent get_async_client calls.

    This tests the core concurrency requirement: despite multiple concurrent
    calls, only one client should be created and both should receive it.
    """
    from crypto_news_aggregator.db.mongodb import MongoManager

    manager = MongoManager()
    manager._async_client = None
    manager._client_loop = None
    manager._initialized = False
    manager._connection_uri = "mongodb://test/crypto_news"
    manager._connection_kwargs = {"maxPoolSize": 10}

    creation_count = 0

    def mock_motor_factory(*args, **kwargs):
        nonlocal creation_count
        creation_count += 1
        return FakeMotorClient()

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=mock_motor_factory), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Launch 3 concurrent calls
        results = await asyncio.gather(
            manager.get_async_client(),
            manager.get_async_client(),
            manager.get_async_client(),
        )

        # All three should get the same client instance
        assert results[0] is results[1], "First two calls should get same client"
        assert results[1] is results[2], "All three calls should get same client"

        # Only one client should have been created
        assert creation_count == 1, f"Expected 1 client, got {creation_count}"


@pytest.mark.asyncio
async def test_client_and_loop_assigned_together():
    """Verify _async_client and _client_loop are set together after ping succeeds.

    This ensures no concurrent caller can see _client_loop=None while
    _async_client is set, which could cause unnecessary recreation.
    """
    from crypto_news_aggregator.db.mongodb import MongoManager
    import inspect

    manager = MongoManager()
    manager._connection_uri = "mongodb://test/crypto_news"
    manager._connection_kwargs = {}

    # Verify the code structure directly
    source = inspect.getsource(MongoManager.get_async_client)

    # Both assignments must occur in success path
    assert "self._async_client = new_client" in source
    assert "self._client_loop = current_loop" in source

    # Both assignments must be in the same success block (not separated by await)
    lines = source.split('\n')
    async_client_line = None
    client_loop_line = None

    for i, line in enumerate(lines):
        if 'self._async_client = new_client' in line:
            async_client_line = i
        if 'self._client_loop = current_loop' in line:
            client_loop_line = i

    # Verify both are in the ping-success path, close together
    assert async_client_line is not None, "Should assign _async_client"
    assert client_loop_line is not None, "Should assign _client_loop"

    # They should be within 3 lines of each other (no await between)
    assert abs(async_client_line - client_loop_line) <= 3, \
        "Assignments too far apart; concurrent caller could see inconsistent state"


@pytest.mark.asyncio
async def test_ping_failure_clears_both_references():
    """Verify ping failure clears both _async_client and _client_loop."""
    from crypto_news_aggregator.db.mongodb import MongoManager

    manager = MongoManager()
    manager._async_client = None
    manager._client_loop = None
    manager._initialized = False
    manager._connection_uri = "mongodb://test/crypto_news"
    manager._connection_kwargs = {}

    ping_error = ConnectionError("Connection refused")

    client_with_error = FakeMotorClient()
    client_with_error.admin.command = AsyncMock(side_effect=ping_error)

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', return_value=client_with_error), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Call should raise, leaving state clean
        with pytest.raises(ConnectionError):
            await manager.get_async_client()

        # Both must be None
        assert manager._async_client is None, "Client should be cleared"
        assert manager._client_loop is None, "Loop should be cleared"
        # Failed client should be closed
        assert client_with_error._closed, "Failed client should be closed"
