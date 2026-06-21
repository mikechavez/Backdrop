"""Tests for LLMTraceCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from crypto_news_aggregator.bugops.evidence.collectors.llm_traces import LLMTraceCollector
from crypto_news_aggregator.bugops.models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    BugOpsSubsystem,
    EvidenceReferenceAllocator,
    LLMTraceSummary,
)


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    return store


def create_mock_db_with_traces(traces):
    """Helper to create a mock database with LLM traces."""
    db = AsyncMock()
    llm_traces_collection = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=traces)
    llm_traces_collection.find = MagicMock(return_value=mock_cursor)

    def get_collection(name):
        if name == "llm_traces":
            return llm_traces_collection
        return AsyncMock()

    db.__getitem__.side_effect = get_collection
    return db


@pytest.fixture
def bugcase_basic():
    """Create a basic BugCase for testing."""
    now = datetime.utcnow()
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
        blast_radius=[],
        first_seen_at=now - timedelta(minutes=90),
        last_seen_at=now,
    )


@pytest.fixture
def bugcase_no_last_seen():
    """Create a BugCase with no last_seen_at."""
    now = datetime.utcnow()
    return BugCase(
        case_id="case_2",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.WARNING,
        alert_type="test",
        title="Test Case 2",
        summary="Test Summary 2",
        dedupe_key="test_2",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.BRIEFINGS.value,
        blast_radius=[],
        first_seen_at=now - timedelta(minutes=90),
        last_seen_at=None,
    )


@pytest.mark.asyncio
async def test_llm_trace_collector_with_traces(mock_store, bugcase_basic):
    """Test LLMTraceCollector with multiple traces in window."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "briefing_generate",
            "model": "claude-haiku-4-5-20251001",
            "cost": 0.031,
            "input_tokens": 1200,
            "output_tokens": 800,
            "cached": False,
            "timestamp": now - timedelta(minutes=5),
        },
        {
            "operation": "briefing_generate",
            "model": "claude-haiku-4-5-20251001",
            "cost": 0.031,
            "input_tokens": 1200,
            "output_tokens": 800,
            "cached": False,
            "timestamp": now - timedelta(minutes=10),
        },
        {
            "operation": "entity_extraction",
            "model": "claude-haiku-4-5-20251001",
            "cost": 0.015,
            "input_tokens": 500,
            "output_tokens": 200,
            "cached": True,
            "timestamp": now - timedelta(minutes=15),
        },
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    # Run collector
    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Verify store was called
    assert mock_store.update_evidence_pack_section.called
    call_args = mock_store.update_evidence_pack_section.call_args
    assert call_args[0][0] == "pack_1"

    update_data = call_args[0][1]
    assert "llm_trace_summary" in update_data
    assert "llm_trace_summary_collected_at" in update_data
    assert "evidence_references" in update_data

    # Verify summary structure
    summary_dict = update_data["llm_trace_summary"]
    assert summary_dict["total_calls"] == 3
    assert summary_dict["total_cost"] == pytest.approx(0.077, abs=0.001)
    assert summary_dict["total_input_tokens"] == 2900
    assert summary_dict["total_output_tokens"] == 1800
    assert summary_dict["cached_calls"] == 1

    # Verify operation breakdown
    ops = summary_dict["operation_breakdown"]
    assert "briefing_generate" in ops
    assert "entity_extraction" in ops
    assert ops["briefing_generate"]["calls"] == 2
    assert ops["briefing_generate"]["cost"] == pytest.approx(0.062, abs=0.001)
    assert ops["entity_extraction"]["calls"] == 1
    assert ops["entity_extraction"]["cost"] == pytest.approx(0.015, abs=0.001)

    # Verify recent traces
    recent = summary_dict["recent_traces"]
    assert len(recent) == 3
    assert recent[0]["operation"] == "briefing_generate"
    assert recent[2]["operation"] == "entity_extraction"


@pytest.mark.asyncio
async def test_llm_trace_collector_uses_timestamp_field(mock_store, bugcase_basic):
    """Test that collector uses 'timestamp' field (NOT 'created_at')."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "test_op",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=30),
        }
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Verify the query used 'timestamp' field
    llm_collection = mock_db.__getitem__("llm_traces")
    call_args = llm_collection.find.call_args
    query = call_args[0][0]
    assert "timestamp" in query
    assert "$gte" in query["timestamp"]
    assert "$lte" in query["timestamp"]


@pytest.mark.asyncio
async def test_llm_trace_collector_uses_cost_field(mock_store, bugcase_basic):
    """Test that collector uses 'cost' field for aggregation (NOT 'cost_usd')."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "test_op",
            "model": "test-model",
            "cost": 0.0012,  # Use 'cost', not 'cost_usd'
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=30),
        }
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    assert summary["total_cost"] == pytest.approx(0.0012, abs=0.0001)


@pytest.mark.asyncio
async def test_llm_trace_collector_window_calculation(mock_store, bugcase_basic):
    """Test that window extends 60 minutes before first_seen_at."""
    now = datetime.utcnow()
    traces = []

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Check the query window
    llm_collection = mock_db.__getitem__("llm_traces")
    call_args = llm_collection.find.call_args
    query = call_args[0][0]
    window_start = query["timestamp"]["$gte"]
    window_end = query["timestamp"]["$lte"]

    # Window start should be 150 minutes before now (90 + 60)
    expected_start = bugcase_basic.first_seen_at - timedelta(minutes=60)
    assert abs((window_start - expected_start).total_seconds()) < 1

    # Window end should be bugcase last_seen_at
    assert window_end == bugcase_basic.last_seen_at


@pytest.mark.asyncio
async def test_llm_trace_collector_window_uses_first_seen_when_no_last_seen(
    mock_store, bugcase_no_last_seen
):
    """Test that window end is first_seen_at when last_seen_at is None."""
    traces = []
    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_no_last_seen, "pack_1", mock_store, ref_allocator)

    # Check the query window
    llm_collection = mock_db.__getitem__("llm_traces")
    call_args = llm_collection.find.call_args
    query = call_args[0][0]
    window_end = query["timestamp"]["$lte"]

    # Window end should be first_seen_at when last_seen_at is None
    assert window_end == bugcase_no_last_seen.first_seen_at


@pytest.mark.asyncio
async def test_llm_trace_collector_empty_traces(mock_store, bugcase_basic):
    """Test LLMTraceCollector when no traces found in window."""
    mock_db = create_mock_db_with_traces([])
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Verify store was called with empty summary
    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    assert summary["total_calls"] == 0
    assert summary["total_cost"] == 0.0
    assert summary["cached_calls"] == 0
    assert len(summary["operation_breakdown"]) == 0
    assert len(summary["recent_traces"]) == 0


@pytest.mark.asyncio
async def test_llm_trace_collector_recent_traces_limit_10(mock_store, bugcase_basic):
    """Test that recent_traces is limited to last 10 traces."""
    now = datetime.utcnow()
    # Create 15 traces
    traces = [
        {
            "operation": f"op_{i}",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=i),
        }
        for i in range(15)
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    # Recent traces should have exactly 10 entries
    assert len(summary["recent_traces"]) == 10


@pytest.mark.asyncio
async def test_llm_trace_collector_evidence_references(mock_store, bugcase_basic):
    """Test that collector adds two evidence references: cost and operations."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "briefing_generate",
            "model": "test-model",
            "cost": 0.05,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=10),
        },
        {
            "operation": "entity_extraction",
            "model": "test-model",
            "cost": 0.02,
            "input_tokens": 50,
            "output_tokens": 25,
            "cached": False,
            "timestamp": now - timedelta(minutes=5),
        },
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    refs = update_data["evidence_references"]

    # Should have exactly 2 references
    assert len(refs) == 2
    assert "E-001" in refs
    assert "E-002" in refs

    # First reference should be about cost
    ref_cost = refs["E-001"]
    assert "cost" in ref_cost["description"].lower() or "spend" in ref_cost["description"].lower()
    assert ref_cost["section"] == "llm_trace_summary"
    assert ref_cost["field"] == "total_cost"

    # Second reference should be about operations
    ref_ops = refs["E-002"]
    assert "operation" in ref_ops["description"].lower()
    assert ref_ops["section"] == "llm_trace_summary"
    assert ref_ops["field"] == "operation_breakdown"


@pytest.mark.asyncio
async def test_llm_trace_collector_ref_allocator_usage(mock_store, bugcase_basic):
    """Test that collector uses ref_allocator.next_ref() for collision-free IDs."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "test_op",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=10),
        }
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    # Allocator should start at E-001
    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Allocator should now be at 2 (used E-001 and E-002)
    assert ref_allocator.current_count() == 2


@pytest.mark.asyncio
async def test_llm_trace_collector_cached_flag_tracking(mock_store, bugcase_basic):
    """Test that collector correctly tracks cached_calls."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "op1",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": True,
            "timestamp": now - timedelta(minutes=30),
        },
        {
            "operation": "op2",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=20),
        },
        {
            "operation": "op3",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": True,
            "timestamp": now - timedelta(minutes=10),
        },
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    # Should have exactly 2 cached calls
    assert summary["cached_calls"] == 2


@pytest.mark.asyncio
async def test_llm_trace_collector_operation_last_at_timestamp(mock_store, bugcase_basic):
    """Test that operation breakdown includes last_at timestamp."""
    now = datetime.utcnow()
    traces = [
        {
            "operation": "briefing_generate",
            "model": "test-model",
            "cost": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "cached": False,
            "timestamp": now - timedelta(minutes=30),
        },
        {
            "operation": "briefing_generate",
            "model": "test-model",
            "cost": 0.002,
            "input_tokens": 150,
            "output_tokens": 75,
            "cached": False,
            "timestamp": now - timedelta(minutes=5),
        },
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    op_data = summary["operation_breakdown"]["briefing_generate"]
    assert "last_at" in op_data
    # Should be the more recent timestamp (5 minutes ago, not 30)
    assert op_data["last_at"] is not None


@pytest.mark.asyncio
async def test_llm_trace_collector_missing_fields_default_safely(mock_store, bugcase_basic):
    """Test that collector handles missing optional fields safely."""
    now = datetime.utcnow()
    # Trace with some fields missing
    traces = [
        {
            "operation": "test_op",
            "model": "test-model",
            # Missing: cost, input_tokens, output_tokens, cached
            "timestamp": now - timedelta(minutes=10),
        }
    ]

    mock_db = create_mock_db_with_traces(traces)
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    # Should not raise
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    # Should use defaults (0.0, 0, False)
    assert summary["total_cost"] == 0.0
    assert summary["total_input_tokens"] == 0
    assert summary["total_output_tokens"] == 0
    assert summary["cached_calls"] == 0


@pytest.mark.asyncio
async def test_llm_trace_collector_sorts_by_timestamp_descending(mock_store, bugcase_basic):
    """Test that collector sorts results by timestamp descending (most recent first)."""
    mock_db = create_mock_db_with_traces([])
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)

    # Verify sort was called with descending order
    llm_collection = mock_db.__getitem__("llm_traces")
    sort_call = llm_collection.find.return_value.sort.call_args
    assert sort_call[0][0] == "timestamp"
    assert sort_call[0][1] == -1  # -1 means descending


@pytest.mark.asyncio
async def test_llm_trace_collector_collected_at_timestamp(mock_store, bugcase_basic):
    """Test that collector sets collected_at timestamp."""
    mock_db = create_mock_db_with_traces([])
    collector = LLMTraceCollector(mock_db)

    ref_allocator = EvidenceReferenceAllocator()
    before = datetime.utcnow()
    await collector.collect(bugcase_basic, "pack_1", mock_store, ref_allocator)
    after = datetime.utcnow()

    call_args = mock_store.update_evidence_pack_section.call_args
    update_data = call_args[0][1]
    summary = update_data["llm_trace_summary"]

    # Summary should have collected_at
    assert "collected_at" in summary
    collected_at = summary["collected_at"]
    assert before <= collected_at <= after
