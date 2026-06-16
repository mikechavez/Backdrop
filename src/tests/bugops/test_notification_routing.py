"""Tests for BugOps notification routing logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.models import (
    BugCase,
    BugCaseCreate,
    AlertSeverity,
    CaseStatus,
)
from crypto_news_aggregator.bugops.slack import route_and_send_notification


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.update_notification_state = AsyncMock()
    return store


@pytest.fixture
def mock_settings():
    """Create mock settings with Slack enabled."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock:
        settings = MagicMock()
        settings.BUGOPS_SLACK_ENABLED = True
        settings.BUGOPS_NOTIFICATION_THROTTLE_MINUTES = 60
        mock.return_value = settings
        yield mock


@pytest.fixture
def high_bugcase():
    """Create a High severity BugCase."""
    return BugCase(
        case_id="bc_test_1",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="article_freshness",
        title="Article Freshness Failure",
        summary="No articles inserted for 42 minutes",
        dedupe_key="article_freshness:articles",
        source_types=["article_freshness"],
        root_subsystem="articles",
        blast_radius=["signals", "narratives", "briefings"],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        observation_count=1,
        detection_type="runtime",
        suggested_manual_check="Check RSS ingestion health",
        notification_count=0,
        last_notified_at=None,
        muted_until=None,
        snoozed_until=None,
    )


@pytest.fixture
def critical_bugcase():
    """Create a Critical severity BugCase."""
    return BugCase(
        case_id="bc_test_crit",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.CRITICAL,
        alert_type="signal_freshness",
        title="Signal Freshness Failure",
        summary="No signals generated",
        dedupe_key="signal_freshness:signals",
        source_types=["signal_freshness"],
        root_subsystem="signals",
        blast_radius=["narratives", "briefings"],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        observation_count=1,
        detection_type="startup",
        suggested_manual_check="Check signal worker health",
        notification_count=0,
        last_notified_at=None,
        muted_until=None,
        snoozed_until=None,
    )


@pytest.fixture
def medium_bugcase():
    """Create a Medium (WARNING) severity BugCase."""
    case = BugCase(
        case_id="bc_test_med",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.WARNING,
        alert_type="test_alert",
        title="Medium Issue",
        summary="A medium severity issue",
        dedupe_key="test:medium",
        source_types=["test"],
        root_subsystem="database",
        blast_radius=[],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        observation_count=1,
        detection_type="runtime",
        suggested_manual_check="Check logs",
        notification_count=0,
        last_notified_at=None,
        muted_until=None,
        snoozed_until=None,
    )
    return case


@pytest.fixture
def low_bugcase():
    """Create a Low (INFO) severity BugCase."""
    return BugCase(
        case_id="bc_test_low",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.INFO,
        alert_type="test_alert",
        title="Low Severity Issue",
        summary="A low severity issue",
        dedupe_key="test:low",
        source_types=["test"],
        root_subsystem="worker",
        blast_radius=[],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        observation_count=1,
        detection_type="runtime",
        suggested_manual_check=None,
        notification_count=0,
        last_notified_at=None,
        muted_until=None,
        snoozed_until=None,
    )


class TestNotificationRouting:
    """Test notification routing decisions."""

    @pytest.mark.asyncio
    async def test_critical_bugcase_created_sends_slack(self, critical_bugcase, mock_store, mock_settings):
        """Critical BugCase creation should send Slack."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(critical_bugcase, "bugcase_created", mock_store)
            assert result == "sent"
            mock_send.assert_called_once()
            mock_store.update_notification_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_bugcase_created_sends_slack(self, high_bugcase, mock_store, mock_settings):
        """High BugCase creation should send Slack."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "sent"
            mock_send.assert_called_once()
            mock_store.update_notification_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_bugcase_created_logs_digest_intent(self, medium_bugcase, mock_store, mock_settings):
        """Medium BugCase creation should log digest intent and not send Slack."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(medium_bugcase, "bugcase_created", mock_store)
            assert result == "skipped"
            mock_send.assert_not_called()
            mock_store.update_notification_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_bugcase_created_no_slack(self, low_bugcase, mock_store, mock_settings):
        """Low BugCase creation should not send Slack."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(low_bugcase, "bugcase_created", mock_store)
            assert result == "skipped"
            mock_send.assert_not_called()
            mock_store.update_notification_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicate_already_notified(self, high_bugcase, mock_store, mock_settings):
        """BugCase with notification_count > 0 should not re-notify on bugcase_created."""
        high_bugcase.notification_count = 1
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "skipped"
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_severity_escalation_bypasses_dedup(self, high_bugcase, mock_store, mock_settings):
        """Severity escalation should bypass deduplication."""
        high_bugcase.notification_count = 1  # Already notified
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(high_bugcase, "severity_escalated", mock_store)
            assert result == "sent"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_reopen_bypasses_dedup_and_throttle(self, high_bugcase, mock_store, mock_settings):
        """Reopen should bypass deduplication and throttle."""
        high_bugcase.notification_count = 10
        high_bugcase.last_notified_at = datetime.utcnow() - timedelta(seconds=30)
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(high_bugcase, "bugcase_reopened", mock_store)
            assert result == "sent"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_throttle_within_window(self, high_bugcase, mock_store, mock_settings):
        """BugCase within throttle window should not notify."""
        high_bugcase.last_notified_at = datetime.utcnow() - timedelta(seconds=30)
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "skipped"
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_throttle_after_window(self, high_bugcase, mock_store, mock_settings):
        """BugCase after throttle window should notify."""
        # Default throttle is 60 minutes; set last_notified to 61 minutes ago
        high_bugcase.last_notified_at = datetime.utcnow() - timedelta(minutes=61)
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "sent"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_muted_bugcase_suppressed(self, high_bugcase, mock_store, mock_settings):
        """Muted BugCase should suppress notification but update last_notified_at."""
        high_bugcase.muted_until = datetime.utcnow() + timedelta(minutes=10)
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "suppressed"
            mock_send.assert_not_called()
            mock_store.update_notification_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_snoozed_bugcase_suppressed(self, high_bugcase, mock_store, mock_settings):
        """Snoozed BugCase should suppress notification but update last_notified_at."""
        high_bugcase.snoozed_until = datetime.utcnow() + timedelta(hours=2)
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "suppressed"
            mock_send.assert_not_called()
            mock_store.update_notification_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_failure_returns_failed(self, high_bugcase, mock_store, mock_settings):
        """Failed Slack send should return 'failed' status."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "failed"
            mock_store.update_notification_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_slack_disabled_returns_skipped(self, high_bugcase, mock_store):
        """With Slack disabled, should return 'skipped'."""
        with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = False
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "skipped"

    @pytest.mark.asyncio
    async def test_update_notification_state_called_on_success(self, high_bugcase, mock_store, mock_settings):
        """Update notification state should be called when notification is sent."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            mock_store.update_notification_state.return_value = high_bugcase
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "sent"
            assert mock_store.update_notification_state.called
            # Check that the call was made with case_id and a datetime
            call_args = mock_store.update_notification_state.call_args
            assert call_args[0][0] == "bc_test_1"
            assert isinstance(call_args[0][1], datetime)
