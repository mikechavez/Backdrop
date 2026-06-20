"""Tests for EvidencePack persistence layer."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import (
    EvidencePackCreate,
    EvidencePack,
    EvidencePackStatus,
    AlertSeverity,
    CollectionError,
    LLMTraceSummary,
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


def sample_evidence_pack_create() -> EvidencePackCreate:
    """Create a sample EvidencePackCreate for testing."""
    return EvidencePackCreate(
        pack_id="ep_case_001_1234567890",
        bugcase_id="case_001",
        incident_first_seen_at=datetime.utcnow(),
        incident_last_seen_at=datetime.utcnow(),
        root_subsystem="worker",
        severity=AlertSeverity.HIGH,
        primary_signal="memory_leak",
        blast_radius=["worker", "scheduler"],
    )


def sample_evidence_pack_doc() -> dict:
    """Create a minimal valid Evidence Pack document for mocking."""
    now = datetime.utcnow()
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "pack_id": "ep_case_001_1234567890",
        "bugcase_id": "case_001",
        "collection_started_at": now,
        "collection_completed_at": None,
        "collection_duration_ms": None,
        "collection_status": "partial",
        "incident_first_seen_at": now,
        "incident_last_seen_at": now,
        "root_subsystem": "worker",
        "severity": "high",
        "primary_signal": "memory_leak",
        "blast_radius": ["worker", "scheduler"],
        "subsystem_metrics": [],
        "subsystem_metrics_collected_at": None,
        "system_state": {},
        "system_state_collected_at": None,
        "healthy_signals": [],
        "related_cases": [],
        "related_cases_collected_at": None,
        "deploy_context": [],
        "deploy_context_collected_at": None,
        "config_evidence": {},
        "config_evidence_collected_at": None,
        "llm_trace_summary": None,
        "llm_trace_summary_collected_at": None,
        "log_excerpts": [],
        "evidence_references": {},
        "sections_collected": [],
        "sections_missing": [],
        "redactions_applied": 0,
        "truncation_applied": [],
        "total_chars": 0,
        "collection_errors": [],
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_create_evidence_pack_inserts_and_returns_with_id(store):
    """Test create_evidence_pack inserts document and returns EvidencePack with string id."""
    pack = sample_evidence_pack_create()

    # Mock insert_one
    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = ObjectId("507f1f77bcf86cd799439011")
    store.evidence_packs_collection.insert_one = mock_insert

    # Execute
    result = await store.create_evidence_pack(pack)

    # Verify
    assert result.pack_id == "ep_case_001_1234567890"
    assert result.bugcase_id == "case_001"
    assert result.id == "507f1f77bcf86cd799439011"
    assert isinstance(result.id, str)
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_get_evidence_pack_returns_pack_by_pack_id(store):
    """Test get_evidence_pack retrieves pack by pack_id."""
    pack_doc = sample_evidence_pack_doc()

    mock_find_one = AsyncMock()
    mock_find_one.return_value = pack_doc
    store.evidence_packs_collection.find_one = mock_find_one

    # Execute
    result = await store.get_evidence_pack("ep_case_001_1234567890")

    # Verify
    assert result is not None
    assert result.pack_id == "ep_case_001_1234567890"
    mock_find_one.assert_called_once_with({"pack_id": "ep_case_001_1234567890"})


@pytest.mark.asyncio
async def test_get_evidence_pack_returns_none_when_not_found(store):
    """Test get_evidence_pack returns None when pack not found."""
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    store.evidence_packs_collection.find_one = mock_find_one

    # Execute
    result = await store.get_evidence_pack("nonexistent_pack_id")

    # Verify
    assert result is None


@pytest.mark.asyncio
async def test_get_evidence_pack_for_case_queries_by_bugcase_id(store):
    """Test get_evidence_pack_for_case retrieves pack by bugcase_id."""
    pack_doc = sample_evidence_pack_doc()

    mock_find_one = AsyncMock()
    mock_find_one.return_value = pack_doc
    store.evidence_packs_collection.find_one = mock_find_one

    # Execute
    result = await store.get_evidence_pack_for_case("case_001")

    # Verify
    assert result is not None
    assert result.bugcase_id == "case_001"
    mock_find_one.assert_called_once_with({"bugcase_id": "case_001"})


@pytest.mark.asyncio
async def test_get_evidence_pack_for_case_returns_none_when_not_found(store):
    """Test get_evidence_pack_for_case returns None when no pack exists for case."""
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    store.evidence_packs_collection.find_one = mock_find_one

    # Execute
    result = await store.get_evidence_pack_for_case("case_with_no_pack")

    # Verify
    assert result is None


@pytest.mark.asyncio
async def test_update_evidence_pack_section_updates_specified_fields_only(store):
    """Test update_evidence_pack_section updates only specified fields."""
    updated_pack_doc = sample_evidence_pack_doc()
    updated_pack_doc["subsystem_metrics"] = [{"subsystem": "worker", "artifact_count": 5}]

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = updated_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    section_data = {
        "subsystem_metrics": [{"subsystem": "worker", "artifact_count": 5}],
        "subsystem_metrics_collected_at": datetime.utcnow(),
    }
    result = await store.update_evidence_pack_section("ep_case_001_1234567890", section_data)

    # Verify
    assert result is not None
    assert result.pack_id == "ep_case_001_1234567890"
    # Verify the update used $set (partial update, not replacement)
    call_args = mock_find_one_and_update.call_args
    assert "$set" in call_args[0][1]


@pytest.mark.asyncio
async def test_update_evidence_pack_section_sets_updated_at_automatically(store):
    """Test update_evidence_pack_section sets updated_at automatically."""
    now = datetime.utcnow()

    updated_pack_doc = sample_evidence_pack_doc()
    updated_pack_doc["updated_at"] = now
    updated_pack_doc["subsystem_metrics"] = []

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = updated_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    section_data = {"subsystem_metrics": []}
    result = await store.update_evidence_pack_section("ep_case_001_1234567890", section_data, updated_at=now)

    # Verify
    assert result is not None
    assert result.pack_id == "ep_case_001_1234567890"
    call_args = mock_find_one_and_update.call_args
    assert call_args[0][1]["$set"]["updated_at"] == now
    assert call_args[0][1]["$set"]["subsystem_metrics"] == []


@pytest.mark.asyncio
async def test_update_evidence_pack_section_merges_evidence_references(store):
    """Test update_evidence_pack_section merges evidence_references instead of replacing."""
    # After first write with E-001, E-002
    updated_pack_doc_1 = sample_evidence_pack_doc()
    updated_pack_doc_1["evidence_references"] = {
        "E-001": {"section": "metrics", "key": "cpu_usage"},
        "E-002": {"section": "metrics", "key": "memory_usage"},
    }

    # After second write with E-003, E-004 (merged with prior)
    updated_pack_doc_2 = sample_evidence_pack_doc()
    updated_pack_doc_2["evidence_references"] = {
        "E-001": {"section": "metrics", "key": "cpu_usage"},
        "E-002": {"section": "metrics", "key": "memory_usage"},
        "E-003": {"section": "logs", "key": "error_line_42"},
        "E-004": {"section": "logs", "key": "error_line_43"},
    }

    mock_find_one_and_update = AsyncMock()
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # First write: E-001, E-002
    section_data_1 = {
        "evidence_references": {
            "E-001": {"section": "metrics", "key": "cpu_usage"},
            "E-002": {"section": "metrics", "key": "memory_usage"},
        }
    }
    mock_find_one_and_update.return_value = updated_pack_doc_1
    await store.update_evidence_pack_section("ep_case_001_1234567890", section_data_1)

    # Verify first call used dot-notation
    call_args_1 = mock_find_one_and_update.call_args
    set_dict_1 = call_args_1[0][1]["$set"]
    assert "evidence_references.E-001" in set_dict_1
    assert "evidence_references.E-002" in set_dict_1

    # Second write: E-003, E-004 (should merge, not overwrite)
    section_data_2 = {
        "evidence_references": {
            "E-003": {"section": "logs", "key": "error_line_42"},
            "E-004": {"section": "logs", "key": "error_line_43"},
        }
    }
    mock_find_one_and_update.return_value = updated_pack_doc_2
    result = await store.update_evidence_pack_section("ep_case_001_1234567890", section_data_2)

    # Verify the second call used dot-notation for evidence_references
    call_args_2 = mock_find_one_and_update.call_args
    set_dict_2 = call_args_2[0][1]["$set"]
    # Check that dot-notation is used (e.g., "evidence_references.E-003")
    assert "evidence_references.E-003" in set_dict_2
    assert "evidence_references.E-004" in set_dict_2
    # Verify result contains all references (merged)
    assert result is not None
    assert len(result.evidence_references) == 4


@pytest.mark.asyncio
async def test_update_evidence_pack_section_does_not_overwrite_prior_references(store):
    """Test update_evidence_pack_section preserves prior evidence_references entries."""
    updated_pack_doc = sample_evidence_pack_doc()
    updated_pack_doc["evidence_references"] = {
        "E-001": {"section": "metrics", "key": "cpu_usage"},
        "E-002": {"section": "metrics", "key": "memory_usage"},
        "E-003": {"section": "logs", "key": "error_line_42"},
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = updated_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute: Write new references (E-003) assuming E-001, E-002 already exist
    section_data = {
        "evidence_references": {
            "E-003": {"section": "logs", "key": "error_line_42"},
        }
    }
    result = await store.update_evidence_pack_section("ep_case_001_1234567890", section_data)

    # Verify: The update call should use dot-notation, not replace entire dict
    call_args = mock_find_one_and_update.call_args
    set_dict = call_args[0][1]["$set"]
    # Should have dot-notation key for the new reference
    assert "evidence_references.E-003" in set_dict
    # Should NOT have "evidence_references" as a top-level key (that would replace the entire dict)
    # Instead it should only have dot-notation keys like "evidence_references.E-XXX"
    top_level_keys = [k for k in set_dict.keys() if k == "evidence_references"]
    assert len(top_level_keys) == 0, "Should not have top-level 'evidence_references' key"
    # Verify result has all references
    assert result is not None
    assert len(result.evidence_references) == 3


@pytest.mark.asyncio
async def test_mark_evidence_pack_complete_sets_status_complete_when_no_errors(store):
    """Test mark_evidence_pack_complete sets COMPLETE status when no errors and no missing sections."""
    # First call to get_evidence_pack
    current_pack_doc = sample_evidence_pack_doc()
    current_pack_doc["collection_errors"] = []
    current_pack_doc["sections_missing"] = []

    # Second call after update
    completed_pack_doc = sample_evidence_pack_doc()
    completed_pack_doc["collection_status"] = "complete"
    completed_pack_doc["collection_completed_at"] = datetime.utcnow()
    completed_pack_doc["collection_duration_ms"] = 5000
    completed_pack_doc["sections_collected"] = ["metrics", "logs"]
    completed_pack_doc["total_chars"] = 50000

    mock_find_one = AsyncMock()
    mock_find_one.return_value = current_pack_doc
    store.evidence_packs_collection.find_one = mock_find_one

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = completed_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    completed_at = datetime.utcnow()
    result = await store.mark_evidence_pack_complete(
        "ep_case_001_1234567890",
        completed_at,
        5000,
        ["metrics", "logs"],
        50000
    )

    # Verify
    assert result is not None
    assert result.collection_status == EvidencePackStatus.COMPLETE
    call_args = mock_find_one_and_update.call_args
    assert call_args[0][1]["$set"]["collection_status"] == EvidencePackStatus.COMPLETE


@pytest.mark.asyncio
async def test_mark_evidence_pack_complete_sets_status_partial_when_has_errors(store):
    """Test mark_evidence_pack_complete sets PARTIAL status when collection_errors exist."""
    current_pack_doc = sample_evidence_pack_doc()
    error = CollectionError(
        source="railway_api",
        error_type="timeout",
        error_message="API timeout after 30s"
    )
    current_pack_doc["collection_errors"] = [error.model_dump()]
    current_pack_doc["sections_missing"] = []

    completed_pack_doc = sample_evidence_pack_doc()
    completed_pack_doc["collection_status"] = "partial"
    completed_pack_doc["collection_completed_at"] = datetime.utcnow()
    completed_pack_doc["collection_duration_ms"] = 5000
    completed_pack_doc["sections_collected"] = ["metrics"]
    completed_pack_doc["total_chars"] = 30000
    completed_pack_doc["collection_errors"] = [error.model_dump()]

    mock_find_one = AsyncMock()
    mock_find_one.return_value = current_pack_doc
    store.evidence_packs_collection.find_one = mock_find_one

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = completed_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    completed_at = datetime.utcnow()
    result = await store.mark_evidence_pack_complete(
        "ep_case_001_1234567890",
        completed_at,
        5000,
        ["metrics"],
        30000
    )

    # Verify
    assert result is not None
    assert result.collection_status == EvidencePackStatus.PARTIAL
    call_args = mock_find_one_and_update.call_args
    assert call_args[0][1]["$set"]["collection_status"] == EvidencePackStatus.PARTIAL


@pytest.mark.asyncio
async def test_mark_evidence_pack_complete_sets_status_partial_when_sections_missing(store):
    """Test mark_evidence_pack_complete sets PARTIAL status when sections_missing is non-empty."""
    current_pack_doc = sample_evidence_pack_doc()
    current_pack_doc["collection_errors"] = []
    current_pack_doc["sections_missing"] = [
        {
            "section": "deploy_context",
            "reason": "Railway API unavailable"
        }
    ]

    completed_pack_doc = sample_evidence_pack_doc()
    completed_pack_doc["collection_status"] = "partial"
    completed_pack_doc["collection_completed_at"] = datetime.utcnow()
    completed_pack_doc["collection_duration_ms"] = 5000
    completed_pack_doc["sections_collected"] = ["metrics", "logs"]
    completed_pack_doc["total_chars"] = 45000
    completed_pack_doc["sections_missing"] = [
        {
            "section": "deploy_context",
            "reason": "Railway API unavailable"
        }
    ]

    mock_find_one = AsyncMock()
    mock_find_one.return_value = current_pack_doc
    store.evidence_packs_collection.find_one = mock_find_one

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = completed_pack_doc
    store.evidence_packs_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    completed_at = datetime.utcnow()
    result = await store.mark_evidence_pack_complete(
        "ep_case_001_1234567890",
        completed_at,
        5000,
        ["metrics", "logs"],
        45000
    )

    # Verify
    assert result is not None
    assert result.collection_status == EvidencePackStatus.PARTIAL
    call_args = mock_find_one_and_update.call_args
    assert call_args[0][1]["$set"]["collection_status"] == EvidencePackStatus.PARTIAL


@pytest.mark.asyncio
async def test_mark_evidence_pack_complete_returns_none_when_pack_not_found(store):
    """Test mark_evidence_pack_complete returns None when pack not found."""
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    store.evidence_packs_collection.find_one = mock_find_one

    # Execute
    result = await store.mark_evidence_pack_complete(
        "nonexistent_pack_id",
        datetime.utcnow(),
        5000,
        ["metrics"],
        30000
    )

    # Verify
    assert result is None


@pytest.mark.asyncio
async def test_config_keys_accessible(store):
    """Test that new config keys are accessible via settings."""
    from crypto_news_aggregator.core.config import settings

    # Verify all new config keys exist and have expected defaults
    assert hasattr(settings, "BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES")
    assert settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES == 10

    assert hasattr(settings, "BUGOPS_LOG_WINDOW_MINUTES")
    assert settings.BUGOPS_LOG_WINDOW_MINUTES == 10

    assert hasattr(settings, "BUGOPS_LOG_LINE_CAP")
    assert settings.BUGOPS_LOG_LINE_CAP == 200

    assert hasattr(settings, "BUGOPS_EVIDENCE_MAX_TOTAL_CHARS")
    assert settings.BUGOPS_EVIDENCE_MAX_TOTAL_CHARS == 60000

    assert hasattr(settings, "BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS")
    assert settings.BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS == 12000

    assert hasattr(settings, "RAILWAY_API_TOKEN")
    # Token value depends on environment; just verify it's set/accessible
    assert isinstance(settings.RAILWAY_API_TOKEN, str)
