"""Tests for BugOps Slack notification."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.slack import send_case_notification, _build_slack_message
from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus


@pytest.fixture
def sample_case():
    """Create a sample BugCase for testing."""
    return BugCase(
        id="case_123",
        case_id="case_001",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.CRITICAL,
        title="LLM Cost Runaway Detected",
        summary="LLM cost exceeded threshold in 5-minute window",
        dedupe_key="llm_cost_runaway_2026-05-08",
        source_types=["llm_traces"],
        alert_ids=["alert_001"],
        correlation_keys=["service:enrichment"],
        created_at=datetime(2026, 5, 8, 10, 30, 0),
        updated_at=datetime(2026, 5, 8, 10, 30, 0),
        metric={"cost_5min_usd": 0.35, "threshold_usd": 0.25, "projected_hourly_usd": 4.20}
    )


class TestBuildSlackMessage:
    """Tests for _build_slack_message."""

    def test_build_message_critical_severity(self, sample_case):
        """Test message building with CRITICAL severity."""
        message = _build_slack_message(sample_case)

        assert "attachments" in message
        assert len(message["attachments"]) == 1
        attachment = message["attachments"][0]
        assert attachment["color"] == "#ff0000"
        assert attachment["title"] == "LLM Cost Runaway Detected"
        assert attachment["text"] == "LLM cost exceeded threshold in 5-minute window"

    def test_message_includes_required_fields(self, sample_case):
        """Test that message includes all required fields."""
        message = _build_slack_message(sample_case)
        attachment = message["attachments"][0]
        field_titles = [f["title"] for f in attachment["fields"]]

        assert "Case ID" in field_titles
        assert "Severity" in field_titles
        assert "Source Type" in field_titles
        assert "Status" in field_titles
        assert "Metrics" in field_titles

    def test_message_case_id_field(self, sample_case):
        """Test that case_id is included correctly."""
        message = _build_slack_message(sample_case)
        attachment = message["attachments"][0]
        case_id_field = next(f for f in attachment["fields"] if f["title"] == "Case ID")

        assert case_id_field["value"] == "case_001"
        assert case_id_field["short"] is True

    def test_message_severity_field(self, sample_case):
        """Test that severity is formatted correctly."""
        message = _build_slack_message(sample_case)
        attachment = message["attachments"][0]
        severity_field = next(f for f in attachment["fields"] if f["title"] == "Severity")

        assert severity_field["value"] == "CRITICAL"

    def test_message_metrics_field(self, sample_case):
        """Test that metrics are included in the message."""
        message = _build_slack_message(sample_case)
        attachment = message["attachments"][0]
        metrics_field = next(f for f in attachment["fields"] if f["title"] == "Metrics")

        assert "cost_5min_usd: 0.35" in metrics_field["value"]
        assert "threshold_usd: 0.25" in metrics_field["value"]
        assert "projected_hourly_usd: 4.2" in metrics_field["value"]

    def test_message_severity_colors(self):
        """Test severity color mapping."""
        colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffa500",
            AlertSeverity.HIGH: "#ff6600",
            AlertSeverity.CRITICAL: "#ff0000",
        }

        for severity, expected_color in colors.items():
            case = BugCase(
                case_id="test",
                status=CaseStatus.OPEN,
                severity=severity,
                title="Test",
                summary="Test",
                dedupe_key="test",
                source_types=["test"],
                created_at=datetime.utcnow()
            )
            message = _build_slack_message(case)
            assert message["attachments"][0]["color"] == expected_color

    def test_message_timestamp(self, sample_case):
        """Test that created_at is included as timestamp."""
        message = _build_slack_message(sample_case)
        attachment = message["attachments"][0]

        assert "ts" in attachment
        assert attachment["ts"] == int(sample_case.created_at.timestamp())

    def test_message_without_metrics(self):
        """Test message building when case has no metrics."""
        case = BugCase(
            case_id="test",
            status=CaseStatus.OPEN,
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            summary="Test summary",
            dedupe_key="test",
            source_types=["test"],
            created_at=datetime.utcnow(),
            metric={}
        )
        message = _build_slack_message(case)
        attachment = message["attachments"][0]
        field_titles = [f["title"] for f in attachment["fields"]]

        assert "Metrics" not in field_titles


class TestSendCaseNotification:
    """Tests for send_case_notification."""

    @pytest.mark.asyncio
    async def test_send_notification_success(self, sample_case):
        """Test successful Slack notification send."""
        with patch('crypto_news_aggregator.bugops.slack.get_bugops_settings') as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
            mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            with patch('crypto_news_aggregator.bugops.slack.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await send_case_notification(sample_case)

                assert result is True
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert call_args[0][0] == "https://hooks.slack.com/test"
                assert call_args[1]["timeout"] == 10.0

    @pytest.mark.asyncio
    async def test_send_notification_disabled(self, sample_case):
        """Test that notification is skipped when disabled."""
        with patch('crypto_news_aggregator.bugops.slack.get_bugops_settings') as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = False

            result = await send_case_notification(sample_case)

            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_missing_webhook_url(self, sample_case):
        """Test that notification fails gracefully when webhook URL is missing."""
        with patch('crypto_news_aggregator.bugops.slack.get_bugops_settings') as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
            mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = ""

            result = await send_case_notification(sample_case)

            assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_http_error(self, sample_case):
        """Test that HTTP errors are handled gracefully."""
        with patch('crypto_news_aggregator.bugops.slack.get_bugops_settings') as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
            mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            with patch('crypto_news_aggregator.bugops.slack.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=Exception("Connection error"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await send_case_notification(sample_case)

                assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_does_not_crash_monitor(self, sample_case):
        """Test that Slack failures don't crash the monitor loop."""
        with patch('crypto_news_aggregator.bugops.slack.get_bugops_settings') as mock_settings:
            mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
            mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            with patch('crypto_news_aggregator.bugops.slack.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(side_effect=Exception("Fatal error"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                # Should return False and not raise
                result = await send_case_notification(sample_case)
                assert result is False
