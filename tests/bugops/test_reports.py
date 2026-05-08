"""Tests for BugOps deterministic case reports."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.reports import generate_case_report
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
    AlertSeverity,
    AlertStatus,
    CaseStatus,
)


@pytest.fixture
def mock_db():
    """Create a mock Motor database."""
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda x: MagicMock())
    return db


@pytest.fixture
def store(mock_db):
    """Create a BugOpsStore instance with mock database."""
    return BugOpsStore(mock_db)


def test_report_includes_case_id_and_severity():
    """Test that report includes case ID and severity."""
    case = BugCase(
        case_id="case_001",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="cost_runaway",
        title="Cost Runaway Detected",
        summary="API costs exceeded threshold",
        dedupe_key="cost_runaway_1",
        source_types=["llm_traces"],
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )
    alert_events = []

    report = generate_case_report(case, alert_events)

    assert "case_001" in report
    assert "Cost Runaway Detected" in report
    assert "high" in report
    assert "open" in report


def test_report_includes_alert_event_metrics():
    """Test that report includes alert event metrics."""
    case = BugCase(
        case_id="case_002",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.CRITICAL,
        alert_type="error_spike",
        title="Error Spike",
        summary="Error rate elevated",
        dedupe_key="error_spike_1",
        source_types=["railway_logs"],
        metric={"error_count": 500},
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )

    alert_event = BugAlertEvent(
        alert_id="alert_1",
        case_id="case_002",
        source_type="railway_logs",
        source_id="railway.errors",
        alert_type="error_spike",
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.ATTACHED,
        title="Error Rate High",
        summary="Error rate above threshold",
        domain=["errors", "monitoring"],
        dedupe_key="error_spike_1",
        metric={"error_rate": 25.5, "threshold": 10.0},
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )

    report = generate_case_report(case, [alert_event])

    assert "Alert Events" in report
    assert "Error Rate High" in report
    assert "Observed Metrics" in report
    assert "error_count" in report
    assert "500" in report


def test_report_does_not_include_unsupported_root_cause_claims():
    """Test that report does not make root-cause claims."""
    case = BugCase(
        case_id="case_003",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.WARNING,
        alert_type="latency",
        title="High Latency",
        summary="Response times elevated",
        dedupe_key="latency_1",
        source_types=["api_metrics"],
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )
    alert_events = []

    report = generate_case_report(case, alert_events)

    # Verify no root-cause claims like "caused by", "due to", "resulting from"
    assert "caused by" not in report.lower()
    assert "due to" not in report.lower()
    assert "root cause" not in report.lower()


def test_report_deterministic():
    """Test that report generation is deterministic."""
    case = BugCase(
        case_id="case_004",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test_alert",
        title="Test Case",
        summary="Test summary",
        dedupe_key="test_1",
        source_types=["test_source"],
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )

    alert_event = BugAlertEvent(
        alert_id="alert_1",
        case_id="case_004",
        source_type="test_source",
        source_id="test.source",
        alert_type="test_alert",
        severity=AlertSeverity.HIGH,
        status=AlertStatus.ATTACHED,
        title="Test Alert",
        summary="Test alert summary",
        domain=["test"],
        dedupe_key="test_1",
        created_at=datetime(2026, 5, 8, 10, 0, 0),
        updated_at=datetime(2026, 5, 8, 10, 0, 0),
    )

    report1 = generate_case_report(case, [alert_event])
    report2 = generate_case_report(case, [alert_event])

    assert report1 == report2


@pytest.mark.asyncio
async def test_report_is_written_back_to_case(store):
    """Test that report is persisted to bug_cases collection."""
    case_id = "case_005"
    report_text = "# Test Report\n\nThis is a test report."

    # Mock the find_one_and_update method
    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = {
        "case_id": case_id,
        "status": "open",
        "severity": "high",
        "alert_type": "test",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["test"],
        "deterministic_report": report_text,
        "created_at": datetime(2026, 5, 8, 10, 0, 0),
        "updated_at": datetime(2026, 5, 8, 10, 0, 0),
    }
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    result = await store.save_case_report(case_id, report_text)

    assert result.deterministic_report == report_text
    mock_find_one_and_update.assert_called_once()
    call_args = mock_find_one_and_update.call_args
    assert call_args[0][0] == {"case_id": case_id}
    assert "$set" in call_args[0][1]
    assert call_args[0][1]["$set"]["deterministic_report"] == report_text


@pytest.mark.asyncio
async def test_get_alert_events_for_case(store):
    """Test fetching alert events for a case."""
    case_id = "case_006"

    # Mock the find().to_list() pattern
    mock_find = MagicMock()
    mock_find.to_list = AsyncMock(return_value=[
        {
            "_id": "event_1",
            "alert_id": "alert_1",
            "case_id": case_id,
            "source_type": "test",
            "source_id": "test.source",
            "alert_type": "test",
            "severity": "high",
            "status": "attached",
            "title": "Test",
            "summary": "Test",
            "domain": ["test"],
            "dedupe_key": "test_1",
            "created_at": datetime(2026, 5, 8, 10, 0, 0),
            "updated_at": datetime(2026, 5, 8, 10, 0, 0),
        }
    ])
    store.alert_events_collection.find = MagicMock(return_value=mock_find)

    result = await store.get_alert_events_for_case(case_id)

    assert len(result) == 1
    assert result[0].alert_id == "alert_1"
    store.alert_events_collection.find.assert_called_once_with({"case_id": case_id})
