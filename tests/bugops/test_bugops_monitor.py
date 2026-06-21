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
    import asyncio

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_ENABLED = True

    mock_async_db = AsyncMock(spec=AsyncIOMotorDatabase)

    with patch.object(mongo_manager, 'initialize', new_callable=AsyncMock, return_value=True):
        with patch.object(mongo_manager, 'get_async_database', new_callable=AsyncMock, return_value=mock_async_db):
            with patch.object(mongo_manager, 'aclose', new_callable=AsyncMock):
                with patch.object(monitor, '_poll_signals', new_callable=AsyncMock):
                    with patch.object(monitor, '_poll_freshness_detectors', new_callable=AsyncMock):
                        with patch.object(monitor, '_run_auto_resolution', new_callable=AsyncMock):
                            with patch.object(monitor, '_run_evidence_collection', new_callable=AsyncMock):
                                # Patch sleep to immediately stop after one iteration
                                with patch.object(asyncio, 'sleep', new_callable=AsyncMock, side_effect=lambda *args: monitor.stop()):
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


@pytest.mark.asyncio
async def test_run_evidence_collection_queries_store():
    """Test that _run_evidence_collection queries get_cases_without_evidence."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor

    monitor = BugOpsMonitor()
    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = []

    await monitor._run_evidence_collection()

    monitor.store.get_cases_without_evidence.assert_called_once()


@pytest.mark.asyncio
async def test_run_evidence_collection_checks_eligibility():
    """Test that _run_evidence_collection calls is_eligible for each case."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    fake_case = BugCase(
        case_id="TEST-EV-001",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-001",
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [fake_case]
    monitor.evidence_collector.is_eligible.return_value = False

    await monitor._run_evidence_collection()

    monitor.evidence_collector.is_eligible.assert_called_once_with(fake_case)


@pytest.mark.asyncio
async def test_run_evidence_collection_skips_ineligible_cases():
    """Test that _run_evidence_collection skips ineligible cases."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    fake_case = BugCase(
        case_id="TEST-EV-002",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-002",
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [fake_case]
    monitor.evidence_collector.is_eligible.return_value = False

    await monitor._run_evidence_collection()

    # collect should NOT be called for ineligible cases
    monitor.evidence_collector.collect.assert_not_called()


@pytest.mark.asyncio
async def test_run_evidence_collection_calls_collect_for_eligible_cases():
    """Test that _run_evidence_collection calls collect for eligible cases."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus, EvidencePack, EvidencePackStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    fake_case = BugCase(
        case_id="TEST-EV-003",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-003",
        created_at=datetime.utcnow(),
    )

    fake_pack = EvidencePack(
        pack_id="ep_test_123",
        bugcase_id="TEST-EV-003",
        collection_status=EvidencePackStatus.COMPLETE,
        sections_collected=["metrics"],
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [fake_case]
    monitor.evidence_collector.is_eligible.return_value = True
    monitor.evidence_collector.collect.return_value = fake_pack

    await monitor._run_evidence_collection()

    monitor.evidence_collector.collect.assert_called_once_with(fake_case)


@pytest.mark.asyncio
async def test_run_evidence_collection_sends_notification_for_complete_packs():
    """Test that _run_evidence_collection sends Slack notification for COMPLETE packs."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus, EvidencePack, EvidencePackStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    fake_case = BugCase(
        case_id="TEST-EV-004",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-004",
        created_at=datetime.utcnow(),
    )

    fake_pack = EvidencePack(
        pack_id="ep_test_124",
        bugcase_id="TEST-EV-004",
        collection_status=EvidencePackStatus.COMPLETE,
        sections_collected=["metrics"],
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [fake_case]
    monitor.evidence_collector.is_eligible.return_value = True
    monitor.evidence_collector.collect.return_value = fake_pack

    with patch('crypto_news_aggregator.bugops.slack.send_evidence_collected_notification', new_callable=AsyncMock) as mock_notify:
        await monitor._run_evidence_collection()
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_run_evidence_collection_does_not_notify_for_partial_packs():
    """Test that _run_evidence_collection does NOT send Slack notification for PARTIAL packs."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus, EvidencePack, EvidencePackStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    monitor.settings.BUGOPS_SLACK_ENABLED = True
    fake_case = BugCase(
        case_id="TEST-EV-005",
        title="Test case",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-005",
        created_at=datetime.utcnow(),
    )

    fake_pack = EvidencePack(
        pack_id="ep_test_125",
        bugcase_id="TEST-EV-005",
        collection_status=EvidencePackStatus.PARTIAL,
        sections_collected=["metrics"],
        sections_missing=[{"collector_name": "logs", "reason": "API timeout"}],
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [fake_case]
    monitor.evidence_collector.is_eligible.return_value = True
    monitor.evidence_collector.collect.return_value = fake_pack

    with patch('crypto_news_aggregator.bugops.slack.send_evidence_collected_notification', new_callable=AsyncMock) as mock_notify:
        await monitor._run_evidence_collection()
        mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_run_evidence_collection_handles_errors_gracefully():
    """Test that _run_evidence_collection handles errors gracefully and continues."""
    from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
    from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
    from datetime import datetime

    monitor = BugOpsMonitor()
    case1 = BugCase(
        case_id="TEST-EV-006",
        title="Case 1",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-006",
        created_at=datetime.utcnow(),
    )
    case2 = BugCase(
        case_id="TEST-EV-007",
        title="Case 2",
        summary="Test summary",
        severity=AlertSeverity.WARNING,
        status=CaseStatus.OPEN,
        source_types=["test"],
        alert_type="test_alert",
        dedupe_key="test-dedupe-007",
        created_at=datetime.utcnow(),
    )

    monitor.store = AsyncMock()
    monitor.evidence_collector = AsyncMock()
    monitor.store.get_cases_without_evidence.return_value = [case1, case2]

    # First case fails, second succeeds
    monitor.evidence_collector.is_eligible.side_effect = [Exception("Test error"), True]

    # Should NOT raise
    await monitor._run_evidence_collection()

    # Both cases should have been attempted
    assert monitor.evidence_collector.is_eligible.call_count == 2
