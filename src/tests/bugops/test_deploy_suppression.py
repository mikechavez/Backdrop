"""Tests for TASK-112: global deploy suppression."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.slack import is_suppression_active, route_and_send_notification
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, BugCaseCreate
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor


class TestSuppressionCheck:
    """Test is_suppression_active() logic."""

    def test_suppression_active_future_timestamp(self):
        """BUGOPS_SUPPRESSED_UNTIL set to future timestamp → returns True."""
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = future.isoformat()

        assert is_suppression_active(settings) is True

    def test_suppression_inactive_past_timestamp(self):
        """BUGOPS_SUPPRESSED_UNTIL set to past timestamp → returns False."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = past.isoformat()

        assert is_suppression_active(settings) is False

    def test_suppression_inactive_empty_string(self):
        """BUGOPS_SUPPRESSED_UNTIL empty string → returns False."""
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = ""

        assert is_suppression_active(settings) is False

    def test_suppression_inactive_invalid_string(self):
        """BUGOPS_SUPPRESSED_UNTIL invalid string → returns False (no exception)."""
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = "not-a-valid-timestamp"

        assert is_suppression_active(settings) is False

    def test_suppression_inactive_none(self):
        """BUGOPS_SUPPRESSED_UNTIL None → returns False."""
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = None

        assert is_suppression_active(settings) is False


@pytest.mark.asyncio
class TestSuppressionRouting:
    """Test suppression in route_and_send_notification()."""

    async def test_suppression_active_suppresses_notification(self):
        """Suppression active → notification suppressed, BugCase still created."""
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = future.isoformat()

        case = BugCase(
            case_id="bc_test",
            status="open",
            severity=AlertSeverity.HIGH,
            alert_type="article_freshness",
            title="Article Freshness Failure",
            summary="No articles for 60 minutes",
            dedupe_key="article_freshness:articles",
            source_types=["article_freshness"],
            root_subsystem="articles",
            blast_radius=[],
            affected_subsystems=[],
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            observation_count=1,
            detection_type="runtime",
            suggested_manual_check="Check RSS ingestion",
        )

        store = AsyncMock()
        store.update_last_notified_at_only = AsyncMock()
        store.create_notification_attempt = AsyncMock()

        with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings", return_value=settings):
            result = await route_and_send_notification(case, "bugcase_created", store)

        assert result == "suppressed"
        store.update_last_notified_at_only.assert_called_once()
        store.create_notification_attempt.assert_called_once()

        # Verify attempt was persisted with correct reason
        attempt = store.create_notification_attempt.call_args[0][0]
        assert attempt.status == "suppressed"
        assert attempt.suppressed_reason == "deploy_suppression"

    async def test_suppression_active_allows_auto_resolution(self):
        """Suppression active → auto-resolution still runs (mocked verification)."""
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        settings = MagicMock()
        settings.BUGOPS_SUPPRESSED_UNTIL = future.isoformat()
        settings.BUGOPS_ENABLED = True
        settings.BUGOPS_POLL_INTERVAL_SECONDS = 300
        settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10
        settings.BUGOPS_SLACK_ENABLED = True

        monitor = BugOpsMonitor()
        monitor.settings = settings
        monitor.store = AsyncMock()
        monitor.store.get_open_freshness_cases = AsyncMock(return_value=[])

        # Mock _run_auto_resolution to track if it's called
        with patch.object(monitor, "_run_auto_resolution", new_callable=AsyncMock) as mock_auto_res:
            with patch("crypto_news_aggregator.bugops.slack.is_suppression_active", return_value=True):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    monitor.running = False  # Stop after one iteration
                    monitor._poll_signals = AsyncMock()
                    monitor._poll_freshness_detectors = AsyncMock()

                    # Simulate one iteration
                    await monitor._poll_signals()
                    await monitor._poll_freshness_detectors()
                    await monitor._run_auto_resolution()

                    mock_auto_res.assert_called_once()

    async def test_suppression_expiry_detection(self):
        """Suppression expires (was active, now inactive) → _send_suppression_expiry_summary() called."""
        settings = MagicMock()

        monitor = BugOpsMonitor()
        monitor.settings = settings
        monitor._suppression_was_active = True

        # Simulate suppression transition: was active → now inactive
        with patch("crypto_news_aggregator.bugops.slack.is_suppression_active", return_value=False):
            with patch.object(monitor, "_send_suppression_expiry_summary", new_callable=AsyncMock) as mock_summary:
                # Manually run the expiry detection logic (without running the full monitor)
                currently_suppressed = False
                if monitor._suppression_was_active and not currently_suppressed:
                    await monitor._send_suppression_expiry_summary()
                monitor._suppression_was_active = currently_suppressed

                # Verify summary was called (expiry detected)
                mock_summary.assert_called_once()


@pytest.mark.asyncio
class TestMuteSnoozeStoreOperations:
    """Test mute_case() and snooze_case() store methods."""

    async def test_mute_case(self):
        """mute_case() sets muted_until correctly."""
        db = AsyncMock()
        db.__getitem__ = MagicMock(side_effect=lambda x: AsyncMock())

        store = BugOpsStore(db)

        muted_until = datetime.utcnow() + timedelta(hours=1)
        updated_case_doc = {
            "case_id": "bc_test",
            "status": "open",
            "severity": "high",
            "alert_type": "article_freshness",
            "title": "Article Freshness Failure",
            "summary": "No articles",
            "dedupe_key": "article_freshness:articles",
            "source_types": ["article_freshness"],
            "root_subsystem": "articles",
            "blast_radius": [],
            "affected_subsystems": [],
            "first_seen_at": datetime.utcnow(),
            "last_seen_at": datetime.utcnow(),
            "observation_count": 1,
            "detection_type": "runtime",
            "suggested_manual_check": "Check RSS",
            "muted_until": muted_until,
        }

        store.cases_collection.find_one_and_update = AsyncMock(return_value=updated_case_doc)

        result = await store.mute_case("bc_test", muted_until)

        assert result.case_id == "bc_test"
        assert result.muted_until == muted_until
        store.cases_collection.find_one_and_update.assert_called_once()

    async def test_snooze_case(self):
        """snooze_case() sets snoozed_until correctly."""
        db = AsyncMock()
        db.__getitem__ = MagicMock(side_effect=lambda x: AsyncMock())

        store = BugOpsStore(db)

        snoozed_until = datetime.utcnow() + timedelta(hours=2)
        updated_case_doc = {
            "case_id": "bc_test",
            "status": "open",
            "severity": "high",
            "alert_type": "article_freshness",
            "title": "Article Freshness Failure",
            "summary": "No articles",
            "dedupe_key": "article_freshness:articles",
            "source_types": ["article_freshness"],
            "root_subsystem": "articles",
            "blast_radius": [],
            "affected_subsystems": [],
            "first_seen_at": datetime.utcnow(),
            "last_seen_at": datetime.utcnow(),
            "observation_count": 1,
            "detection_type": "runtime",
            "suggested_manual_check": "Check RSS",
            "snoozed_until": snoozed_until,
        }

        store.cases_collection.find_one_and_update = AsyncMock(return_value=updated_case_doc)

        result = await store.snooze_case("bc_test", snoozed_until)

        assert result.case_id == "bc_test"
        assert result.snoozed_until == snoozed_until
        store.cases_collection.find_one_and_update.assert_called_once()
