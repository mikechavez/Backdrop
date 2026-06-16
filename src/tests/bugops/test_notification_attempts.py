"""Tests for BugOps notification attempt persistence."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.models import (
    BugCase,
    AlertSeverity,
    CaseStatus,
    NotificationAttemptCreate,
)
from crypto_news_aggregator.bugops.slack import route_and_send_notification


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore with all required methods."""
    store = AsyncMock()
    store.update_notification_state = AsyncMock()
    store.update_last_notified_at_only = AsyncMock()
    store.create_notification_attempt = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_settings():
    """Create mock settings with Slack enabled."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock:
        settings = MagicMock()
        settings.BUGOPS_SLACK_ENABLED = True
        settings.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"
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


class TestNotificationAttemptPersistence:
    """Test notification attempt record persistence."""

    @pytest.mark.asyncio
    async def test_sent_attempt_persisted(self, high_bugcase, mock_store, mock_settings):
        """Successful Slack send should persist attempt record with status='sent'."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)

            assert result == "sent"
            # Verify attempt was persisted
            assert mock_store.create_notification_attempt.called
            call_args = mock_store.create_notification_attempt.call_args[0][0]
            assert call_args.bugcase_id == "bc_test_1"
            assert call_args.status == "sent"
            assert call_args.event_type == "bugcase_created"
            assert call_args.error_type is None
            assert call_args.error_message is None

    @pytest.mark.asyncio
    async def test_failed_attempt_persisted(self, high_bugcase, mock_store, mock_settings):
        """Failed Slack send should persist attempt record with status='failed'."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)

            assert result == "failed"
            # Verify attempt was persisted
            assert mock_store.create_notification_attempt.called
            call_args = mock_store.create_notification_attempt.call_args[0][0]
            assert call_args.bugcase_id == "bc_test_1"
            assert call_args.status == "failed"
            assert call_args.error_type == "UnknownError"
            assert call_args.error_message == "Slack send returned False"

    @pytest.mark.asyncio
    async def test_muted_suppressed_attempt_persisted(self, high_bugcase, mock_store, mock_settings):
        """Muted BugCase should persist attempt record with status='suppressed', suppressed_reason='muted'."""
        high_bugcase.muted_until = datetime.utcnow() + timedelta(minutes=10)

        result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)

        assert result == "suppressed"
        # Verify attempt was persisted
        assert mock_store.create_notification_attempt.called
        call_args = mock_store.create_notification_attempt.call_args[0][0]
        assert call_args.bugcase_id == "bc_test_1"
        assert call_args.status == "suppressed"
        assert call_args.suppressed_reason == "muted"
        assert call_args.error_type is None

    @pytest.mark.asyncio
    async def test_snoozed_suppressed_attempt_persisted(self, high_bugcase, mock_store, mock_settings):
        """Snoozed BugCase should persist attempt record with status='suppressed', suppressed_reason='snoozed'."""
        high_bugcase.snoozed_until = datetime.utcnow() + timedelta(hours=2)

        result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)

        assert result == "suppressed"
        # Verify attempt was persisted
        assert mock_store.create_notification_attempt.called
        call_args = mock_store.create_notification_attempt.call_args[0][0]
        assert call_args.bugcase_id == "bc_test_1"
        assert call_args.status == "suppressed"
        assert call_args.suppressed_reason == "snoozed"
        assert call_args.error_type is None

    @pytest.mark.asyncio
    async def test_notification_attempt_storage_failure_does_not_propagate(
        self, high_bugcase, mock_store, mock_settings
    ):
        """Storage failure in create_notification_attempt should not propagate."""
        # Mock send_case_notification to succeed
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            # Mock store method to raise exception
            mock_store.create_notification_attempt.side_effect = Exception("Database error")

            # Should not raise even though storage failed
            result = await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            assert result == "sent"
            # Attempt to persist was made despite failure
            assert mock_store.create_notification_attempt.called

    @pytest.mark.asyncio
    async def test_notification_id_uniqueness(self, high_bugcase, mock_store, mock_settings):
        """notification_id should be unique across attempts."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            # Make two attempts
            await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)
            await route_and_send_notification(high_bugcase, "bugcase_created", mock_store)

            # Both should have different notification_ids
            assert mock_store.create_notification_attempt.call_count == 2
            first_call = mock_store.create_notification_attempt.call_args_list[0][0][0]
            second_call = mock_store.create_notification_attempt.call_args_list[1][0][0]
            assert first_call.notification_id != second_call.notification_id

    @pytest.mark.asyncio
    async def test_attempt_created_with_required_fields_only(self):
        """NotificationAttemptCreate should be instantiable with required fields."""
        attempt = NotificationAttemptCreate(
            notification_id="notif_test_uuid",
            bugcase_id="bc_123",
            event_type="bugcase_created",
            status="sent",
        )
        assert attempt.notification_id == "notif_test_uuid"
        assert attempt.bugcase_id == "bc_123"
        assert attempt.event_type == "bugcase_created"
        assert attempt.channel == "slack"  # Default
        assert attempt.status == "sent"
        assert attempt.error_type is None
        assert attempt.error_message is None
        assert attempt.suppressed_reason is None

    @pytest.mark.asyncio
    async def test_sent_event_persisted(self, high_bugcase, mock_store, mock_settings):
        """Different event types should be persisted correctly."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await route_and_send_notification(high_bugcase, "bugcase_reopened", mock_store)

            call_args = mock_store.create_notification_attempt.call_args[0][0]
            assert call_args.event_type == "bugcase_reopened"

    @pytest.mark.asyncio
    async def test_severity_escalation_event_persisted(self, high_bugcase, mock_store, mock_settings):
        """Severity escalation event should be persisted."""
        with patch("crypto_news_aggregator.bugops.slack.send_case_notification", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await route_and_send_notification(high_bugcase, "severity_escalated", mock_store)

            call_args = mock_store.create_notification_attempt.call_args[0][0]
            assert call_args.event_type == "severity_escalated"
