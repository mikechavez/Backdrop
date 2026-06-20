"""Tests for SystemStateCollector."""

import pytest
import httpx
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.evidence.collectors.system_state import SystemStateCollector
from crypto_news_aggregator.bugops.models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    BugOpsSubsystem,
    EvidenceReferenceAllocator,
)


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    return store


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.BUGOPS_HEALTH_ENDPOINT_URL = "http://localhost:8000"
    return settings


@pytest.fixture
def bugcase():
    """Create a test BugCase."""
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
    )


@pytest.fixture
def healthy_health_response():
    """Create a healthy health endpoint response."""
    return {
        "status": "healthy",
        "timestamp": "2026-06-19T12:00:00Z",
        "checks": {
            "database": {"status": "ok", "latency_ms": 12},
            "redis": {"status": "ok", "latency_ms": 4},
            "llm": {"status": "ok", "model": "claude-haiku"},
            "data_freshness": {"status": "ok", "latest_article_age_hours": 2.5},
            "pipeline": {
                "fetch_news": {"status": "ok", "last_success": "2026-06-19T11:55:00Z"},
                "generate_briefing": {"status": "ok", "last_success": "2026-06-19T11:50:00Z"},
            },
        },
    }


@pytest.mark.asyncio
async def test_system_state_collector_healthy_system(mock_store, mock_settings, bugcase, healthy_health_response):
    """Test SystemStateCollector with a healthy system."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        # Mock httpx.AsyncClient
        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = healthy_health_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            assert mock_store.update_evidence_pack_section.called

            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify system_state is populated
            assert "system_state" in update_data
            assert "system_state_collected_at" in update_data
            assert "healthy_signals" in update_data
            assert "evidence_references" in update_data
            assert "sections_missing" in update_data

            # Verify healthy signals were added
            healthy_signals = update_data["healthy_signals"]
            assert len(healthy_signals) > 0
            assert any("MongoDB" in signal for signal in healthy_signals)
            assert any("Redis" in signal for signal in healthy_signals)
            assert any("LLM" in signal for signal in healthy_signals)
            assert any("fetch" in signal or "RSS" in signal for signal in healthy_signals)
            assert any("Briefing" in signal for signal in healthy_signals)


@pytest.mark.asyncio
async def test_system_state_collector_no_healthy_signals(mock_store, mock_settings, bugcase):
    """Test SystemStateCollector when no checks are healthy."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        unhealthy_response = {
            "status": "unhealthy",
            "timestamp": "2026-06-19T12:00:00Z",
            "checks": {
                "database": {"status": "error", "latency_ms": 5000, "error": "Connection timeout"},
                "redis": {"status": "error", "latency_ms": 3000, "error": "Connection refused"},
                "llm": {"status": "degraded", "reason": "spend_cap"},
                "pipeline": {
                    "fetch_news": {"status": "critical", "last_success": "2026-06-15T00:00:00Z"},
                    "generate_briefing": {"status": "critical", "last_success": "2026-06-15T00:00:00Z"},
                },
            },
        }

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = unhealthy_response
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify healthy signals list is empty (no healthy checks)
            healthy_signals = update_data["healthy_signals"]
            assert len(healthy_signals) == 0


@pytest.mark.asyncio
async def test_system_state_collector_partial_health(mock_store, mock_settings, bugcase):
    """Test SystemStateCollector with some healthy and some unhealthy checks."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        partial_response = {
            "status": "degraded",
            "timestamp": "2026-06-19T12:00:00Z",
            "checks": {
                "database": {"status": "ok", "latency_ms": 15},
                "redis": {"status": "error", "latency_ms": 5000},
                "llm": {"status": "ok", "model": "claude-haiku"},
                "pipeline": {
                    "fetch_news": {"status": "ok", "last_success": "2026-06-19T11:55:00Z"},
                    "generate_briefing": {"status": "critical", "last_success": "2026-06-15T00:00:00Z"},
                },
            },
        }

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = partial_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify healthy signals include only the healthy checks
            healthy_signals = update_data["healthy_signals"]
            assert len(healthy_signals) == 3  # Database, LLM, fetch_news
            assert any("MongoDB" in signal for signal in healthy_signals)
            assert any("LLM" in signal for signal in healthy_signals)
            assert any("fetch" in signal or "RSS" in signal for signal in healthy_signals)


@pytest.mark.asyncio
async def test_system_state_collector_timeout(mock_store, mock_settings, bugcase):
    """Test SystemStateCollector handles health endpoint timeout."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify timeout is recorded in sections_missing
            sections_missing = update_data["sections_missing"]
            assert any("timeout" in entry["reason"].lower() for entry in sections_missing)


@pytest.mark.asyncio
async def test_system_state_collector_http_error(mock_store, mock_settings, bugcase):
    """Test SystemStateCollector handles HTTP errors."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Server error", request=None, response=mock_response)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify HTTP error is recorded
            sections_missing = update_data["sections_missing"]
            assert any("500" in entry["reason"] for entry in sections_missing)


@pytest.mark.asyncio
async def test_system_state_collector_celery_always_missing(mock_store, mock_settings, bugcase, healthy_health_response):
    """Test SystemStateCollector always records Celery worker/scheduler as sections_missing."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = healthy_health_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify Celery entries are in sections_missing
            sections_missing = update_data["sections_missing"]
            assert any("celery_worker" in entry["section"] for entry in sections_missing)
            assert any("celery_scheduler" in entry["section"] for entry in sections_missing)

            # Verify they mention TASK-119
            celery_entries = [e for e in sections_missing if "celery" in e["section"]]
            assert all("TASK-119" in entry["reason"] for entry in celery_entries)


@pytest.mark.asyncio
async def test_system_state_collector_uses_ref_allocator(mock_store, mock_settings, bugcase, healthy_health_response):
    """Test SystemStateCollector uses ref_allocator for evidence references."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = healthy_health_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            initial_count = ref_allocator.current_count()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify allocator was used
            final_count = ref_allocator.current_count()
            assert final_count > initial_count

            # Verify evidence reference follows pattern
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]
            evidence_references = update_data["evidence_references"]

            for ref_id in evidence_references.keys():
                assert ref_id.startswith("E-")
                assert ref_id[2:].isdigit()


@pytest.mark.asyncio
async def test_system_state_collector_latency_included(mock_store, mock_settings, bugcase, healthy_health_response):
    """Test SystemStateCollector includes latency in healthy signals."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = SystemStateCollector()

        with patch("crypto_news_aggregator.bugops.evidence.collectors.system_state.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = healthy_health_response
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Run collector
            ref_allocator = EvidenceReferenceAllocator()
            await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

            # Verify store was called
            call_args = mock_store.update_evidence_pack_section.call_args
            update_data = call_args[0][1]

            # Verify healthy signals include latency
            healthy_signals = update_data["healthy_signals"]
            mongo_signal = [s for s in healthy_signals if "MongoDB" in s][0]
            assert "(12ms)" in mongo_signal

            redis_signal = [s for s in healthy_signals if "Redis" in s][0]
            assert "(4ms)" in redis_signal
