"""Tests for auto-resolution with Recovery Window."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
from crypto_news_aggregator.bugops.models import BugCase, CaseStatus, AlertSeverity


@pytest.fixture
def mock_store():
    """Mock BugOpsStore."""
    store = AsyncMock()
    store.update_recovery_candidate = AsyncMock()
    store.resolve_case = AsyncMock()
    store.get_open_freshness_cases = AsyncMock()
    return store


@pytest.fixture
def mock_detector():
    """Mock freshness detector."""
    detector = AsyncMock()
    detector.check_recovery = AsyncMock()
    detector.root_subsystem = "articles"
    return detector


@pytest.fixture
def sample_case(now: datetime) -> BugCase:
    """Create a sample open BugCase."""
    return BugCase(
        case_id="bc_articles_123",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="article_freshness",
        title="Article Freshness Failure",
        summary="No articles inserted for 60 minutes.",
        dedupe_key="article_freshness:articles",
        source_types=["article_freshness"],
        root_subsystem="articles",
        blast_radius=["signals", "narratives", "briefings"],
        affected_subsystems=[],
        observation_count=1,
        detection_type="runtime",
        recovery_candidate_at=None,
    )


@pytest.fixture
def now():
    """Current timestamp."""
    return datetime.utcnow()


@pytest.mark.asyncio
async def test_recovery_condition_met_first_time_sets_candidate(
    mock_store, mock_detector, sample_case, now
):
    """Recovery condition met for first time → update_recovery_candidate() called."""
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}

    await monitor._run_auto_resolution()

    # Should set recovery_candidate_at to now
    mock_store.update_recovery_candidate.assert_called_once()
    call_args = mock_store.update_recovery_candidate.call_args
    assert call_args[0][0] == "bc_articles_123"
    # Recovery candidate should be set to approximately now
    assert isinstance(call_args[0][1], datetime)

    # resolve_case should NOT be called yet
    mock_store.resolve_case.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_condition_met_window_not_elapsed(
    mock_store, mock_detector, sample_case, now
):
    """Recovery condition met, window NOT elapsed → case stays open, no resolve."""
    sample_case.recovery_candidate_at = now - timedelta(minutes=5)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    await monitor._run_auto_resolution()

    # Should NOT call resolve or update_recovery_candidate
    mock_store.resolve_case.assert_not_called()
    mock_store.update_recovery_candidate.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_condition_met_window_elapsed(
    mock_store, mock_detector, sample_case, now
):
    """Recovery condition met, window elapsed → resolve_case() called."""
    sample_case.recovery_candidate_at = now - timedelta(minutes=15)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    await monitor._run_auto_resolution()

    # Should call resolve_case
    mock_store.resolve_case.assert_called_once_with("bc_articles_123")

    # Should NOT call update_recovery_candidate
    mock_store.update_recovery_candidate.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_fails_before_window_elapses(
    mock_store, mock_detector, sample_case, now
):
    """Failure recurs before window elapses → recovery_candidate cleared."""
    sample_case.recovery_candidate_at = now - timedelta(minutes=5)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = False

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}

    await monitor._run_auto_resolution()

    # Should clear recovery_candidate_at
    mock_store.update_recovery_candidate.assert_called_once_with("bc_articles_123", None)

    # Should NOT resolve
    mock_store.resolve_case.assert_not_called()


@pytest.mark.asyncio
async def test_no_slack_notification_on_resolution(
    mock_store, mock_detector, sample_case, now
):
    """No Slack notification sent on auto-resolution."""
    sample_case.recovery_candidate_at = now - timedelta(minutes=15)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    with patch("crypto_news_aggregator.bugops.slack.send_case_notification") as mock_slack:
        await monitor._run_auto_resolution()

        # Slack should NOT be called
        mock_slack.assert_not_called()


@pytest.mark.asyncio
async def test_manually_closed_case_skipped(
    mock_store, mock_detector, sample_case
):
    """Manually closed case (status=closed) skipped — check_recovery() not called."""
    sample_case.status = CaseStatus.CLOSED
    mock_store.get_open_freshness_cases.return_value = [sample_case]

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}

    await monitor._run_auto_resolution()

    # check_recovery() should NOT be called
    mock_detector.check_recovery.assert_not_called()

    # No store updates
    mock_store.resolve_case.assert_not_called()
    mock_store.update_recovery_candidate.assert_not_called()


@pytest.mark.asyncio
async def test_muted_case_resolves_normally(
    mock_store, mock_detector, sample_case, now
):
    """Muted case (muted_until in future) resolves normally."""
    sample_case.muted_until = now + timedelta(hours=1)
    sample_case.recovery_candidate_at = now - timedelta(minutes=15)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    await monitor._run_auto_resolution()

    # Should resolve despite muted_until being set
    mock_store.resolve_case.assert_called_once_with("bc_articles_123")


@pytest.mark.asyncio
async def test_snoozed_case_resolves_normally(
    mock_store, mock_detector, sample_case, now
):
    """Snoozed case (snoozed_until in future) resolves normally."""
    sample_case.snoozed_until = now + timedelta(hours=1)
    sample_case.recovery_candidate_at = now - timedelta(minutes=15)
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    await monitor._run_auto_resolution()

    # Should resolve despite snoozed_until being set
    mock_store.resolve_case.assert_called_once_with("bc_articles_123")


@pytest.mark.asyncio
async def test_detector_not_found_warning_logged(
    mock_store, sample_case
):
    """Detector not found for root_subsystem → warning logged, case skipped."""
    sample_case.root_subsystem = "unknown_subsystem"
    mock_store.get_open_freshness_cases.return_value = [sample_case]

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {}

    with patch("crypto_news_aggregator.bugops.monitor.logger") as mock_logger:
        await monitor._run_auto_resolution()

        # Should log warning
        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "No detector found" in args[0]
        assert "unknown_subsystem" in args[0]


@pytest.mark.asyncio
async def test_check_recovery_exception_logged(
    mock_store, mock_detector, sample_case
):
    """check_recovery() raises exception → error logged, loop continues."""
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.side_effect = ValueError("DB connection failed")

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}

    with patch("crypto_news_aggregator.bugops.monitor.logger") as mock_logger:
        await monitor._run_auto_resolution()

        # Should log error
        mock_logger.error.assert_called_once()
        args = mock_logger.error.call_args[0]
        assert "Recovery check failed" in args[0]

        # Should NOT call resolve or update
        mock_store.resolve_case.assert_not_called()
        mock_store.update_recovery_candidate.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_cases_processed(
    mock_store, mock_detector, sample_case, now
):
    """Multiple open cases processed in sequence."""
    case1 = sample_case
    case1.recovery_candidate_at = now - timedelta(minutes=15)

    case2 = BugCase(
        case_id="bc_signals_456",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="signal_freshness",
        title="Signal Freshness Failure",
        summary="No signals generated for 90 minutes.",
        dedupe_key="signal_freshness:signals",
        source_types=["signal_freshness"],
        root_subsystem="signals",
        blast_radius=["narratives", "briefings"],
        affected_subsystems=[],
        observation_count=2,
        detection_type="runtime",
        recovery_candidate_at=now - timedelta(minutes=5),
    )

    mock_store.get_open_freshness_cases.return_value = [case1, case2]
    mock_detector.check_recovery.return_value = True

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector, "signals": mock_detector}
    monitor.settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10

    await monitor._run_auto_resolution()

    # case1 should be resolved (window elapsed)
    # case2 should not be resolved (window not elapsed)
    assert mock_store.resolve_case.call_count == 1
    mock_store.resolve_case.assert_called_with("bc_articles_123")


@pytest.mark.asyncio
async def test_recovery_candidate_not_set_remains_none(
    mock_store, mock_detector, sample_case
):
    """No recovery candidate set and recovery fails → no action."""
    sample_case.recovery_candidate_at = None
    mock_store.get_open_freshness_cases.return_value = [sample_case]
    mock_detector.check_recovery.return_value = False

    monitor = BugOpsMonitor()
    monitor.store = mock_store
    monitor.detector_by_subsystem = {"articles": mock_detector}

    await monitor._run_auto_resolution()

    # Should NOT call resolve or update
    mock_store.resolve_case.assert_not_called()
    mock_store.update_recovery_candidate.assert_not_called()
