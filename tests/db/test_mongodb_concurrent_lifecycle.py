"""
Behavioral tests for MongoDB MongoManager concurrent lifecycle safety.

Verifies deterministic behavior under:
- Concurrent initialization
- Ping failure during initialization
- Loop changes (Celery worker scenario)
- Close/recreate overlap
- Cancellation and interrupt handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from crypto_news_aggregator.db.mongodb import MongoManager


class MockAsyncClient:
    """Mock Motor client that allows controlling ping behavior."""

    def __init__(self, ping_result=None, ping_delay=0.01, ping_error=None):
        self.ping_result = ping_result
        self.ping_delay = ping_delay
        self.ping_error = ping_error
        self.close_called = False
        self.admin = MagicMock()
        self.closed = False

    async def ping(self):
        """Simulate ping with optional delay and error."""
        if self.ping_delay:
            await asyncio.sleep(self.ping_delay)
        if self.ping_error:
            raise self.ping_error
        return self.ping_result

    def close(self):
        """Mark as closed."""
        self.close_called = True
        self.closed = True


def _make_ping_side_effect(client: "MockAsyncClient"):
    """Returns an async function suitable as AsyncMock(side_effect=...) that
    actually awaits client.ping() (including its ping_delay).

    AsyncMock(side_effect=<sync function returning a coroutine>) does NOT
    await the returned coroutine -- it hands the coroutine object straight
    back, so a caller doing `await mock(...)` gets the coroutine's return
    value skipped entirely and the coroutine itself is never run (Python
    emits "coroutine was never awaited"). This silently defeated the
    intended ping_delay in every test that used
    `AsyncMock(side_effect=lambda *a, **kw: client.ping())` -- the delay
    never actually happened, though the affected tests still passed
    because their assertions (single-creation counts) held regardless of
    timing. Discovered while adding aclose()/close() lock-coordination
    tests (BUG-108 review finding 3) that DO depend on the delay actually
    elapsing. Using an `async def` side_effect (which AsyncMock does
    correctly await) fixes this.
    """

    async def _side_effect(*args, **kwargs):
        return await client.ping()

    return _side_effect


@pytest.fixture
def fresh_manager():
    """Fresh MongoManager instance for each test."""
    manager = MongoManager()
    manager._async_client = None
    manager._client_loop = None
    manager._initialized = False
    manager._connection_uri = "mongodb://test/crypto_news"
    manager._connection_kwargs = {"maxPoolSize": 10}
    return manager


@pytest.mark.asyncio
async def test_concurrent_get_async_client_single_creation(fresh_manager):
    """Verify that concurrent get_async_client() calls create only one client.

    Two tasks calling get_async_client() concurrently should:
    1. Both see needs_recreation = True initially
    2. Only one creates the Motor client
    3. Both receive the same client instance
    """
    manager = fresh_manager
    creation_count = 0

    def counting_motor_client(*args, **kwargs):
        # AsyncIOMotorClient(...) is called synchronously in production code
        # (it is a constructor, not awaited) -- side_effect must therefore be
        # a plain sync function returning the mock client directly, not an
        # `async def`, which would make this call return an unawaited
        # coroutine instead of the client.
        nonlocal creation_count
        creation_count += 1
        client = MockAsyncClient()
        client.admin.command = AsyncMock(return_value=None)
        return client

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=counting_motor_client), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Launch concurrent calls
        results = await asyncio.gather(
            manager.get_async_client(),
            manager.get_async_client(),
            manager.get_async_client(),
        )

        # All should get the same client
        assert results[0] is results[1], "Concurrent callers should receive same client"
        assert results[1] is results[2], "All concurrent callers should receive same client"

        # Only one creation should occur (or 2 if there's a race, but not 3)
        assert creation_count == 1, f"Client created {creation_count} times; the lock in get_async_client() should serialize concurrent creation to exactly 1"


@pytest.mark.asyncio
async def test_ping_failure_clears_client_and_loop_before_raising(fresh_manager):
    """Verify ping failure does not leave stale client or loop reference.

    If ping fails:
    1. Both _async_client and _client_loop should be None
    2. Failed client should be closed
    3. Exception should propagate
    4. Retry should be able to create new client
    """
    manager = fresh_manager
    ping_error = ConnectionError("Connection refused")

    client1 = MockAsyncClient(ping_error=ping_error)
    client1.admin.command = AsyncMock(side_effect=ping_error)

    client2 = MockAsyncClient()  # For retry
    client2.admin.command = AsyncMock(return_value=None)

    client_sequence = [client1, client2]
    creation_index = [0]

    def motor_client_creator(*args, **kwargs):
        result = client_sequence[creation_index[0]]
        if creation_index[0] < len(client_sequence) - 1:
            creation_index[0] += 1
        return result

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=motor_client_creator), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # First call fails on ping
        with pytest.raises(ConnectionError):
            await manager.get_async_client()

        # State should be fully cleared
        assert manager._async_client is None, "Client should be None after ping failure"
        assert manager._client_loop is None, "Loop should be None after ping failure"
        assert client1.close_called, "Failed client should be closed"

        # Retry should succeed with new client
        client = await manager.get_async_client()
        assert client is client2, "Should get new client on retry"
        assert manager._async_client is client2, "Should store new client"
        assert manager._client_loop is not None, "Loop should be set after successful retry"


@pytest.mark.asyncio
async def test_concurrent_calls_during_ping_wait(fresh_manager):
    """Verify concurrent callers during ping don't create overlapping clients.

    Scenario:
    1. Task A starts creation, awaits ping (takes 0.1s)
    2. Task B arrives during ping, sees needs_recreation=True
    3. Task B should wait or skip, not create second client
    4. Both receive same client after ping completes
    """
    manager = fresh_manager
    creation_count = 0
    ping_delay = 0.05  # 50ms ping delay

    def motor_client_with_delay(*args, **kwargs):
        # Sync factory (see counting_motor_client above for why): the ping
        # delay is simulated inside MockAsyncClient.ping(), which IS awaited
        # by production code, so the delay still takes effect.
        nonlocal creation_count
        creation_count += 1
        client = MockAsyncClient(ping_delay=ping_delay)
        client.admin.command = AsyncMock(
            side_effect=_make_ping_side_effect(client)
        )
        return client

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=motor_client_with_delay), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Launch 5 concurrent calls (to stress test)
        results = await asyncio.gather(
            manager.get_async_client(),
            manager.get_async_client(),
            manager.get_async_client(),
            manager.get_async_client(),
            manager.get_async_client(),
        )

        # All should receive the same client
        first_client = results[0]
        for i, client in enumerate(results[1:], 1):
            assert client is first_client, f"Call {i+1} got different client"

        # Creation should be minimal (1-2 due to timing, not 5)
        assert creation_count == 1, f"Created {creation_count} clients; concurrent callers during ping wait should serialize to exactly 1 creation"


@pytest.mark.asyncio
async def test_loop_change_detected_and_client_recreated(fresh_manager):
    """Verify loop change triggers recreation deterministically.

    When event loop changes (e.g., Celery worker):
    1. Previous _client_loop != current_loop
    2. Needs recreation = True
    3. Old client closed, new client created
    4. New loop stored
    """
    manager = fresh_manager

    client1 = MockAsyncClient()
    client1.admin.command = AsyncMock(return_value=None)
    client1.close = MagicMock()

    client2 = MockAsyncClient()
    client2.admin.command = AsyncMock(return_value=None)

    client_sequence = [client1, client2]
    creation_index = [0]

    def motor_client_creator(*args, **kwargs):
        result = client_sequence[creation_index[0]]
        if creation_index[0] < len(client_sequence) - 1:
            creation_index[0] += 1
        return result

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=motor_client_creator), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Get client in first loop
        loop1 = asyncio.get_running_loop()
        client_first = await manager.get_async_client()
        assert client_first is client1
        assert manager._client_loop is loop1

        # Simulate loop change (in real code, this happens when Celery switches event loops)
        # For testing, we simulate by setting a mock loop
        fake_loop = MagicMock()
        fake_loop.is_closed.return_value = False
        manager._client_loop = fake_loop  # Simulate loop change

        # Next call should detect loop change and recreate
        client_second = await manager.get_async_client()

        # Should get new client
        assert client_second is client2, "Should create new client for new loop"
        # Old client should be closed. client1.close was replaced with a
        # MagicMock() above (to allow asserting it was called), which no
        # longer sets close_called -- assert on the mock call instead.
        client1.close.assert_called_once()
        # Loop reference should be updated
        assert manager._client_loop is loop1, "Should track new loop"


@pytest.mark.asyncio
async def test_client_shared_across_concurrent_database_operations(fresh_manager):
    """Verify that same client instance is used across concurrent DB calls.

    Multiple concurrent database operations should all use the same
    Motor client, not create separate ones.
    """
    manager = fresh_manager
    creation_count = 0

    def counting_motor_client(*args, **kwargs):
        # Sync factory: see the note in test_concurrent_get_async_client_single_creation.
        nonlocal creation_count
        creation_count += 1
        client = MockAsyncClient()
        client.admin.command = AsyncMock(return_value=None)
        return client

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=counting_motor_client), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()

        # Simulate multiple concurrent database operations
        # Each calls get_async_client() as part of its work
        async def db_operation(op_id):
            client = await manager.get_async_client()
            await asyncio.sleep(0.01)  # Simulate DB work
            return (op_id, client)

        results = await asyncio.gather(
            db_operation(1),
            db_operation(2),
            db_operation(3),
        )

        # All operations should use same client
        first_client = results[0][1]
        for op_id, client in results[1:]:
            assert client is first_client, f"Operation {op_id} got different client"

        # Only one client should be created
        assert creation_count == 1, f"Created {creation_count} clients, expected 1"


@pytest.mark.asyncio
async def test_aclose_does_not_close_client_created_during_the_call(fresh_manager):
    """Verify aclose() and get_async_client() are serialized against each
    other (BUG-108 review finding 3).

    aclose() sleeps 0.1s inside its lock (asyncio.sleep(0.1), an existing
    production behavior -- "give the client a moment to close connections")
    and get_async_client()'s mocked ping sleeps 0.05s inside its own lock
    acquisition. If _async_lock truly serializes them, total wall-clock
    time for running both concurrently must be close to the SUM of the two
    delays (~0.15s) -- if the lock were absent (or a no-op), both critical
    sections would run concurrently and total time would be close to the
    MAX of the two delays (~0.1s) instead. This is a much more reliable
    signal than comparing wall-clock timestamps of when each coroutine
    merely started (both start at ~the same instant regardless of the
    lock; what matters is when each enters its critical section, which
    per-coroutine timestamps can't distinguish from lock-queueing time).
    Verified empirically: this test fails when the lock is removed from
    aclose() (elapsed ~0.1s, below the 0.13s threshold) and passes with it
    present (elapsed ~0.15s).
    """
    manager = fresh_manager

    def counting_motor_client(*args, **kwargs):
        client = MockAsyncClient(ping_delay=0.05)
        client.admin.command = AsyncMock(side_effect=_make_ping_side_effect(client))
        return client

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=counting_motor_client), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()
        first_client = await manager.get_async_client()

        async def get_client_after_forcing_recreation():
            # Force _async_client to None so get_async_client() must go
            # through the (locked) recreation path concurrently with
            # aclose(), rather than short-circuiting via the
            # needs_recreation fast-path check outside the lock.
            manager._async_client = None
            manager._client_loop = None
            return await manager.get_async_client()

        start = asyncio.get_event_loop().time()
        results = await asyncio.gather(manager.aclose(), get_client_after_forcing_recreation())
        elapsed = asyncio.get_event_loop().time() - start
        second_client = results[1]

        assert elapsed >= 0.13, (
            f"aclose() (0.1s internal sleep) and get_async_client() (0.05s "
            f"mocked ping) took only {elapsed:.3f}s combined -- expected "
            f"~0.15s if _async_lock serialized them; this low an elapsed "
            f"time indicates they ran concurrently instead"
        )
        assert manager._async_client is second_client
        assert second_client.close_called is False


@pytest.mark.asyncio
async def test_close_serializes_against_get_async_client(fresh_manager):
    """Same coordination guarantee as aclose(), but for close() (which also
    tears down the sync client and _initialized).

    Unlike aclose(), close()'s async-client section has no internal delay
    to build a sum-of-delays timing proof on (see
    test_aclose_does_not_close_client_created_during_the_call for that
    approach). Instead, this test holds the manager's lock directly (the
    same lock object close() and get_async_client() both acquire via
    _get_async_lock()) and verifies get_async_client() genuinely blocks
    until the lock is released, then completes correctly afterward --
    proving mutual exclusion directly rather than inferring it from timing.
    """
    manager = fresh_manager

    def counting_motor_client(*args, **kwargs):
        client = MockAsyncClient(ping_delay=0.01)
        client.admin.command = AsyncMock(side_effect=_make_ping_side_effect(client))
        return client

    with patch('crypto_news_aggregator.db.mongodb.AsyncIOMotorClient', side_effect=counting_motor_client), \
         patch('crypto_news_aggregator.db.mongodb.get_settings') as mock_settings:

        mock_settings.return_value.MONGODB_URI = "mongodb://test/crypto_news"
        mock_settings.return_value.MONGODB_MAX_POOL_SIZE = 10
        mock_settings.return_value.MONGODB_MIN_POOL_SIZE = 1

        await manager.initialize()
        first_client = await manager.get_async_client()
        assert first_client.close_called is False

        lock = manager._get_async_lock()
        await lock.acquire()
        try:
            # Force recreation so get_async_client() must go through the
            # locked section rather than short-circuiting via the
            # needs_recreation fast-path check (which runs before the lock
            # is even attempted, and correctly does not block).
            manager._async_client = None
            manager._client_loop = None
            get_client_task = asyncio.create_task(manager.get_async_client())
            await asyncio.sleep(0.05)
            assert not get_client_task.done(), (
                "get_async_client() must block while close()'s (and, here, "
                "the test's own) lock is held, not proceed unfenced"
            )
        finally:
            lock.release()

        second_client = await get_client_task
        assert second_client is not None

        # Now verify close() itself actually acquires and releases this
        # same lock as part of its normal operation (not a different lock
        # instance), by holding the lock again and confirming close()
        # blocks too.
        await lock.acquire()
        try:
            close_task = asyncio.create_task(manager.close())
            await asyncio.sleep(0.05)
            assert not close_task.done(), "close() must block while the lock is held"
        finally:
            lock.release()

        await close_task
        assert manager._async_client is None
        assert manager._initialized is False


def test_duplicate_key_error_index_detection():
    """Verify we can detect URL vs other unique index violations."""
    from pymongo.errors import DuplicateKeyError

    # URL unique constraint violation
    url_error = DuplicateKeyError("E11000 duplicate key error")
    url_error._OperationFailure__details = {
        'index': 'url_unique',
        'keyPattern': {'url': 1}
    }

    # Check that we extract index correctly
    violated_index = url_error._OperationFailure__details.get('index') if hasattr(url_error, '_OperationFailure__details') else None
    assert violated_index == 'url_unique' or 'url' in str(violated_index).lower(), "Should identify URL constraint"

    # Different unique constraint
    other_error = DuplicateKeyError("E11000 duplicate key error")
    other_error._OperationFailure__details = {
        'index': 'fingerprint_unique',
        'keyPattern': {'fingerprint': 1}
    }

    other_index = other_error._OperationFailure__details.get('index') if hasattr(other_error, '_OperationFailure__details') else None
    assert other_index != 'url_unique', "Should not confuse other indexes with URL"
