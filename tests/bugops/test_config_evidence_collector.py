"""Tests for ConfigEvidenceCollector."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from types import ModuleType

from src.crypto_news_aggregator.bugops.evidence.collectors.config_evidence import (
    ConfigEvidenceCollector,
)
from src.crypto_news_aggregator.bugops.models import BugCase, BugOpsSubsystem, CaseStatus, AlertSeverity, EvidenceReferenceAllocator


@pytest.fixture
def mock_settings():
    """Mock settings object with all required LLM and BugOps config keys."""
    settings = MagicMock()
    settings.LLM_DAILY_SOFT_LIMIT = 3.00
    settings.LLM_DAILY_HARD_LIMIT = 15.00
    settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES = 60
    settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES = 90
    settings.BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES = 120
    settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10
    settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES = 10
    settings.BUGOPS_INVESTIGATION_MODEL = "deepseek"
    settings.BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS = 12000
    settings.BUGOPS_EVIDENCE_MAX_TOTAL_CHARS = 60000
    return settings


@pytest.fixture
def mock_cost_tracker():
    """Mock cost_tracker module with CRITICAL_OPERATIONS."""
    module = ModuleType("cost_tracker")
    module.CRITICAL_OPERATIONS = {
        "briefing_generation",
        "briefing_generate",
        "briefing_critique",
        "entity_extraction",
    }
    return module


@pytest.fixture
def collector(mock_settings, mock_cost_tracker):
    """Create ConfigEvidenceCollector instance."""
    return ConfigEvidenceCollector(mock_settings, mock_cost_tracker)


@pytest.fixture
def sample_bugcase():
    """Create a sample BugCase for testing."""
    return BugCase(
        case_id="BUG-001",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test case",
        summary="Test summary",
        dedupe_key="test_1",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.BRIEFINGS.value,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_store():
    """Mock BugOpsStore."""
    store = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    return store


@pytest.fixture
def ref_allocator():
    """Create EvidenceReferenceAllocator for testing."""
    return EvidenceReferenceAllocator()


@pytest.mark.asyncio
async def test_collect_reads_llm_soft_limit(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that collector reads LLM_DAILY_SOFT_LIMIT from settings."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    # Verify store was called
    mock_store.update_evidence_pack_section.assert_called_once()
    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    assert update_dict["config_evidence"]["llm_daily_soft_limit"] == 3.00


@pytest.mark.asyncio
async def test_collect_reads_llm_hard_limit(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that collector reads LLM_DAILY_HARD_LIMIT from settings."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    assert update_dict["config_evidence"]["llm_daily_hard_limit"] == 15.00


@pytest.mark.asyncio
async def test_collect_reads_critical_operations(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that collector reads CRITICAL_OPERATIONS from cost_tracker and sorts them."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    critical_ops = update_dict["config_evidence"]["critical_operations"]
    assert isinstance(critical_ops, list)
    assert critical_ops == sorted(critical_ops)  # Verify it's sorted
    assert set(critical_ops) == {
        "briefing_generation",
        "briefing_generate",
        "briefing_critique",
        "entity_extraction",
    }


@pytest.mark.asyncio
async def test_collect_reads_bugops_thresholds(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that collector reads all BugOps freshness window thresholds."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    thresholds = update_dict["config_evidence"]["bugops_thresholds"]
    assert thresholds["article_freshness_window_minutes"] == 60
    assert thresholds["signal_freshness_window_minutes"] == 90
    assert thresholds["narrative_freshness_window_minutes"] == 120
    assert thresholds["recovery_window_minutes"] == 10
    assert thresholds["evidence_settling_window_minutes"] == 10


@pytest.mark.asyncio
async def test_collect_handles_missing_llm_settings(sample_bugcase, mock_store, ref_allocator):
    """Test that missing LLM settings are stored as None without raising."""
    settings = MagicMock(spec=[])  # Spec empty to simulate missing attributes
    settings.LLM_DAILY_SOFT_LIMIT = None
    settings.LLM_DAILY_HARD_LIMIT = None
    settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES = 60
    settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES = 90
    settings.BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES = 120
    settings.BUGOPS_RECOVERY_WINDOW_MINUTES = 10
    settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES = 10
    settings.BUGOPS_INVESTIGATION_MODEL = "deepseek"
    settings.BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS = 12000
    settings.BUGOPS_EVIDENCE_MAX_TOTAL_CHARS = 60000

    module = ModuleType("cost_tracker")
    module.CRITICAL_OPERATIONS = set()

    collector = ConfigEvidenceCollector(settings, module)
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    assert update_dict["config_evidence"]["llm_daily_soft_limit"] is None
    assert update_dict["config_evidence"]["llm_daily_hard_limit"] is None


@pytest.mark.asyncio
async def test_collect_handles_missing_critical_operations(sample_bugcase, mock_store, ref_allocator, mock_settings):
    """Test that missing CRITICAL_OPERATIONS is handled gracefully with empty list."""
    module = ModuleType("cost_tracker")
    # Simulate missing CRITICAL_OPERATIONS attribute

    collector = ConfigEvidenceCollector(mock_settings, module)
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    assert update_dict["config_evidence"]["critical_operations"] == []


@pytest.mark.asyncio
async def test_collect_adds_two_evidence_references(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that exactly two evidence references are added."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    evidence_refs = update_dict["evidence_references"]
    assert len(evidence_refs) == 2


@pytest.mark.asyncio
async def test_collect_reference_for_budget_threshold(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that one reference is added for budget threshold with actual value in description."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    evidence_refs = update_dict["evidence_references"]
    # Find the budget threshold reference
    budget_refs = [ref for ref in evidence_refs.values() if "soft limit" in ref["description"]]
    assert len(budget_refs) == 1

    budget_ref = budget_refs[0]
    assert "3.0" in budget_ref["description"]  # Actual value in description
    assert budget_ref["section"] == "config_evidence"
    assert budget_ref["field"] == "llm_daily_soft_limit"


@pytest.mark.asyncio
async def test_collect_reference_for_critical_operations(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that one reference is added for critical operations with actual values in description."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    evidence_refs = update_dict["evidence_references"]
    # Find the critical operations reference
    ops_refs = [ref for ref in evidence_refs.values() if "Critical operations" in ref["description"]]
    assert len(ops_refs) == 1

    ops_ref = ops_refs[0]
    assert "briefing_generation" in ops_ref["description"]  # Actual value in description
    assert ops_ref["section"] == "config_evidence"
    assert ops_ref["field"] == "critical_operations"


@pytest.mark.asyncio
async def test_collect_uses_allocator_for_references(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that ref_allocator.next_ref() is called and returns unique IDs."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    evidence_refs = update_dict["evidence_references"]
    ref_ids = list(evidence_refs.keys())

    # Should have two unique reference IDs
    assert len(ref_ids) == 2
    assert ref_ids[0] != ref_ids[1]
    assert ref_ids[0].startswith("E-")
    assert ref_ids[1].startswith("E-")


@pytest.mark.asyncio
async def test_collect_writes_timestamp(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that config_evidence_collected_at timestamp is written."""
    before = datetime.utcnow()
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)
    after = datetime.utcnow()

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    assert "config_evidence_collected_at" in update_dict
    timestamp = update_dict["config_evidence_collected_at"]
    assert isinstance(timestamp, datetime)
    assert before <= timestamp <= after


@pytest.mark.asyncio
async def test_collect_includes_investigation_config(collector, sample_bugcase, mock_store, ref_allocator):
    """Test that investigation_config is included with model and budget settings."""
    await collector.collect(sample_bugcase, "pack_001", mock_store, ref_allocator)

    call_args = mock_store.update_evidence_pack_section.call_args
    update_dict = call_args[0][1]

    investigation_config = update_dict["config_evidence"]["investigation_config"]
    assert investigation_config["investigation_model"] == "deepseek"
    assert investigation_config["investigation_max_input_tokens"] == 12000
    assert investigation_config["evidence_max_total_chars"] == 60000


@pytest.mark.asyncio
async def test_collector_name(collector):
    """Test that collector_name is set correctly."""
    assert collector.collector_name == "config_evidence"
