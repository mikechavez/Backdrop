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


@pytest.mark.asyncio
async def test_poll_signals_slack_disabled_no_nameerror():
    """Test that _poll_signals works with BUGOPS_SLACK_ENABLED=false without NameError."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = False
    monitor.settings.BUGOPS_ENABLED = True

    # Create a fake signal source
    mock_source = AsyncMock()
    fake_event = {"type": "cost_anomaly", "data": {}}
    mock_source.collect.return_value = [fake_event]
    monitor.signal_sources = [mock_source]

    # Create a fake case
    fake_case = BugCase(
        case_id="TEST-001",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-001",
        created_at=datetime.utcnow(),
    )

    # Mock the store
    monitor.store = AsyncMock()
    monitor.store.process_alert_event.return_value = (fake_case, True)

    # This should NOT raise NameError even though Slack is disabled
    with patch('crypto_news_aggregator.bugops.slack.send_case_notification') as mock_slack:
        await monitor._poll_signals()
        # Slack should NOT be called when disabled
        mock_slack.assert_not_called()


@pytest.mark.asyncio
async def test_poll_signals_slack_enabled_calls_notification():
    """Test that _poll_signals calls send_case_notification when BUGOPS_SLACK_ENABLED=true."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    monitor.settings.BUGOPS_ENABLED = True

    # Create a fake signal source
    mock_source = AsyncMock()
    fake_event = {"type": "cost_anomaly", "data": {}}
    mock_source.collect.return_value = [fake_event]
    monitor.signal_sources = [mock_source]

    # Create a fake case
    fake_case = BugCase(
        case_id="TEST-002",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.HIGH,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-002",
        created_at=datetime.utcnow(),
    )

    # Mock the store
    monitor.store = AsyncMock()
    monitor.store.process_alert_event.return_value = (fake_case, True)

    # Mock send_case_notification
    mock_send_notification = AsyncMock()

    with patch('crypto_news_aggregator.bugops.slack.send_case_notification', mock_send_notification):
        await monitor._poll_signals()
        # Slack should be called exactly once for the new case
        mock_send_notification.assert_called_once_with(fake_case)


@pytest.mark.asyncio
async def test_poll_signals_slack_not_called_for_existing_cases():
    """Test that _poll_signals does not call Slack for existing cases (is_new=False)."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    monitor.settings.BUGOPS_ENABLED = True

    # Create a fake signal source
    mock_source = AsyncMock()
    fake_event = {"type": "cost_anomaly", "data": {}}
    mock_source.collect.return_value = [fake_event]
    monitor.signal_sources = [mock_source]

    # Create a fake case
    fake_case = BugCase(
        case_id="TEST-003",
        title="Existing case",
        summary="Test summary",
        severity=AlertSeverity.INFO,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-003",
        created_at=datetime.utcnow(),
    )

    # Mock the store with is_new=False
    monitor.store = AsyncMock()
    monitor.store.process_alert_event.return_value = (fake_case, False)

    mock_send_notification = AsyncMock()

    with patch('crypto_news_aggregator.bugops.slack.send_case_notification', mock_send_notification):
        await monitor._poll_signals()
        # Slack should NOT be called for existing cases
        mock_send_notification.assert_not_called()


@pytest.mark.asyncio
async def test_poll_signals_slack_failure_does_not_crash():
    """Test that Slack notification failure does not crash the monitor."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    monitor.settings.BUGOPS_ENABLED = True

    # Create a fake signal source
    mock_source = AsyncMock()
    fake_event = {"type": "cost_anomaly", "data": {}}
    mock_source.collect.return_value = [fake_event]
    monitor.signal_sources = [mock_source]

    # Create a fake case
    fake_case = BugCase(
        case_id="TEST-004",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.CRITICAL,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-004",
        created_at=datetime.utcnow(),
    )

    # Mock the store
    monitor.store = AsyncMock()
    monitor.store.process_alert_event.return_value = (fake_case, True)

    # Mock send_case_notification to raise an exception
    mock_send_notification = AsyncMock(side_effect=Exception("Slack API error"))

    with patch('crypto_news_aggregator.bugops.slack.send_case_notification', mock_send_notification):
        # This should NOT raise - monitor should catch and log the error
        await monitor._poll_signals()
        # Verify Slack was attempted
        mock_send_notification.assert_called_once_with(fake_case)


@pytest.mark.asyncio
async def test_poll_signals_slack_returns_false_is_logged():
    """Test that Slack notification returning False is logged as a warning."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    monitor.settings.BUGOPS_ENABLED = True

    # Create a fake signal source
    mock_source = AsyncMock()
    fake_event = {"type": "cost_anomaly", "data": {}}
    mock_source.collect.return_value = [fake_event]
    monitor.signal_sources = [mock_source]

    # Create a fake case
    fake_case = BugCase(
        case_id="TEST-005",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.INFO,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-005",
        created_at=datetime.utcnow(),
    )

    # Mock the store
    monitor.store = AsyncMock()
    monitor.store.process_alert_event.return_value = (fake_case, True)

    # Mock send_case_notification to return False
    mock_send_notification = AsyncMock(return_value=False)

    with patch('crypto_news_aggregator.bugops.slack.send_case_notification', mock_send_notification):
        # This should NOT raise
        await monitor._poll_signals()
        # Verify Slack was attempted
        mock_send_notification.assert_called_once_with(fake_case)
