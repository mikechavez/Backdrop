"""Tests for EvidenceCollector framework."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.evidence import EvidenceCollector, EvidenceCollectorBase
from crypto_news_aggregator.bugops.models import (
    BugCaseCreate,
    BugCase,
    CaseStatus,
    AlertSeverity,
    BugOpsSubsystem,
    EvidencePack,
    EvidencePackCreate,
    EvidenceReferenceAllocator,
    CollectionError,
)


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.get_evidence_pack_for_case = AsyncMock(return_value=None)
    store.create_evidence_pack = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    store.mark_evidence_pack_complete = AsyncMock()

    # Mock mongo_manager for collectors that need MongoDB access
    mock_db = AsyncMock()
    store.mongo_manager = MagicMock()
    store.mongo_manager.get_async_database = AsyncMock(return_value=mock_db)
    # Mock __getitem__ for database collection access
    mock_db.__getitem__.side_effect = lambda name: AsyncMock()  # Return empty async mock for any collection

    return store


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES = 10
    return settings


@pytest.fixture
def open_bugcase():
    """Create an open BugCase."""
    return BugCase(
        case_id="case_1",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test Case",
        summary="Test Summary",
        dedupe_key="test_1",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.ARTICLES.value,
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
        last_seen_at=datetime.utcnow(),
    )


@pytest.fixture
def critical_bugcase():
    """Create a critical BugCase."""
    return BugCase(
        case_id="case_critical",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.CRITICAL,
        alert_type="test",
        title="Critical Case",
        summary="Critical Summary",
        dedupe_key="critical_1",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.SCHEDULER.value,
        first_seen_at=datetime.utcnow() - timedelta(seconds=1),  # Just happened
        last_seen_at=datetime.utcnow(),
    )


@pytest.fixture
def resolved_bugcase():
    """Create a resolved BugCase."""
    return BugCase(
        case_id="case_resolved",
        status=CaseStatus.RESOLVED,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Resolved Case",
        summary="Resolved Summary",
        dedupe_key="resolved_1",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.WORKER.value,
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
        last_seen_at=datetime.utcnow() - timedelta(minutes=5),
        resolved_at=datetime.utcnow() - timedelta(minutes=5),
    )


@pytest.fixture
def closed_bugcase():
    """Create a manually closed BugCase."""
    return BugCase(
        case_id="case_closed",
        status=CaseStatus.CLOSED,
        severity=AlertSeverity.WARNING,
        alert_type="test",
        title="Closed Case",
        summary="Closed Summary",
        dedupe_key="closed_1",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.NARRATIVES.value,
        closed_at=datetime.utcnow() - timedelta(hours=1),
    )


@pytest.fixture
def mock_collector():
    """Create a mock collector."""
    collector = AsyncMock(spec=EvidenceCollectorBase)
    collector.collector_name = "test_collector"
    collector.collect = AsyncMock()
    return collector


@pytest.fixture
def mock_evidence_pack():
    """Create a mock Evidence Pack."""
    return EvidencePack(
        pack_id="ep_case_1_12345",
        bugcase_id="case_1",
        collection_status="complete",
        collection_completed_at=datetime.utcnow(),
        collection_duration_ms=100,
        sections_collected=["test_collector"],
    )


@pytest.mark.asyncio
async def test_is_eligible_closed_case(mock_store, mock_settings, closed_bugcase):
    """Test is_eligible returns False for manually closed BugCase."""
    collector = EvidenceCollector(mock_store, mock_settings)
    assert not await collector.is_eligible(closed_bugcase)


@pytest.mark.asyncio
async def test_is_eligible_existing_pack(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test is_eligible returns False when Evidence Pack already exists."""
    mock_store.get_evidence_pack_for_case = AsyncMock(return_value=mock_evidence_pack)
    collector = EvidenceCollector(mock_store, mock_settings)
    assert not await collector.is_eligible(open_bugcase)


@pytest.mark.asyncio
async def test_is_eligible_settling_window_not_elapsed(mock_store, mock_settings):
    """Test is_eligible returns False when settling window has not elapsed."""
    bugcase = BugCase(
        case_id="case_new",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="New Case",
        summary="New Summary",
        dedupe_key="new_1",
        source_types=["test"],
        first_seen_at=datetime.utcnow() - timedelta(minutes=3),  # Only 3 minutes ago
    )
    collector = EvidenceCollector(mock_store, mock_settings)
    assert not await collector.is_eligible(bugcase)


@pytest.mark.asyncio
async def test_is_eligible_settling_window_elapsed(mock_store, mock_settings, open_bugcase):
    """Test is_eligible returns True when settling window has elapsed."""
    collector = EvidenceCollector(mock_store, mock_settings)
    assert await collector.is_eligible(open_bugcase)


@pytest.mark.asyncio
async def test_is_eligible_critical_no_wait(mock_store, mock_settings, critical_bugcase):
    """Test is_eligible returns True immediately for Critical severity."""
    collector = EvidenceCollector(mock_store, mock_settings)
    assert await collector.is_eligible(critical_bugcase)


@pytest.mark.asyncio
async def test_is_eligible_resolved_case_eligible(mock_store, mock_settings, resolved_bugcase):
    """Test is_eligible returns True for resolved BugCase when no pack exists and window elapsed."""
    collector = EvidenceCollector(mock_store, mock_settings)
    assert await collector.is_eligible(resolved_bugcase)


@pytest.mark.asyncio
async def test_collect_not_eligible(mock_store, mock_settings, closed_bugcase):
    """Test collect returns None when BugCase is not eligible."""
    collector = EvidenceCollector(mock_store, mock_settings)
    result = await collector.collect(closed_bugcase)
    assert result is None
    mock_store.create_evidence_pack.assert_not_called()


@pytest.mark.asyncio
async def test_collect_creates_pack(mock_store, mock_settings, open_bugcase, mock_evidence_pack):
    """Test collect creates Evidence Pack before running collectors."""
    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    result = await collector.collect(open_bugcase)

    # Check pack was created with correct snapshot data
    assert mock_store.create_evidence_pack.called
    call_args = mock_store.create_evidence_pack.call_args
    pack_create = call_args[0][0]
    assert pack_create.bugcase_id == open_bugcase.case_id
    assert pack_create.incident_first_seen_at == open_bugcase.first_seen_at
    assert pack_create.root_subsystem == open_bugcase.root_subsystem
    assert pack_create.severity == open_bugcase.severity

    # Check pack was marked complete
    assert mock_store.mark_evidence_pack_complete.called


@pytest.mark.asyncio
async def test_collect_runs_all_collectors(
    mock_store, mock_settings, open_bugcase, mock_collector, mock_evidence_pack
):
    """Test collect runs all registered collectors."""
    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(mock_collector)

    result = await collector.collect(open_bugcase)

    assert mock_collector.collect.called
    # Verify collector received correct parameters
    call_args = mock_collector.collect.call_args
    assert call_args[0][0] == open_bugcase
    assert "ep_" in call_args[0][1]  # pack_id
    assert call_args[0][2] == mock_store
    assert isinstance(call_args[0][3], EvidenceReferenceAllocator)


@pytest.mark.asyncio
async def test_collect_collector_isolation_on_failure(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test one collector failure does not halt others."""
    # Create two collectors: one fails, one succeeds
    failing_collector = AsyncMock(spec=EvidenceCollectorBase)
    failing_collector.collector_name = "failing_collector"
    failing_collector.collect = AsyncMock(side_effect=ValueError("Test error"))

    success_collector = AsyncMock(spec=EvidenceCollectorBase)
    success_collector.collector_name = "success_collector"
    success_collector.collect = AsyncMock()

    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)
    mock_store.get_evidence_pack = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(failing_collector)
    collector.register_collector(success_collector)

    result = await collector.collect(open_bugcase)

    # Both collectors should have been called
    assert failing_collector.collect.called
    assert success_collector.collect.called

    # Error should be recorded
    assert mock_store.update_evidence_pack_section.called

    # Verify sections_collected includes only the success_collector
    mark_complete_call = mock_store.mark_evidence_pack_complete.call_args
    sections = mark_complete_call[1]["sections_collected"]
    assert "success_collector" in sections
    assert "failing_collector" not in sections


@pytest.mark.asyncio
async def test_collect_records_collection_error(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test CollectionError is recorded for failed collector."""
    failing_collector = AsyncMock(spec=EvidenceCollectorBase)
    failing_collector.collector_name = "failing_collector"
    failing_collector.collect = AsyncMock(side_effect=RuntimeError("Collection failed"))

    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)
    mock_store.get_evidence_pack = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(failing_collector)

    result = await collector.collect(open_bugcase)

    # Verify error was recorded
    assert mock_store.update_evidence_pack_section.called
    call_args = mock_store.update_evidence_pack_section.call_args
    section_data = call_args[0][1]
    assert "collection_errors" in section_data
    errors = section_data["collection_errors"]
    assert len(errors) > 0
    assert errors[0]["source"] == "failing_collector"
    assert errors[0]["error_type"] == "RuntimeError"
    assert "Collection failed" in errors[0]["error_message"]


@pytest.mark.asyncio
async def test_collect_multiple_errors_all_recorded(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test that all collector failures are recorded in a single error list."""
    # Create two failing collectors
    failing_collector_1 = AsyncMock(spec=EvidenceCollectorBase)
    failing_collector_1.collector_name = "failing_collector_1"
    failing_collector_1.collect = AsyncMock(side_effect=RuntimeError("First failure"))

    failing_collector_2 = AsyncMock(spec=EvidenceCollectorBase)
    failing_collector_2.collector_name = "failing_collector_2"
    failing_collector_2.collect = AsyncMock(side_effect=ValueError("Second failure"))

    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(failing_collector_1)
    collector.register_collector(failing_collector_2)

    result = await collector.collect(open_bugcase)

    # Verify error was recorded once with both errors
    assert mock_store.update_evidence_pack_section.called
    call_args = mock_store.update_evidence_pack_section.call_args
    section_data = call_args[0][1]
    assert "collection_errors" in section_data
    errors = section_data["collection_errors"]
    # Both errors should be present in the single error list
    assert len(errors) == 2
    assert any(e["source"] == "failing_collector_1" for e in errors)
    assert any(e["source"] == "failing_collector_2" for e in errors)


@pytest.mark.asyncio
async def test_collect_marks_pack_complete(
    mock_store, mock_settings, open_bugcase, mock_collector, mock_evidence_pack
):
    """Test collect marks pack complete after all collectors run."""
    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(mock_collector)

    result = await collector.collect(open_bugcase)

    assert mock_store.mark_evidence_pack_complete.called
    call_args = mock_store.mark_evidence_pack_complete.call_args
    assert "ep_" in call_args[1]["pack_id"]
    assert isinstance(call_args[1]["collection_completed_at"], datetime)
    assert call_args[1]["collection_duration_ms"] >= 0
    assert "test_collector" in call_args[1]["sections_collected"]


@pytest.mark.asyncio
async def test_collect_no_registered_collectors(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test collect works with zero registered collectors."""
    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    # No collectors registered
    result = await collector.collect(open_bugcase)

    assert result is not None
    assert mock_store.create_evidence_pack.called
    assert mock_store.mark_evidence_pack_complete.called


@pytest.mark.asyncio
async def test_collect_returns_partial_pack_on_collector_failure(
    mock_store, mock_settings, open_bugcase
):
    """Test collect returns partial pack when some collectors fail."""
    failing_collector = AsyncMock(spec=EvidenceCollectorBase)
    failing_collector.collector_name = "failing_collector"
    failing_collector.collect = AsyncMock(side_effect=Exception("Failed"))

    pack_with_error = EvidencePack(
        pack_id="ep_case_1_12345",
        bugcase_id="case_1",
        collection_status="partial",
        collection_errors=[
            CollectionError(
                source="failing_collector",
                error_type="Exception",
                error_message="Failed",
            ).model_dump()
        ],
    )

    mock_store.create_evidence_pack = AsyncMock(return_value=pack_with_error)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=pack_with_error)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(failing_collector)

    result = await collector.collect(open_bugcase)

    assert result is not None
    assert result.collection_status == "partial"


def test_is_settling_window_elapsed_critical(mock_settings):
    """Test _is_settling_window_elapsed returns True for Critical immediately."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    bugcase = BugCase(
        case_id="case_critical",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.CRITICAL,
        alert_type="test",
        title="Critical",
        summary="Critical",
        dedupe_key="crit_1",
        source_types=["test"],
        first_seen_at=datetime.utcnow() - timedelta(seconds=1),
    )
    assert collector._is_settling_window_elapsed(bugcase)


def test_is_settling_window_elapsed_no_first_seen(mock_settings):
    """Test _is_settling_window_elapsed returns False when first_seen_at is None."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    bugcase = BugCase(
        case_id="case_no_first_seen",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="No First Seen",
        summary="No First Seen",
        dedupe_key="nfs_1",
        source_types=["test"],
        first_seen_at=None,
    )
    assert not collector._is_settling_window_elapsed(bugcase)


def test_is_settling_window_elapsed_after_window(mock_settings):
    """Test _is_settling_window_elapsed returns True after window elapses."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    bugcase = BugCase(
        case_id="case_elapsed",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Elapsed",
        summary="Elapsed",
        dedupe_key="el_1",
        source_types=["test"],
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
    )
    assert collector._is_settling_window_elapsed(bugcase)


def test_is_settling_window_elapsed_before_window(mock_settings):
    """Test _is_settling_window_elapsed returns False before window elapses."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    bugcase = BugCase(
        case_id="case_not_elapsed",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Not Elapsed",
        summary="Not Elapsed",
        dedupe_key="ne_1",
        source_types=["test"],
        first_seen_at=datetime.utcnow() - timedelta(minutes=3),
    )
    assert not collector._is_settling_window_elapsed(bugcase)


def test_generate_pack_id(mock_settings):
    """Test _generate_pack_id generates correct format."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    pack_id = collector._generate_pack_id("case_123")
    assert pack_id.startswith("ep_case_123_")
    # Extract timestamp part and verify it's a number
    parts = pack_id.split("_")
    assert len(parts) == 4
    assert parts[0] == "ep"
    assert parts[1] == "case"
    assert parts[2] == "123"
    assert parts[3].isdigit()


@pytest.mark.asyncio
async def test_collect_sections_collected_excludes_failures(
    mock_store, mock_settings, open_bugcase, mock_evidence_pack
):
    """Test sections_collected only includes successfully completed collectors."""
    # Create mixed collectors: success, failure, success
    success_1 = AsyncMock(spec=EvidenceCollectorBase)
    success_1.collector_name = "success_1"
    success_1.collect = AsyncMock()

    failing = AsyncMock(spec=EvidenceCollectorBase)
    failing.collector_name = "failing"
    failing.collect = AsyncMock(side_effect=RuntimeError("Failed"))

    success_2 = AsyncMock(spec=EvidenceCollectorBase)
    success_2.collector_name = "success_2"
    success_2.collect = AsyncMock()

    mock_store.create_evidence_pack = AsyncMock(return_value=mock_evidence_pack)
    mock_store.mark_evidence_pack_complete = AsyncMock(return_value=mock_evidence_pack)

    collector = EvidenceCollector(mock_store, mock_settings)
    collector.register_collector(success_1)
    collector.register_collector(failing)
    collector.register_collector(success_2)

    result = await collector.collect(open_bugcase)

    # Verify mark_evidence_pack_complete was called with only successful collectors
    assert mock_store.mark_evidence_pack_complete.called
    call_args = mock_store.mark_evidence_pack_complete.call_args
    sections = call_args[1]["sections_collected"]

    # Should have: metrics, system_state (auto-registered), success_1, success_2
    # Should NOT have: failing
    assert len(sections) == 4
    assert "metrics" in sections
    assert "system_state" in sections
    assert "success_1" in sections
    assert "success_2" in sections
    assert "failing" not in sections


def test_register_collector(mock_settings, mock_collector):
    """Test register_collector adds collector to list."""
    collector = EvidenceCollector(AsyncMock(), mock_settings)
    # EvidenceCollector auto-registers built-in collectors (MetricsCollector, SystemStateCollector)
    initial_count = len(collector.collectors)
    assert initial_count == 2
    collector.register_collector(mock_collector)
    assert len(collector.collectors) == initial_count + 1
    assert collector.collectors[-1] == mock_collector
