"""Tests for BugOps data models."""

import pytest
from datetime import datetime
from crypto_news_aggregator.bugops.models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
    AlertSeverity,
    AlertStatus,
    CaseStatus,
    BugOpsSubsystem,
)


def test_alert_severity_enum_values():
    """Test severity enum has exact values."""
    assert AlertSeverity.INFO.value == "info"
    assert AlertSeverity.WARNING.value == "warning"
    assert AlertSeverity.HIGH.value == "high"
    assert AlertSeverity.CRITICAL.value == "critical"


def test_bug_alert_event_create_requires_severity():
    """Test that severity is required on alert events."""
    with pytest.raises(Exception):  # Pydantic validation error
        BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            title="Test Alert",
            summary="Test Summary",
            domain=["llm", "cost"],
            dedupe_key="cost_runaway_1",
            # Missing severity
        )


def test_bug_alert_event_create_requires_dedupe_key():
    """Test that dedupe_key is required on alert events."""
    with pytest.raises(Exception):  # Pydantic validation error
        BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            summary="Test Summary",
            domain=["llm", "cost"],
            # Missing dedupe_key
        )


def test_bug_alert_event_create_valid():
    """Test creating a valid alert event."""
    event = BugAlertEventCreate(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.HIGH,
        title="Cost Runaway Detected",
        summary="LLM cost exceeded threshold",
        domain=["llm", "cost"],
        dedupe_key="cost_runaway_1",
    )
    assert event.alert_id == "alert_1"
    assert event.severity == AlertSeverity.HIGH
    assert event.status == AlertStatus.NEW
    assert event.dedupe_key == "cost_runaway_1"


def test_bug_alert_event_default_status():
    """Test that alert events default to status=new."""
    event = BugAlertEventCreate(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.WARNING,
        title="Test",
        summary="Test",
        domain=["llm"],
        dedupe_key="test_1",
    )
    assert event.status == AlertStatus.NEW


def test_bug_case_create_requires_severity():
    """Test that severity is required on cases."""
    with pytest.raises(Exception):  # Pydantic validation error
        BugCaseCreate(
            case_id="case_1",
            title="Test Case",
            summary="Test",
            dedupe_key="test_1",
            source_types=["llm_traces"],
            # Missing severity
        )


def test_bug_case_create_requires_dedupe_key():
    """Test that dedupe_key is required on cases."""
    with pytest.raises(Exception):  # Pydantic validation error
        BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            title="Test Case",
            summary="Test",
            source_types=["llm_traces"],
            # Missing dedupe_key
        )


def test_bug_case_create_valid():
    """Test creating a valid case."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="cost_runaway",
        title="Cost Runaway Case",
        summary="Multiple cost runaway alerts",
        dedupe_key="cost_runaway_1",
        source_types=["llm_traces"],
        alert_ids=["alert_1", "alert_2"],
    )
    assert case.case_id == "case_1"
    assert case.status == CaseStatus.OPEN
    assert case.severity == AlertSeverity.HIGH
    assert case.dedupe_key == "cost_runaway_1"


def test_bug_case_create_default_status():
    """Test that cases default to status=open."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.WARNING,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )
    assert case.status == CaseStatus.OPEN


def test_bug_case_create_default_alert_ids():
    """Test that cases default to empty alert_ids list."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.WARNING,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )
    assert case.alert_ids == []


def test_bug_case_manual_only_lifecycle():
    """Test case lifecycle states: open, resolved, closed."""
    # Create as open
    case = BugCaseCreate(
        case_id="case_1",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )
    assert case.status == CaseStatus.OPEN

    # Manual transition to resolved
    case_resolved = BugCaseCreate(
        case_id="case_1",
        status=CaseStatus.RESOLVED,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )
    assert case_resolved.status == CaseStatus.RESOLVED

    # Manual transition to closed
    case_closed = BugCaseCreate(
        case_id="case_1",
        status=CaseStatus.CLOSED,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )
    assert case_closed.status == CaseStatus.CLOSED


def test_bug_case_sprint020_fields_with_defaults():
    """Test that Sprint 020 fields are present with correct defaults."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="freshness",
        title="Article Freshness Failure",
        summary="No articles inserted",
        dedupe_key="article_freshness:articles",
        source_types=["freshness_detector"],
    )
    assert case.observation_count == 1
    assert case.reopen_count == 0
    assert case.root_subsystem is None
    assert case.affected_subsystems == []
    assert case.blast_radius == []
    assert case.first_seen_at is None
    assert case.last_seen_at is None
    assert case.recovery_candidate_at is None
    assert case.resolution_type is None
    assert case.detection_type is None
    assert case.muted_until is None
    assert case.snoozed_until is None
    assert case.last_notified_at is None
    assert case.notification_count == 0


def test_bug_case_sprint020_fields_with_values():
    """Test that Sprint 020 fields can be set with values."""
    now = datetime.utcnow()
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="freshness",
        title="Article Freshness Failure",
        summary="No articles inserted",
        dedupe_key="article_freshness:articles",
        source_types=["freshness_detector"],
        root_subsystem="articles",
        affected_subsystems=["signals", "narratives"],
        blast_radius=["signals", "narratives", "briefings"],
        observation_count=3,
        first_seen_at=now,
        last_seen_at=now,
        detection_type="startup",
        reopen_count=1,
    )
    assert case.root_subsystem == "articles"
    assert case.affected_subsystems == ["signals", "narratives"]
    assert case.blast_radius == ["signals", "narratives", "briefings"]
    assert case.observation_count == 3
    assert case.first_seen_at == now
    assert case.last_seen_at == now
    assert case.detection_type == "startup"
    assert case.reopen_count == 1


def test_bug_case_detection_type_values():
    """Test detection_type enum values."""
    for detection_type in ["startup", "runtime", "reopen"]:
        case = BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="freshness",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            detection_type=detection_type,
        )
        assert case.detection_type == detection_type


def test_bug_case_read_model_inherits_sprint020_fields():
    """Test that BugCase (read model) inherits all Sprint 020 fields from BugCaseCreate."""
    now = datetime.utcnow()
    case_data = {
        "case_id": "case_1",
        "severity": AlertSeverity.HIGH,
        "alert_type": "freshness",
        "title": "Article Freshness",
        "summary": "No articles",
        "dedupe_key": "article_freshness:articles",
        "source_types": ["detector"],
        "root_subsystem": "articles",
        "affected_subsystems": ["signals"],
        "blast_radius": ["signals", "narratives"],
        "observation_count": 2,
        "first_seen_at": now,
        "last_seen_at": now,
        "detection_type": "startup",
        "reopen_count": 1,
    }
    case = BugCase(**case_data)
    assert case.root_subsystem == "articles"
    assert case.affected_subsystems == ["signals"]
    assert case.blast_radius == ["signals", "narratives"]
    assert case.observation_count == 2
    assert case.first_seen_at == now
    assert case.last_seen_at == now
    assert case.detection_type == "startup"
    assert case.reopen_count == 1


# BugOpsSubsystem enum tests
def test_bugops_subsystem_enum_has_all_values():
    """Test that canonical subsystem enum has all expected values."""
    assert BugOpsSubsystem.SCHEDULER.value == "scheduler"
    assert BugOpsSubsystem.INGESTION.value == "ingestion"
    assert BugOpsSubsystem.ARTICLES.value == "articles"
    assert BugOpsSubsystem.SIGNALS.value == "signals"
    assert BugOpsSubsystem.NARRATIVES.value == "narratives"
    assert BugOpsSubsystem.BRIEFINGS.value == "briefings"
    assert BugOpsSubsystem.WORKER.value == "worker"
    assert BugOpsSubsystem.DATABASE.value == "database"


def test_bugops_subsystem_enum_count():
    """Test that there are exactly 8 canonical subsystems."""
    assert len(BugOpsSubsystem) == 8


def test_bugops_subsystem_is_string_enum():
    """Test that BugOpsSubsystem is a string enum."""
    assert isinstance(BugOpsSubsystem.ARTICLES, str)
    assert BugOpsSubsystem.ARTICLES == "articles"


def test_root_subsystem_accepts_valid_value():
    """Test that root_subsystem accepts valid canonical value."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="freshness",
        title="Article Freshness",
        summary="No articles",
        dedupe_key="article_freshness:articles",
        source_types=["detector"],
        root_subsystem="articles",
    )
    assert case.root_subsystem == "articles"


def test_root_subsystem_rejects_invalid_value():
    """Test that root_subsystem rejects non-canonical value."""
    with pytest.raises(ValueError, match="root_subsystem must be a valid BugOpsSubsystem value"):
        BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="freshness",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            root_subsystem="invalid_subsystem",
        )


def test_affected_subsystems_accepts_valid_values():
    """Test that affected_subsystems accepts valid canonical values."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="freshness",
        title="Test",
        summary="Test",
        dedupe_key="test",
        source_types=["detector"],
        affected_subsystems=["signals", "narratives", "briefings"],
    )
    assert case.affected_subsystems == ["signals", "narratives", "briefings"]


def test_affected_subsystems_rejects_invalid_value():
    """Test that affected_subsystems rejects non-canonical value."""
    with pytest.raises(ValueError, match="affected_subsystems contains invalid value"):
        BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="freshness",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            affected_subsystems=["signals", "invalid_subsystem"],
        )


def test_blast_radius_accepts_valid_values():
    """Test that blast_radius accepts valid canonical values."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="freshness",
        title="Test",
        summary="Test",
        dedupe_key="test",
        source_types=["detector"],
        blast_radius=["signals", "narratives", "briefings"],
    )
    assert case.blast_radius == ["signals", "narratives", "briefings"]


def test_blast_radius_rejects_invalid_value():
    """Test that blast_radius rejects non-canonical value."""
    with pytest.raises(ValueError, match="blast_radius contains invalid value"):
        BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="freshness",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            blast_radius=["signals", "bad_subsystem"],
        )


def test_all_subsystems_valid_in_case_fields():
    """Test that all canonical subsystems are valid in case fields."""
    for subsystem in BugOpsSubsystem:
        # Test root_subsystem
        case1 = BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            root_subsystem=subsystem.value,
        )
        assert case1.root_subsystem == subsystem.value

        # Test affected_subsystems
        case2 = BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            affected_subsystems=[subsystem.value],
        )
        assert case2.affected_subsystems == [subsystem.value]

        # Test blast_radius
        case3 = BugCaseCreate(
            case_id="case_1",
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Test",
            summary="Test",
            dedupe_key="test",
            source_types=["detector"],
            blast_radius=[subsystem.value],
        )
        assert case3.blast_radius == [subsystem.value]


def test_empty_subsystem_lists_valid():
    """Test that empty subsystem lists are valid."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test",
        source_types=["detector"],
        affected_subsystems=[],
        blast_radius=[],
    )
    assert case.affected_subsystems == []
    assert case.blast_radius == []


def test_none_root_subsystem_valid():
    """Test that None is valid for optional root_subsystem."""
    case = BugCaseCreate(
        case_id="case_1",
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test",
        summary="Test",
        dedupe_key="test",
        source_types=["detector"],
        root_subsystem=None,
    )
    assert case.root_subsystem is None
