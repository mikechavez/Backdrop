"""Tests for RelatedCaseCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from crypto_news_aggregator.bugops.evidence.collectors.related_cases import RelatedCaseCollector
from crypto_news_aggregator.bugops.models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    EvidenceReferenceAllocator,
)


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.get_related_cases = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    return store


@pytest.fixture
def bugcase_current():
    """Create a current BugCase with root_subsystem and blast_radius."""
    return BugCase(
        case_id="case_current",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Current Issue",
        summary="Current issue summary",
        dedupe_key="test_current",
        source_types=["test"],
        root_subsystem="articles",
        blast_radius=["signals", "narratives"],
        affected_subsystems=["briefings"],
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
        last_seen_at=datetime.utcnow(),
    )


@pytest.fixture
def bugcase_related_1():
    """Create a related BugCase (same root_subsystem)."""
    return BugCase(
        case_id="case_related_1",
        status=CaseStatus.RESOLVED,
        severity=AlertSeverity.WARNING,
        alert_type="test",
        title="Related Issue 1",
        summary="Related issue 1",
        dedupe_key="test_related_1",
        source_types=["test"],
        root_subsystem="articles",
        blast_radius=[],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow() - timedelta(hours=2),
        last_seen_at=datetime.utcnow() - timedelta(hours=1),
    )


@pytest.fixture
def bugcase_related_2():
    """Create another related BugCase (affected_subsystems overlap)."""
    return BugCase(
        case_id="case_related_2",
        status=CaseStatus.RESOLVED,
        severity=AlertSeverity.INFO,
        alert_type="test",
        title="Related Issue 2",
        summary="Related issue 2",
        dedupe_key="test_related_2",
        source_types=["test"],
        root_subsystem="signals",
        blast_radius=[],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow() - timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_collector_with_related_cases(mock_store, bugcase_current, bugcase_related_1, bugcase_related_2):
    """Test RelatedCaseCollector when related cases are found."""
    # Setup mock to return related cases
    mock_store.get_related_cases.return_value = [bugcase_related_1, bugcase_related_2]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    # Verify store method was called with correct arguments
    mock_store.get_related_cases.assert_called_once()
    call_args = mock_store.get_related_cases.call_args
    assert call_args[1]["bugcase_id"] == "case_current"
    assert set(call_args[1]["subsystems"]) == {"articles", "signals", "narratives", "briefings"}
    assert call_args[1]["lookback_days"] == 7
    assert call_args[1]["limit"] == 10

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify related_cases list
    assert "related_cases" in section_data
    assert len(section_data["related_cases"]) == 2
    assert section_data["related_cases"][0]["case_id"] == "case_related_1"
    assert section_data["related_cases"][1]["case_id"] == "case_related_2"

    # Verify timestamp
    assert "related_cases_collected_at" in section_data
    assert isinstance(section_data["related_cases_collected_at"], datetime)

    # Verify evidence reference
    assert "evidence_references" in section_data
    refs = section_data["evidence_references"]
    assert len(refs) == 1
    ref_id = list(refs.keys())[0]
    assert "2 related BugCases" in refs[ref_id]["description"]
    assert refs[ref_id]["section"] == "related_cases"


@pytest.mark.asyncio
async def test_collector_with_no_related_cases(mock_store, bugcase_current):
    """Test RelatedCaseCollector when no related cases are found."""
    # Setup mock to return empty list
    mock_store.get_related_cases.return_value = []

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    # Verify store method was called
    mock_store.get_related_cases.assert_called_once()

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify empty list is written
    assert "related_cases" in section_data
    assert section_data["related_cases"] == []

    # Verify timestamp is still written
    assert "related_cases_collected_at" in section_data

    # Verify NO evidence reference when empty
    assert "evidence_references" not in section_data or len(section_data.get("evidence_references", {})) == 0


@pytest.mark.asyncio
async def test_collector_extracts_subsystems_correctly(mock_store, bugcase_current):
    """Test that collector extracts all subsystems from root_subsystem, blast_radius, and affected_subsystems."""
    mock_store.get_related_cases.return_value = []

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    # Verify subsystems were extracted and deduplicated
    call_args = mock_store.get_related_cases.call_args
    subsystems = call_args[1]["subsystems"]

    # Should have exactly 4 unique subsystems
    assert len(subsystems) == 4
    assert set(subsystems) == {"articles", "signals", "narratives", "briefings"}


@pytest.mark.asyncio
async def test_collector_handles_missing_subsystem_fields(mock_store):
    """Test collector handles BugCase with missing subsystem fields."""
    bugcase = BugCase(
        case_id="case_minimal",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.INFO,
        alert_type="test",
        title="Minimal Case",
        summary="Minimal",
        dedupe_key="test_minimal",
        source_types=["test"],
        root_subsystem=None,
        blast_radius=[],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )

    mock_store.get_related_cases.return_value = []

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    # Should handle gracefully with empty subsystems list
    call_args = mock_store.get_related_cases.call_args
    assert call_args[1]["subsystems"] == []


@pytest.mark.asyncio
async def test_collector_handles_store_error(mock_store, bugcase_current):
    """Test collector handles exceptions from store gracefully."""
    mock_store.get_related_cases.side_effect = Exception("Database connection error")

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    # Should not raise — handle error internally
    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    # Store update should not be called when exception occurs
    mock_store.update_evidence_pack_section.assert_not_called()


@pytest.mark.asyncio
async def test_collector_formats_timestamps_as_isoformat(mock_store, bugcase_current, bugcase_related_1):
    """Test that collector formats timestamps as ISO format strings."""
    mock_store.get_related_cases.return_value = [bugcase_related_1]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    related_dict = section_data["related_cases"][0]

    # Verify timestamps are ISO format strings
    assert isinstance(related_dict["first_seen_at"], str)
    assert isinstance(related_dict["last_seen_at"], str)
    assert "T" in related_dict["first_seen_at"]
    assert "T" in related_dict["last_seen_at"]


@pytest.mark.asyncio
async def test_collector_uses_ref_allocator(mock_store, bugcase_current, bugcase_related_1):
    """Test that collector uses EvidenceReferenceAllocator for reference IDs."""
    mock_store.get_related_cases.return_value = [bugcase_related_1]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    refs = section_data["evidence_references"]

    # Should use allocator-generated reference ID (E-001, E-002, etc.)
    ref_id = list(refs.keys())[0]
    assert ref_id.startswith("E-")
    assert ref_id in ["E-001", "E-002", "E-003", "E-004"]  # Allocator format


@pytest.mark.asyncio
async def test_collector_sorts_by_first_seen_descending(mock_store, bugcase_current):
    """Test that collector respects sort order from store (most recent first)."""
    # Create related cases with different timestamps
    recent_case = BugCase(
        case_id="case_recent",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Recent",
        summary="Recent",
        dedupe_key="test_recent",
        source_types=["test"],
        root_subsystem="articles",
        first_seen_at=datetime.utcnow() - timedelta(hours=1),
        last_seen_at=datetime.utcnow(),
    )

    old_case = BugCase(
        case_id="case_old",
        status=CaseStatus.RESOLVED,
        severity=AlertSeverity.INFO,
        alert_type="test",
        title="Old",
        summary="Old",
        dedupe_key="test_old",
        source_types=["test"],
        root_subsystem="articles",
        first_seen_at=datetime.utcnow() - timedelta(days=5),
        last_seen_at=datetime.utcnow() - timedelta(days=5),
    )

    # Store returns cases already sorted by store (descending)
    mock_store.get_related_cases.return_value = [recent_case, old_case]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    related_cases = section_data["related_cases"]

    # Verify order is preserved
    assert related_cases[0]["case_id"] == "case_recent"
    assert related_cases[1]["case_id"] == "case_old"


@pytest.mark.asyncio
async def test_collector_name_attribute(mock_store, bugcase_current):
    """Test that collector has correct name attribute."""
    collector = RelatedCaseCollector()
    assert collector.collector_name == "related_cases"


@pytest.mark.asyncio
async def test_collector_with_single_related_case(mock_store, bugcase_current, bugcase_related_1):
    """Test collector correctly handles single related case."""
    mock_store.get_related_cases.return_value = [bugcase_related_1]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify single case is included
    assert len(section_data["related_cases"]) == 1
    assert section_data["related_cases"][0]["case_id"] == "case_related_1"

    # Verify evidence reference mentions "1 related BugCases"
    refs = section_data["evidence_references"]
    ref_id = list(refs.keys())[0]
    assert "1 related BugCases" in refs[ref_id]["description"]


@pytest.mark.asyncio
async def test_collector_with_ten_related_cases(mock_store, bugcase_current):
    """Test collector correctly handles maximum 10 related cases."""
    # Create 10 related cases
    related_cases = [
        BugCase(
            case_id=f"case_related_{i}",
            status=CaseStatus.RESOLVED,
            severity=AlertSeverity.WARNING,
            alert_type="test",
            title=f"Related {i}",
            summary=f"Related {i}",
            dedupe_key=f"test_related_{i}",
            source_types=["test"],
            root_subsystem="articles",
            first_seen_at=datetime.utcnow() - timedelta(hours=i),
            last_seen_at=datetime.utcnow() - timedelta(hours=i),
        )
        for i in range(10)
    ]

    mock_store.get_related_cases.return_value = related_cases

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify all 10 cases are included
    assert len(section_data["related_cases"]) == 10

    # Verify evidence reference mentions "10 related BugCases"
    refs = section_data["evidence_references"]
    ref_id = list(refs.keys())[0]
    assert "10 related BugCases" in refs[ref_id]["description"]


@pytest.mark.asyncio
async def test_collector_preserves_bugcase_fields(mock_store, bugcase_current, bugcase_related_1):
    """Test collector preserves all expected fields from related BugCase."""
    mock_store.get_related_cases.return_value = [bugcase_related_1]

    collector = RelatedCaseCollector()
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase_current, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    related_dict = section_data["related_cases"][0]

    # Verify all expected fields are present
    expected_fields = {"case_id", "root_subsystem", "severity", "status", "first_seen_at", "last_seen_at", "title"}
    assert set(related_dict.keys()) == expected_fields

    # Verify field values match
    assert related_dict["case_id"] == "case_related_1"
    assert related_dict["root_subsystem"] == "articles"
    assert related_dict["severity"] == AlertSeverity.WARNING
    assert related_dict["status"] == CaseStatus.RESOLVED
    assert related_dict["title"] == "Related Issue 1"
