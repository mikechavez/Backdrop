"""Tests for Evidence Pack models."""

import pytest
from datetime import datetime, timedelta
from crypto_news_aggregator.bugops.models import (
    EvidencePackStatus,
    CollectionError,
    LogExcerptSection,
    SectionMetrics,
    LLMTraceRecord,
    LLMTraceSummary,
    EvidenceReferenceAllocator,
    EvidencePackCreate,
    EvidencePack,
    BugOpsSubsystem,
    AlertSeverity,
)


class TestEvidencePackStatus:
    """Tests for EvidencePackStatus enum."""

    def test_enum_values(self):
        """Test enum values are correct strings."""
        assert EvidencePackStatus.COMPLETE.value == "complete"
        assert EvidencePackStatus.PARTIAL.value == "partial"

    def test_enum_count(self):
        """Test enum has exactly 2 values."""
        assert len(EvidencePackStatus) == 2


class TestCollectionError:
    """Tests for CollectionError model."""

    def test_collection_error_instantiation(self):
        """Test CollectionError instantiates with required fields."""
        err = CollectionError(
            source="railway_logs",
            error_type="TimeoutError",
            error_message="API timeout after 30s",
        )
        assert err.source == "railway_logs"
        assert err.error_type == "TimeoutError"
        assert err.error_message == "API timeout after 30s"
        assert isinstance(err.attempted_at, datetime)

    def test_collection_error_auto_timestamp(self):
        """Test CollectionError auto-sets attempted_at."""
        before = datetime.utcnow()
        err = CollectionError(
            source="deploy_context",
            error_type="ConnectionError",
            error_message="Connection refused",
        )
        after = datetime.utcnow()
        assert before <= err.attempted_at <= after


class TestLogExcerptSection:
    """Tests for LogExcerptSection model."""

    def test_log_excerpt_section_instantiation(self):
        """Test LogExcerptSection instantiates with all fields."""
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=10)
        window_end = now

        section = LogExcerptSection(
            service="fastapi",
            lines_fetched=500,
            lines_stored=200,
            truncated=True,
            window_start=window_start,
            window_end=window_end,
            excerpts=["[ERROR] Database connection failed", "[WARN] Retry attempt 2"],
        )
        assert section.service == "fastapi"
        assert section.lines_fetched == 500
        assert section.lines_stored == 200
        assert section.truncated is True
        assert section.window_start == window_start
        assert section.window_end == window_end
        assert len(section.excerpts) == 2

    def test_log_excerpt_section_default_excerpts(self):
        """Test LogExcerptSection defaults excerpts to empty list."""
        section = LogExcerptSection(
            service="celery_worker",
            lines_fetched=100,
            lines_stored=100,
            truncated=False,
            window_start=datetime.utcnow() - timedelta(minutes=10),
            window_end=datetime.utcnow(),
        )
        assert section.excerpts == []

    def test_log_excerpt_section_auto_timestamp(self):
        """Test LogExcerptSection auto-sets collected_at."""
        now = datetime.utcnow()
        section = LogExcerptSection(
            service="celery_scheduler",
            lines_fetched=50,
            lines_stored=50,
            truncated=False,
            window_start=now - timedelta(minutes=10),
            window_end=now,
        )
        assert isinstance(section.collected_at, datetime)
        assert section.collected_at >= now


class TestSectionMetrics:
    """Tests for SectionMetrics model."""

    def test_section_metrics_instantiation(self):
        """Test SectionMetrics instantiates with subsystem."""
        now = datetime.utcnow()
        metrics = SectionMetrics(
            subsystem="articles",
            last_artifact_at=now - timedelta(minutes=5),
            artifact_count=1250,
            freshness_indicator="5 minutes ago",
        )
        assert metrics.subsystem == "articles"
        assert metrics.artifact_count == 1250
        assert metrics.freshness_indicator == "5 minutes ago"

    def test_section_metrics_optional_fields_default_none(self):
        """Test SectionMetrics optional fields default to None."""
        metrics = SectionMetrics(subsystem="signals")
        assert metrics.last_artifact_at is None
        assert metrics.artifact_count is None
        assert metrics.freshness_indicator is None


class TestLLMTraceRecord:
    """Tests for LLMTraceRecord model."""

    def test_llm_trace_record_instantiation(self):
        """Test LLMTraceRecord instantiates with all fields."""
        now = datetime.utcnow()
        record = LLMTraceRecord(
            timestamp=now,
            operation="narrative_generation",
            model="gpt-4",
            cost=0.045,
            input_tokens=150,
            output_tokens=500,
        )
        assert record.operation == "narrative_generation"
        assert record.cost == 0.045
        assert record.input_tokens == 150
        assert record.output_tokens == 500

    def test_llm_trace_record_preserves_timestamp(self):
        """Test LLMTraceRecord preserves exact timestamp."""
        now = datetime.utcnow()
        record = LLMTraceRecord(
            timestamp=now,
            operation="entity_extraction",
            model="gpt-3.5-turbo",
            cost=0.001,
            input_tokens=50,
            output_tokens=20,
        )
        assert record.timestamp == now


class TestLLMTraceSummary:
    """Tests for LLMTraceSummary model."""

    def test_llm_trace_summary_defaults(self):
        """Test LLMTraceSummary defaults to zero cost and empty breakdown."""
        summary = LLMTraceSummary()
        assert summary.total_cost == 0.0
        assert summary.total_operations == 0
        assert summary.operation_breakdown == {}
        assert summary.recent_traces == []

    def test_llm_trace_summary_with_data(self):
        """Test LLMTraceSummary with populated fields."""
        now = datetime.utcnow()
        summary = LLMTraceSummary(
            total_cost=15.32,
            total_operations=284,
            operation_breakdown={
                "narrative_generation": 150,
                "entity_extraction": 134,
            },
            recent_traces=[
                LLMTraceRecord(
                    timestamp=now - timedelta(minutes=5),
                    operation="narrative_generation",
                    model="gpt-4",
                    cost=0.045,
                    input_tokens=150,
                    output_tokens=500,
                ),
                LLMTraceRecord(
                    timestamp=now - timedelta(minutes=3),
                    operation="entity_extraction",
                    model="gpt-3.5-turbo",
                    cost=0.001,
                    input_tokens=50,
                    output_tokens=20,
                ),
            ],
        )
        assert summary.total_cost == 15.32
        assert summary.total_operations == 284
        assert summary.operation_breakdown["narrative_generation"] == 150
        assert len(summary.recent_traces) == 2

    def test_llm_trace_summary_bug_064_reproduction(self):
        """Test LLMTraceSummary fields needed for BUG-064 reproduction."""
        now = datetime.utcnow()
        summary = LLMTraceSummary(
            total_cost=125.50,
            total_operations=500,
            operation_breakdown={
                "narrative_generation": 400,
                "entity_extraction": 100,
            },
            recent_traces=[
                LLMTraceRecord(
                    timestamp=now - timedelta(seconds=30),
                    operation="narrative_generation",
                    model="gpt-4",
                    cost=1.50,
                    input_tokens=200,
                    output_tokens=800,
                ),
            ],
        )
        assert hasattr(summary, "total_cost")
        assert summary.total_cost == 125.50
        assert "narrative_generation" in summary.operation_breakdown
        assert len(summary.recent_traces) > 0
        assert summary.recent_traces[0].operation == "narrative_generation"


class TestEvidenceReferenceAllocator:
    """Tests for EvidenceReferenceAllocator."""

    def test_allocator_initial_state(self):
        """Test allocator starts at 0."""
        allocator = EvidenceReferenceAllocator()
        assert allocator.current_count() == 0

    def test_allocator_next_ref_sequence(self):
        """Test next_ref returns E-001, E-002, ... sequentially."""
        allocator = EvidenceReferenceAllocator()
        assert allocator.next_ref() == "E-001"
        assert allocator.next_ref() == "E-002"
        assert allocator.next_ref() == "E-003"

    def test_allocator_count_tracking(self):
        """Test current_count tracks allocated refs."""
        allocator = EvidenceReferenceAllocator()
        allocator.next_ref()
        allocator.next_ref()
        allocator.next_ref()
        assert allocator.current_count() == 3

    def test_allocator_no_reuse(self):
        """Test allocator never reuses reference IDs."""
        allocator = EvidenceReferenceAllocator()
        refs = [allocator.next_ref() for _ in range(15)]
        assert len(refs) == len(set(refs))  # all unique
        assert refs[-1] == "E-015"

    def test_allocator_format(self):
        """Test reference IDs have correct format E-NNN."""
        allocator = EvidenceReferenceAllocator()
        for i in range(1, 101):
            ref = allocator.next_ref()
            assert ref == f"E-{i:03d}"


class TestEvidencePackCreate:
    """Tests for EvidencePackCreate model."""

    def test_evidence_pack_create_minimal(self):
        """Test EvidencePackCreate with only required fields."""
        pack = EvidencePackCreate(
            pack_id="ep_BUG-064_20260616T120000Z",
            bugcase_id="BUG-064",
        )
        assert pack.pack_id == "ep_BUG-064_20260616T120000Z"
        assert pack.bugcase_id == "BUG-064"
        assert pack.collection_status == EvidencePackStatus.PARTIAL
        assert pack.blast_radius == []
        assert pack.subsystem_metrics == []
        assert pack.system_state == {}
        assert pack.healthy_signals == []
        assert pack.related_cases == []
        assert pack.deploy_context == []
        assert pack.config_evidence == {}
        assert pack.log_excerpts == []
        assert pack.evidence_references == {}
        assert pack.sections_collected == []
        assert pack.sections_missing == []
        assert pack.collection_errors == []
        assert pack.redactions_applied == 0
        assert pack.truncation_applied == []
        assert pack.total_chars == 0

    def test_evidence_pack_create_auto_timestamps(self):
        """Test EvidencePackCreate auto-sets timestamps."""
        before = datetime.utcnow()
        pack = EvidencePackCreate(
            pack_id="ep_test",
            bugcase_id="BUG-001",
        )
        after = datetime.utcnow()
        assert before <= pack.collection_started_at <= after
        assert before <= pack.created_at <= after
        assert before <= pack.updated_at <= after

    def test_evidence_pack_create_complete_fields(self):
        """Test EvidencePackCreate with all fields populated."""
        now = datetime.utcnow()
        pack = EvidencePackCreate(
            pack_id="ep_BUG-064_20260616T120000Z",
            bugcase_id="BUG-064",
            collection_started_at=now,
            collection_completed_at=now + timedelta(minutes=2),
            collection_duration_ms=120000,
            collection_status=EvidencePackStatus.COMPLETE,
            incident_first_seen_at=now - timedelta(minutes=30),
            incident_last_seen_at=now,
            root_subsystem="worker",
            severity="critical",
            primary_signal="Memory utilization >90%",
            blast_radius=["worker", "scheduler"],
            subsystem_metrics=[
                SectionMetrics(subsystem="articles", artifact_count=1250)
            ],
            subsystem_metrics_collected_at=now,
            system_state={"mongodb": {"status": "ok", "latency_ms": 12}},
            system_state_collected_at=now,
            healthy_signals=["MongoDB reachable (12ms)"],
            related_cases=[
                {
                    "case_id": "BUG-063",
                    "root_subsystem": "worker",
                    "severity": "high",
                    "status": "resolved",
                    "first_seen_at": now - timedelta(hours=1),
                    "last_seen_at": now - timedelta(minutes=45),
                }
            ],
            related_cases_collected_at=now,
            deploy_context=[
                {
                    "service": "api",
                    "deployment_id": "deploy-2026-06-16-120000",
                    "status": "active",
                    "created_at": now - timedelta(days=1),
                    "updated_at": now - timedelta(hours=2),
                }
            ],
            deploy_context_collected_at=now,
            config_evidence={
                "llm_daily_soft_limit": 100.0,
                "llm_daily_hard_limit": 150.0,
                "critical_operations": ["narrative_generation", "entity_extraction"],
            },
            config_evidence_collected_at=now,
            llm_trace_summary=LLMTraceSummary(
                total_cost=15.32,
                total_operations=284,
                operation_breakdown={
                    "narrative_generation": 150,
                    "entity_extraction": 134,
                },
            ),
            llm_trace_summary_collected_at=now,
            log_excerpts=[
                LogExcerptSection(
                    service="fastapi",
                    lines_fetched=200,
                    lines_stored=200,
                    truncated=False,
                    window_start=now - timedelta(minutes=10),
                    window_end=now,
                    excerpts=["[ERROR] Memory exhausted"],
                )
            ],
            evidence_references={
                "E-001": {
                    "description": "Cost controls daily_soft_limit",
                    "section": "config_evidence",
                    "field": "llm_daily_soft_limit",
                },
                "E-002": {
                    "description": "Total LLM cost",
                    "section": "llm_trace_summary",
                    "field": "total_cost",
                },
            },
            sections_collected=["config_evidence", "llm_trace_summary"],
            sections_missing=[
                {
                    "section": "deploy_context",
                    "reason": "Railway API timeout",
                    "attempted_at": now,
                }
            ],
            redactions_applied=3,
            truncation_applied=["log_excerpts"],
            total_chars=45000,
        )
        assert pack.pack_id == "ep_BUG-064_20260616T120000Z"
        assert pack.collection_status == EvidencePackStatus.COMPLETE
        assert pack.root_subsystem == "worker"
        assert pack.severity == "critical"
        assert len(pack.blast_radius) == 2
        assert len(pack.subsystem_metrics) == 1
        assert len(pack.related_cases) == 1
        assert len(pack.evidence_references) == 2
        assert pack.redactions_applied == 3
        assert pack.total_chars == 45000

    def test_evidence_pack_create_validation_root_subsystem(self):
        """Test root_subsystem validation against BugOpsSubsystem enum."""
        with pytest.raises(ValueError, match="root_subsystem must be a valid"):
            EvidencePackCreate(
                pack_id="ep_test",
                bugcase_id="BUG-001",
                root_subsystem="invalid_subsystem",
            )

    def test_evidence_pack_create_validation_severity(self):
        """Test severity validation against AlertSeverity enum."""
        with pytest.raises(ValueError, match="severity must be a valid"):
            EvidencePackCreate(
                pack_id="ep_test",
                bugcase_id="BUG-001",
                severity="catastrophic",
            )

    def test_evidence_pack_create_validation_blast_radius(self):
        """Test blast_radius validation against BugOpsSubsystem enum."""
        with pytest.raises(ValueError, match="blast_radius contains invalid value"):
            EvidencePackCreate(
                pack_id="ep_test",
                bugcase_id="BUG-001",
                blast_radius=["worker", "invalid_subsystem"],
            )

    def test_evidence_pack_create_valid_root_subsystems(self):
        """Test all valid BugOpsSubsystem values work as root_subsystem."""
        for subsystem in BugOpsSubsystem:
            pack = EvidencePackCreate(
                pack_id=f"ep_test_{subsystem.value}",
                bugcase_id="BUG-001",
                root_subsystem=subsystem.value,
            )
            assert pack.root_subsystem == subsystem.value

    def test_evidence_pack_create_valid_severities(self):
        """Test all valid AlertSeverity values work as severity."""
        for severity in AlertSeverity:
            pack = EvidencePackCreate(
                pack_id=f"ep_test_{severity.value}",
                bugcase_id="BUG-001",
                severity=severity.value,
            )
            assert pack.severity == severity.value


class TestEvidencePack:
    """Tests for EvidencePack persisted model."""

    def test_evidence_pack_inherits_from_create(self):
        """Test EvidencePack inherits all EvidencePackCreate fields."""
        pack = EvidencePack(
            pack_id="ep_BUG-064",
            bugcase_id="BUG-064",
            collection_status=EvidencePackStatus.COMPLETE,
        )
        assert pack.pack_id == "ep_BUG-064"
        assert pack.bugcase_id == "BUG-064"
        assert pack.collection_status == EvidencePackStatus.COMPLETE

    def test_evidence_pack_id_field(self):
        """Test EvidencePack has id field with _id alias."""
        pack = EvidencePack(
            id="60d5ec49c1234567890abcde",
            pack_id="ep_BUG-064",
            bugcase_id="BUG-064",
        )
        assert pack.id == "60d5ec49c1234567890abcde"

    def test_evidence_pack_populate_by_name(self):
        """Test EvidencePack populate_by_name=True works."""
        pack = EvidencePack.model_validate(
            {
                "_id": "60d5ec49c1234567890abcde",
                "pack_id": "ep_BUG-064",
                "bugcase_id": "BUG-064",
            }
        )
        assert pack.id == "60d5ec49c1234567890abcde"

    def test_evidence_pack_mongo_dump_format(self):
        """Test EvidencePack model_dump with by_alias=True for MongoDB."""
        pack = EvidencePack(
            id="60d5ec49c1234567890abcde",
            pack_id="ep_BUG-064",
            bugcase_id="BUG-064",
        )
        dumped = pack.model_dump(by_alias=True)
        assert "_id" in dumped
        assert dumped["_id"] == "60d5ec49c1234567890abcde"
        assert dumped["pack_id"] == "ep_BUG-064"


class TestEvidencePackIntegration:
    """Integration tests for Evidence Pack models."""

    def test_evidence_pack_with_reference_allocator(self):
        """Test building an Evidence Pack with reference allocator."""
        allocator = EvidenceReferenceAllocator()
        now = datetime.utcnow()

        pack = EvidencePackCreate(
            pack_id="ep_BUG-064_20260616T120000Z",
            bugcase_id="BUG-064",
            collection_status=EvidencePackStatus.COMPLETE,
            config_evidence={
                "llm_daily_soft_limit": 100.0,
                "llm_daily_hard_limit": 150.0,
            },
            config_evidence_collected_at=now,
            llm_trace_summary=LLMTraceSummary(
                total_cost=15.32,
                total_operations=284,
                operation_breakdown={
                    "narrative_generation": 150,
                    "entity_extraction": 134,
                },
            ),
            llm_trace_summary_collected_at=now,
        )

        # Simulate allocator allocation during collection
        ref_id_1 = allocator.next_ref()
        ref_id_2 = allocator.next_ref()

        pack.evidence_references[ref_id_1] = {
            "description": "Cost controls daily_soft_limit",
            "section": "config_evidence",
            "field": "llm_daily_soft_limit",
        }
        pack.evidence_references[ref_id_2] = {
            "description": "Total LLM cost",
            "section": "llm_trace_summary",
            "field": "total_cost",
        }

        assert pack.evidence_references["E-001"]["section"] == "config_evidence"
        assert pack.evidence_references["E-002"]["section"] == "llm_trace_summary"
        assert allocator.current_count() == 2

    def test_evidence_pack_partial_with_missing_sections(self):
        """Test partial Evidence Pack with explicit missing section records."""
        now = datetime.utcnow()
        pack = EvidencePackCreate(
            pack_id="ep_BUG-064_partial",
            bugcase_id="BUG-064",
            collection_status=EvidencePackStatus.PARTIAL,
            config_evidence={
                "llm_daily_soft_limit": 100.0,
            },
            config_evidence_collected_at=now,
            sections_collected=["config_evidence"],
            sections_missing=[
                {
                    "section": "deploy_context",
                    "reason": "Railway API timeout after 30s",
                    "attempted_at": now,
                },
                {
                    "section": "llm_trace_summary",
                    "reason": "No llm_traces in MongoDB during window",
                    "attempted_at": now,
                },
            ],
        )
        assert pack.collection_status == EvidencePackStatus.PARTIAL
        assert len(pack.sections_collected) == 1
        assert len(pack.sections_missing) == 2
        assert pack.sections_missing[0]["section"] == "deploy_context"
        assert "timeout" in pack.sections_missing[0]["reason"]

    def test_evidence_pack_collection_errors_recorded(self):
        """Test Evidence Pack records collection errors explicitly."""
        now = datetime.utcnow()
        pack = EvidencePackCreate(
            pack_id="ep_BUG-064_errors",
            bugcase_id="BUG-064",
            collection_status=EvidencePackStatus.PARTIAL,
            collection_errors=[
                CollectionError(
                    source="railway_logs",
                    error_type="TimeoutError",
                    error_message="API timeout after 30s",
                    attempted_at=now,
                ),
                CollectionError(
                    source="deploy_context",
                    error_type="ConnectionError",
                    error_message="Connection refused",
                    attempted_at=now,
                ),
            ],
        )
        assert len(pack.collection_errors) == 2
        assert pack.collection_errors[0].source == "railway_logs"
        assert pack.collection_errors[1].error_type == "ConnectionError"
