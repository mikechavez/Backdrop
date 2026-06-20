"""Tests for LogCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.evidence.collectors.logs import LogCollector
from crypto_news_aggregator.bugops.evidence.redaction import LogRedactor
from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, EvidenceReferenceAllocator


@pytest.fixture
def mock_railway_client():
    """Provide a mock RailwayClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_redactor():
    """Provide a mock LogRedactor."""
    redactor = MagicMock()
    return redactor


@pytest.fixture
def real_redactor():
    """Provide a real LogRedactor for integration tests."""
    return LogRedactor()


@pytest.fixture
def mock_settings():
    """Provide mock settings."""
    settings = MagicMock()
    settings.BUGOPS_LOG_WINDOW_MINUTES = 10
    settings.BUGOPS_LOG_LINE_CAP = 200
    return settings


@pytest.fixture
def mock_store():
    """Provide a mock BugOpsStore."""
    store = AsyncMock()
    return store


@pytest.fixture
def bugcase():
    """Provide a sample BugCase."""
    first_seen = datetime(2026, 6, 20, 12, 0, 0)
    last_seen = datetime(2026, 6, 20, 12, 15, 0)
    return BugCase(
        case_id="BUG-001",
        status="open",
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Test case",
        summary="Test summary",
        dedupe_key="test",
        source_types=["test"],
        created_at=first_seen,
        updated_at=last_seen,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
    )


@pytest.fixture
def ref_allocator():
    """Provide a reference allocator."""
    return EvidenceReferenceAllocator()


class TestLogCollectorBasics:
    """Basic LogCollector tests."""

    def test_collector_name(self, mock_railway_client, mock_redactor, mock_settings):
        """LogCollector has correct collector_name."""
        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )
        assert collector.collector_name == "logs"

    def test_initialization(self, mock_railway_client, mock_redactor, mock_settings):
        """LogCollector initializes with dependencies."""
        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )
        assert collector.railway is mock_railway_client
        assert collector.redactor is mock_redactor
        assert collector.settings is mock_settings


class TestLogCollectorCollection:
    """Tests for log collection behavior."""

    @pytest.mark.asyncio
    async def test_fetches_logs_for_all_services(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Fetches logs for all three services."""
        # Setup
        mock_railway_client.get_logs.return_value = (["log line 1"], False)
        mock_redactor.redact_lines.return_value = (["log line 1"], 0)

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        # Execute
        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Verify all services queried
        assert mock_railway_client.get_logs.call_count == 3
        calls = mock_railway_client.get_logs.call_args_list
        service_names = [call.kwargs["service_name"] for call in calls]
        assert "fastapi" in service_names
        assert "celery_worker" in service_names
        assert "celery_scheduler" in service_names

    @pytest.mark.asyncio
    async def test_window_calculation(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Window is first_seen_at - minutes to last_seen_at + minutes."""
        mock_railway_client.get_logs.return_value = ([], False)
        mock_redactor.redact_lines.return_value = ([], 0)

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Check window calculation
        calls = mock_railway_client.get_logs.call_args_list
        call = calls[0]
        start = call.kwargs["start_time"]
        end = call.kwargs["end_time"]

        expected_start = bugcase.first_seen_at - timedelta(minutes=10)
        expected_end = bugcase.last_seen_at + timedelta(minutes=10)

        assert start == expected_start
        assert end == expected_end

    @pytest.mark.asyncio
    async def test_uses_line_cap_from_settings(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Uses BUGOPS_LOG_LINE_CAP from settings."""
        mock_railway_client.get_logs.return_value = ([], False)
        mock_redactor.redact_lines.return_value = ([], 0)
        mock_settings.BUGOPS_LOG_LINE_CAP = 500

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Check line_cap passed to get_logs
        calls = mock_railway_client.get_logs.call_args_list
        for call in calls:
            assert call.kwargs["line_cap"] == 500

    @pytest.mark.asyncio
    async def test_redacts_all_lines_before_storage(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Redacts all lines before calling store.update_evidence_pack_section()."""
        raw_lines = ["line 1 with secret=value", "line 2"]
        redacted_lines = ["line 1 with secret=[REDACTED:SECRET]", "line 2"]

        mock_railway_client.get_logs.return_value = (raw_lines, False)
        mock_redactor.redact_lines.return_value = (redacted_lines, 1)

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Verify redaction was called
        assert mock_redactor.redact_lines.called
        # Check that store received redacted lines, not raw lines
        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]
        assert section_data["log_excerpts"][0]["excerpts"] == redacted_lines

    @pytest.mark.asyncio
    async def test_truncation_metadata_per_service(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Truncation metadata recorded per service."""
        mock_railway_client.get_logs.side_effect = [
            (["log1", "log2"], False),  # fastapi not truncated
            (["log3", "log4"], True),   # celery_worker truncated
            ([], False),                # celery_scheduler no logs
        ]
        mock_redactor.redact_lines.side_effect = [
            (["log1", "log2"], 0),
            (["log3", "log4"], 0),
            ([], 0),
        ]

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Check section data
        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]
        log_sections = section_data["log_excerpts"]

        assert log_sections[0]["service"] == "fastapi"
        assert log_sections[0]["truncated"] is False
        assert log_sections[0]["lines_fetched"] == 2
        assert log_sections[0]["lines_stored"] == 2

        assert log_sections[1]["service"] == "celery_worker"
        assert log_sections[1]["truncated"] is True
        assert log_sections[1]["lines_fetched"] == 2
        assert log_sections[1]["lines_stored"] == 2

    @pytest.mark.asyncio
    async def test_redactions_applied_count(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """redactions_applied count is sum across all services."""
        mock_railway_client.get_logs.side_effect = [
            (["line1", "line2"], False),
            (["line3"], False),
            ([], False),
        ]
        mock_redactor.redact_lines.side_effect = [
            (["line1", "line2"], 1),  # 1 redaction in fastapi
            (["line3"], 2),            # 2 redactions in celery_worker
            ([], 0),                   # 0 redactions in celery_scheduler
        ]

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]
        assert section_data["redactions_applied"] == 3  # 1 + 2 + 0


class TestLogCollectorErrorHandling:
    """Tests for error handling and resilience."""

    @pytest.mark.asyncio
    async def test_railway_error_one_service(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Railway unavailable for one service — recorded in sections_missing."""
        mock_railway_client.get_logs.side_effect = [
            (["log1"], False),  # fastapi OK
            RuntimeError("Railway API timeout"),  # celery_worker fails
            (["log3"], False),  # celery_scheduler OK
        ]
        mock_redactor.redact_lines.side_effect = [
            (["log1"], 0),
            (["log3"], 0),
        ]

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Should continue to other services and record error
        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        # Two services succeeded
        assert len(section_data["log_excerpts"]) == 2
        # One service in missing sections
        assert len(section_data["sections_missing"]) == 1
        assert section_data["sections_missing"][0]["section"] == "logs.celery_worker"
        assert "RuntimeError" in section_data["sections_missing"][0]["reason"]

    @pytest.mark.asyncio
    async def test_railway_error_all_services(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Railway unavailable for all services — all in sections_missing."""
        mock_railway_client.get_logs.side_effect = [
            RuntimeError("API timeout"),
            RuntimeError("API timeout"),
            RuntimeError("API timeout"),
        ]

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        # No log sections collected
        assert section_data["log_excerpts"] == []
        # All three services in missing sections
        assert len(section_data["sections_missing"]) == 3
        services_missing = [s["section"] for s in section_data["sections_missing"]]
        assert "logs.fastapi" in services_missing
        assert "logs.celery_worker" in services_missing
        assert "logs.celery_scheduler" in services_missing

    @pytest.mark.asyncio
    async def test_does_not_raise_on_error(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """LogCollector does not raise exceptions on Railway errors."""
        mock_railway_client.get_logs.side_effect = RuntimeError("API error")

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        # Should not raise
        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Should still update store
        assert mock_store.update_evidence_pack_section.called


class TestLogCollectorEvidenceReferences:
    """Tests for evidence reference generation."""

    @pytest.mark.asyncio
    async def test_adds_evidence_reference_when_logs_present(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Adds evidence reference describing total lines and truncated services."""
        mock_railway_client.get_logs.side_effect = [
            (["log1", "log2"], False),
            (["log3"], True),  # truncated
            ([], False),
        ]
        mock_redactor.redact_lines.side_effect = [
            (["log1", "log2"], 0),
            (["log3"], 0),
            ([], 0),
        ]

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        # Check evidence references
        refs = section_data["evidence_references"]
        assert len(refs) > 0
        # First ref should be the logs reference
        first_ref_id = list(refs.keys())[0]
        ref = refs[first_ref_id]
        assert "Log excerpts" in ref["description"]
        assert "3 lines" in ref["description"]  # 2 + 1 + 0
        assert "3 services" in ref["description"]
        assert "truncated: celery_worker" in ref["description"]

    @pytest.mark.asyncio
    async def test_reference_when_log_sections_exist(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Evidence reference added when log_sections contain at least one service."""
        mock_railway_client.get_logs.return_value = ([], False)
        mock_redactor.redact_lines.return_value = ([], 0)

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        # log_excerpts has all 3 services even if empty
        assert len(section_data["log_excerpts"]) == 3
        # Evidence reference is added even for empty services
        assert "evidence_references" in section_data
        refs = section_data["evidence_references"]
        assert len(refs) > 0

    @pytest.mark.asyncio
    async def test_uses_ref_allocator(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        bugcase
    ):
        """Uses ref_allocator.next_ref() — does not hardcode reference IDs."""
        mock_railway_client.get_logs.return_value = (["log1"], False)
        mock_redactor.redact_lines.return_value = (["log1"], 0)

        ref_allocator = EvidenceReferenceAllocator()
        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        refs = section_data.get("evidence_references", {})
        assert len(refs) > 0
        # Reference ID should be from allocator (E-001, E-002, etc.)
        ref_ids = list(refs.keys())
        for ref_id in ref_ids:
            assert ref_id.startswith("E-")


class TestLogCollectorNoneSafety:
    """Tests for None value handling."""

    @pytest.mark.asyncio
    async def test_handles_none_first_seen_at(
        self, mock_railway_client, mock_redactor, mock_settings, mock_store,
        ref_allocator
    ):
        """Safely skips collection when first_seen_at is None."""
        bugcase = BugCase(
            case_id="BUG-001",
            status="open",
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Test case",
            summary="Test summary",
            dedupe_key="test",
            source_types=["test"],
            created_at=datetime(2026, 6, 20, 12, 0, 0),
            updated_at=datetime(2026, 6, 20, 12, 0, 0),
            first_seen_at=None,  # No first_seen_at
            last_seen_at=datetime(2026, 6, 20, 12, 15, 0),
        )

        collector = LogCollector(
            mock_railway_client, mock_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        # Verify Railway client was never called
        assert not mock_railway_client.get_logs.called

        # Verify store was updated with empty logs and error
        assert mock_store.update_evidence_pack_section.called
        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        assert section_data["log_excerpts"] == []
        assert section_data["redactions_applied"] == 0
        assert len(section_data["sections_missing"]) == 1
        assert "first_seen_at" in section_data["sections_missing"][0]["reason"]


class TestLogCollectorIntegration:
    """Integration tests with real LogRedactor."""

    @pytest.mark.asyncio
    async def test_full_collection_with_real_redactor(
        self, mock_railway_client, real_redactor, mock_settings, mock_store,
        bugcase, ref_allocator
    ):
        """Full collection flow with real redaction."""
        raw_logs = [
            "2026-06-20T12:05:00Z INFO Starting service",
            "api_key=sk_test_12345678 authenticated",
            "user@example.com connected",
            "2026-06-20T12:10:00Z INFO Service operational",
        ]
        mock_railway_client.get_logs.side_effect = [
            (raw_logs, False),
            ([], False),
            ([], False),
        ]

        collector = LogCollector(
            mock_railway_client, real_redactor, mock_settings
        )

        await collector.collect(bugcase, "pack-001", mock_store, ref_allocator)

        call = mock_store.update_evidence_pack_section.call_args_list[0]
        section_data = call[0][1]

        # Verify real redaction happened
        stored_logs = section_data["log_excerpts"][0]["excerpts"]
        assert len(stored_logs) == 4
        assert "api_key=[REDACTED:SECRET]" in stored_logs[1]
        assert "[REDACTED:EMAIL]" in stored_logs[2]
        assert "2026-06-20T12:05:00Z INFO Starting service" == stored_logs[0]
        assert "2026-06-20T12:10:00Z INFO Service operational" == stored_logs[3]

        # Verify redactions counted
        assert section_data["redactions_applied"] == 2
