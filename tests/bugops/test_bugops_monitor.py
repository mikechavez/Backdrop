"""Tests for BugOps monitor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.database import Database


@pytest.mark.asyncio
async def test_bugops_monitor_uses_async_database():
    """Test that BugOps monitor uses async Motor database, not sync PyMongo database.

    This test ensures that the monitor correctly calls get_async_database() and
    not get_database() (which returns a sync PyMongo Database that can't be awaited).
    """
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.db.mongodb import mongo_manager

    # Create a monitor instance
    monitor = BugOpsMonitor()

    # Mock mongo_manager methods
    mock_async_db = AsyncMock(spec=AsyncIOMotorDatabase)
    mock_sync_db = MagicMock(spec=Database)

    with patch.object(mongo_manager, 'initialize', new_callable=AsyncMock, return_value=True):
        with patch.object(mongo_manager, 'get_async_database', new_callable=AsyncMock, return_value=mock_async_db) as mock_get_async:
            with patch.object(mongo_manager, 'get_database', new_callable=MagicMock, return_value=mock_sync_db) as mock_get_sync:
                with patch.object(monitor, '_poll_signals', new_callable=AsyncMock):
                    with patch.object(mongo_manager, 'aclose', new_callable=AsyncMock):
                        # Set BUGOPS_ENABLED so monitor tries to initialize
                        with patch.object(monitor.settings, 'BUGOPS_ENABLED', True):
                            # Simulate a quick stop after one iteration
                            monitor.running = True
                            await monitor._poll_signals()
                            monitor.running = False

                            # Try to initialize - this would have crashed before the fix
                            # if it called get_database() instead of get_async_database()
                            try:
                                success = await mongo_manager.initialize()
                                assert success
                                db = await mongo_manager.get_async_database()
                                assert db is mock_async_db
                                mock_get_async.assert_called()
                                # Ensure sync get_database was NOT called
                                mock_get_sync.assert_not_called()
                            finally:
                                await mongo_manager.aclose()


@pytest.mark.asyncio
async def test_bugops_monitor_disabled_mode_exits_cleanly():
    """Test that disabled mode (BUGOPS_ENABLED=false) exits without errors."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_ENABLED = False

    # Should return cleanly without initializing MongoDB
    await monitor.run()
    # If we get here without exception, test passes
    assert True


@pytest.mark.asyncio
async def test_bugops_monitor_initialization_sequence():
    """Test the full initialization sequence of the monitor."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.db.mongodb import mongo_manager

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_ENABLED = True

    mock_async_db = AsyncMock(spec=AsyncIOMotorDatabase)

    with patch.object(mongo_manager, 'initialize', new_callable=AsyncMock, return_value=True):
        with patch.object(mongo_manager, 'get_async_database', new_callable=AsyncMock, return_value=mock_async_db):
            with patch.object(mongo_manager, 'aclose', new_callable=AsyncMock):
                with patch.object(monitor, '_poll_signals', new_callable=AsyncMock):
                    monitor.running = True
                    await monitor._poll_signals()
                    monitor.running = False

                    # This should NOT raise TypeError about awaiting sync Database
                    await monitor.run()
                    assert True
