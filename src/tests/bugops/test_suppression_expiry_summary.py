"""Tests for deploy suppression expiry summary (TASK-112A)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.models import BugCase, CaseStatus, AlertSeverity
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
from crypto_news_aggregator.bugops.slack import send_suppression_summary


@pytest.fixture
def sample_cases():
    """Generate sample BugCases for testing."""
    now = datetime.utcnow()
    return [
        BugCase(
            _id="id_1",
            case_id="bc_articles_001",
            severity=AlertSeverity.HIGH,
            alert_type="article_freshness",
            title="Article Freshness Failure",
            summary="No articles inserted for 42 minutes",
            dedupe_key="article_freshness:articles",
            source_types=["article_freshness"],
            alert_ids=[],
            status=CaseStatus.OPEN,
            root_subsystem="articles",
            affected_subsystems=["signals", "narratives", "briefings"],
            blast_radius=["signals", "narratives", "briefings"],
            first_seen_at=now - timedelta(minutes=50),
            last_seen_at=now - timedelta(minutes=10),
            observation_count=5,
            detection_type="runtime",
            created_at=now - timedelta(minutes=50),
            updated_at=now,
            notification_count=1,
            last_notified_at=now - timedelta(minutes=30),
        ),
        BugCase(
            _id="id_2",
            case_id="bc_briefings_002",
            severity=AlertSeverity.HIGH,
            alert_type="briefing_freshness",
            title="Briefing Freshness Failure",
            summary="No briefing generated in expected window",
            dedupe_key="briefing_freshness:briefings",
            source_types=["briefing_freshness"],
            alert_ids=[],
            status=CaseStatus.OPEN,
            root_subsystem="briefings",
            affected_subsystems=[],
            blast_radius=[],
            first_seen_at=now - timedelta(minutes=30),
            last_seen_at=now - timedelta(minutes=5),
            observation_count=3,
            detection_type="runtime",
            created_at=now - timedelta(minutes=30),
            updated_at=now,
            notification_count=1,
            last_notified_at=now - timedelta(minutes=20),
        ),
    ]


@pytest.fixture
def critical_case():
    """Generate a critical severity BugCase."""
    now = datetime.utcnow()
    return BugCase(
        _id="id_critical",
        case_id="bc_critical_001",
        severity=AlertSeverity.CRITICAL,
        alert_type="test_alert",
        title="Critical Failure",
        summary="Critical system failure",
        dedupe_key="critical:test",
        source_types=["test"],
        alert_ids=[],
        status=CaseStatus.OPEN,
        root_subsystem="scheduler",
        affected_subsystems=[],
        blast_radius=[],
        first_seen_at=now - timedelta(minutes=20),
        last_seen_at=now,
        observation_count=1,
        detection_type="runtime",
        created_at=now - timedelta(minutes=20),
        updated_at=now,
        notification_count=0,
    )


@pytest.mark.asyncio
async def test_send_suppression_summary_with_unresolved_cases(sample_cases):
    """Test sending summary when unresolved cases exist."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
        mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_client.post.return_value = mock_response

            result = await send_suppression_summary(sample_cases)

            assert result is True
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["attachments"][0]["text"]


@pytest.mark.asyncio
async def test_send_suppression_summary_empty_list():
    """Test that no Slack call is made when cases list is empty."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
        mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

        with patch("httpx.AsyncClient") as mock_client_class:
            result = await send_suppression_summary([])

            assert result is False
            mock_client_class.assert_not_called()


@pytest.mark.asyncio
async def test_send_suppression_summary_slack_disabled():
    """Test that no Slack call is made when Slack is disabled."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = False

        result = await send_suppression_summary([MagicMock()])

        assert result is False


@pytest.mark.asyncio
async def test_send_suppression_summary_webhook_url_missing():
    """Test that no Slack call is made when webhook URL is not configured."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
        mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = None

        result = await send_suppression_summary([MagicMock()])

        assert result is False


@pytest.mark.asyncio
async def test_send_suppression_summary_http_error(sample_cases):
    """Test error handling when Slack HTTP request fails."""
    import httpx

    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
        mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            mock_client.post.side_effect = httpx.HTTPError("Connection failed")

            result = await send_suppression_summary(sample_cases)

            assert result is False


@pytest.mark.asyncio
async def test_send_suppression_summary_generic_exception(sample_cases):
    """Test error handling for unexpected exceptions."""
    with patch("crypto_news_aggregator.bugops.slack.get_bugops_settings") as mock_settings:
        mock_settings.return_value.BUGOPS_SLACK_ENABLED = True
        mock_settings.return_value.BUGOPS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            mock_client.post.side_effect = RuntimeError("Unexpected error")

            result = await send_suppression_summary(sample_cases)

            assert result is False


@pytest.mark.asyncio
async def test_monitor_suppression_expiry_with_unresolved_cases(sample_cases):
    """Test that monitor sends summary when suppression expires with unresolved cases."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.store = AsyncMock()
        monitor.settings = MagicMock()
        monitor.settings.BUGOPS_SLACK_ENABLED = True
        monitor._suppression_started_at = None
        monitor.store.get_cases_active_during_window = AsyncMock(return_value=sample_cases)

        with patch("crypto_news_aggregator.bugops.slack.send_suppression_summary") as mock_send:
            mock_send.return_value = True
            await monitor._send_suppression_expiry_summary()

            mock_send.assert_called_once()
            called_cases = mock_send.call_args[0][0]
            assert len(called_cases) == 2
            assert called_cases[0].case_id == "bc_articles_001"
            assert called_cases[1].case_id == "bc_briefings_002"


@pytest.mark.asyncio
async def test_monitor_suppression_expiry_all_cases_resolved(sample_cases):
    """Test that monitor skips summary when all cases auto-resolved."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.store = AsyncMock()
        monitor.settings = MagicMock()
        monitor.settings.BUGOPS_SLACK_ENABLED = True
        monitor._suppression_started_at = None
        # Return cases but mark them as resolved
        resolved_cases = [
            {**case.model_dump(), "status": CaseStatus.RESOLVED}
            for case in sample_cases
        ]
        resolved_cases = [BugCase(**case) for case in resolved_cases]
        monitor.store.get_cases_active_during_window = AsyncMock(return_value=resolved_cases)

        with patch("crypto_news_aggregator.bugops.slack.send_suppression_summary") as mock_send:
            await monitor._send_suppression_expiry_summary()

            mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_suppression_expiry_slack_disabled():
    """Test that no Slack call is made when Slack is disabled."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.settings = MagicMock()
        monitor.settings.BUGOPS_SLACK_ENABLED = False
        monitor.store = AsyncMock()

        with patch("crypto_news_aggregator.bugops.slack.send_suppression_summary") as mock_send:
            await monitor._send_suppression_expiry_summary()

            mock_send.assert_not_called()
            monitor.store.get_cases_active_during_window.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_suppression_expiry_resets_start_time(sample_cases):
    """Test that _suppression_started_at is reset after sending summary."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.store = AsyncMock()
        monitor.settings = MagicMock()
        monitor.settings.BUGOPS_SLACK_ENABLED = True
        monitor.store.get_cases_active_during_window = AsyncMock(return_value=sample_cases)
        monitor._suppression_started_at = datetime.utcnow() - timedelta(minutes=5)

        with patch("crypto_news_aggregator.bugops.slack.send_suppression_summary"):
            await monitor._send_suppression_expiry_summary()

            assert monitor._suppression_started_at is None


@pytest.mark.asyncio
async def test_monitor_suppression_expiry_resets_on_no_unresolved(sample_cases):
    """Test that _suppression_started_at is reset when no unresolved cases."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.store = AsyncMock()
        monitor.settings = MagicMock()
        monitor.settings.BUGOPS_SLACK_ENABLED = True
        monitor.store.get_cases_active_during_window = AsyncMock(return_value=[])
        monitor._suppression_started_at = datetime.utcnow() - timedelta(minutes=5)

        await monitor._send_suppression_expiry_summary()

        assert monitor._suppression_started_at is None


@pytest.mark.asyncio
async def test_suppression_summary_message_format(sample_cases):
    """Test that suppression summary message includes all required fields."""
    from crypto_news_aggregator.bugops.slack import _build_suppression_summary_message

    message = _build_suppression_summary_message(sample_cases)

    assert "attachments" in message
    attachment = message["attachments"][0]
    assert attachment["title"] == "🔔 Deploy Suppression Ended"
    assert attachment["color"] == "#ff6600"
    assert "Deploy suppression ended" in attachment["text"]
    assert "2 unresolved BugCases were active during suppression:" in attachment["text"]
    assert "bc_articles_001" in attachment["text"]
    assert "bc_briefings_002" in attachment["text"]
    assert "Article Freshness Failure" in attachment["text"]
    assert "Briefing Freshness Failure" in attachment["text"]


@pytest.mark.asyncio
async def test_suppression_summary_message_format_single_case(critical_case):
    """Test that suppression summary message uses singular form for single case."""
    from crypto_news_aggregator.bugops.slack import _build_suppression_summary_message

    message = _build_suppression_summary_message([critical_case])

    attachment = message["attachments"][0]
    assert "1 unresolved BugCase was active during suppression:" in attachment["text"]


@pytest.mark.asyncio
async def test_suppression_summary_orders_by_severity(sample_cases, critical_case):
    """Test that suppression summary orders cases by severity (critical first)."""
    from crypto_news_aggregator.bugops.slack import _build_suppression_summary_message

    # Mix critical with high severity
    cases = [sample_cases[0], critical_case, sample_cases[1]]
    message = _build_suppression_summary_message(cases)

    text = message["attachments"][0]["text"]
    critical_pos = text.find("CRITICAL")
    article_pos = text.find("Article Freshness")
    briefing_pos = text.find("Briefing Freshness")

    # Critical should appear before HIGH cases
    assert critical_pos < article_pos
    assert critical_pos < briefing_pos
