"""Tests for MetricsCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.evidence.collectors.metrics import MetricsCollector
from crypto_news_aggregator.bugops.models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    BugOpsSubsystem,
    EvidenceReferenceAllocator,
    SectionMetrics,
)


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()

    # Mock mongo_manager with async database
    mock_db = AsyncMock()
    store.mongo_manager = MagicMock()
    store.mongo_manager.get_async_database = AsyncMock(return_value=mock_db)

    return store


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES = 60
    return settings


@pytest.fixture
def bugcase_with_blast_radius():
    """Create a BugCase with blast_radius."""
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
        blast_radius=[BugOpsSubsystem.SIGNALS.value, BugOpsSubsystem.NARRATIVES.value],
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
        last_seen_at=datetime.utcnow(),
    )


@pytest.fixture
def bugcase_with_no_blast_radius():
    """Create a BugCase with no blast_radius."""
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
        first_seen_at=datetime.utcnow() - timedelta(minutes=15),
        last_seen_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_metrics_collector_with_recent_artifacts(mock_store, mock_settings, bugcase_with_blast_radius):
    """Test MetricsCollector with recent artifacts within freshness window."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()

        # Mock collection responses
        async def mock_find_one(sort=None, projection=None):
            return {"created_at": datetime.utcnow() - timedelta(minutes=30)}

        async def mock_count_documents(query):
            return 5

        # Create mock collections for each subsystem
        articles_collection = AsyncMock()
        articles_collection.find_one = mock_find_one
        articles_collection.count_documents = mock_count_documents

        signals_collection = AsyncMock()
        signals_collection.find_one = mock_find_one
        signals_collection.count_documents = mock_count_documents

        narratives_collection = AsyncMock()
        narratives_collection.find_one = mock_find_one
        narratives_collection.count_documents = mock_count_documents

        # Setup mock_db to return collections
        collections_dict = {
            "articles": articles_collection,
            "signals": signals_collection,
            "narratives": narratives_collection,
        }
        mock_db.__getitem__.side_effect = lambda name: collections_dict.get(name)

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        await collector.collect(bugcase_with_blast_radius, "pack_1", mock_store, ref_allocator)

        # Verify store was called with correct data
        assert mock_store.update_evidence_pack_section.called
        call_args = mock_store.update_evidence_pack_section.call_args
        assert call_args[0][0] == "pack_1"

        update_data = call_args[0][1]
        assert "subsystem_metrics" in update_data
        assert "subsystem_metrics_collected_at" in update_data
        assert "evidence_references" in update_data

        # Verify metrics were collected for the right subsystems
        metrics = update_data["subsystem_metrics"]
        subsystem_names = [m["subsystem"] for m in metrics]
        assert BugOpsSubsystem.ARTICLES.value in subsystem_names
        assert BugOpsSubsystem.SIGNALS.value in subsystem_names
        assert BugOpsSubsystem.NARRATIVES.value in subsystem_names

        # Check that one metric has "within window" indicator
        within_window = [m for m in metrics if m["freshness_indicator"] == "within window"]
        assert len(within_window) > 0


@pytest.mark.asyncio
async def test_metrics_collector_with_stale_artifacts(mock_store, mock_settings, bugcase_with_blast_radius):
    """Test MetricsCollector with stale artifacts outside freshness window."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()

        # Return stale artifact
        async def mock_find_one_stale(sort=None, projection=None):
            return {"created_at": datetime.utcnow() - timedelta(hours=3)}

        async def mock_count_documents(query):
            return 0  # No recent artifacts

        articles_collection = AsyncMock()
        articles_collection.find_one = mock_find_one_stale
        articles_collection.count_documents = mock_count_documents

        signals_collection = AsyncMock()
        signals_collection.find_one = mock_find_one_stale
        signals_collection.count_documents = mock_count_documents

        narratives_collection = AsyncMock()
        narratives_collection.find_one = mock_find_one_stale
        narratives_collection.count_documents = mock_count_documents

        collections_dict = {
            "articles": articles_collection,
            "signals": signals_collection,
            "narratives": narratives_collection,
        }
        mock_db.__getitem__.side_effect = lambda name: collections_dict.get(name)

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        await collector.collect(bugcase_with_blast_radius, "pack_1", mock_store, ref_allocator)

        # Verify metrics were collected with stale indicators
        call_args = mock_store.update_evidence_pack_section.call_args
        update_data = call_args[0][1]
        metrics = update_data["subsystem_metrics"]

        # Check that metrics have elapsed time indicators (not "within window")
        for metric in metrics:
            assert "ago" in metric["freshness_indicator"] or "no artifacts" in metric["freshness_indicator"]


@pytest.mark.asyncio
async def test_metrics_collector_with_no_artifacts(mock_store, mock_settings, bugcase_with_blast_radius):
    """Test MetricsCollector when subsystem has no artifacts."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()

        # Return None for no artifacts
        async def mock_find_one_empty(sort=None, projection=None):
            return None

        async def mock_count_documents(query):
            return 0

        articles_collection = AsyncMock()
        articles_collection.find_one = mock_find_one_empty
        articles_collection.count_documents = mock_count_documents

        signals_collection = AsyncMock()
        signals_collection.find_one = mock_find_one_empty
        signals_collection.count_documents = mock_count_documents

        narratives_collection = AsyncMock()
        narratives_collection.find_one = mock_find_one_empty
        narratives_collection.count_documents = mock_count_documents

        collections_dict = {
            "articles": articles_collection,
            "signals": signals_collection,
            "narratives": narratives_collection,
        }
        mock_db.__getitem__.side_effect = lambda name: collections_dict.get(name)

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        await collector.collect(bugcase_with_blast_radius, "pack_1", mock_store, ref_allocator)

        # Verify metrics were collected
        call_args = mock_store.update_evidence_pack_section.call_args
        update_data = call_args[0][1]
        metrics = update_data["subsystem_metrics"]

        # Check that metrics have "no artifacts found" indicator
        for metric in metrics:
            assert metric["freshness_indicator"] == "no artifacts found"
            assert metric["last_artifact_at"] is None


@pytest.mark.asyncio
async def test_metrics_collector_skips_non_mongodb_subsystems(mock_store, mock_settings, bugcase_with_blast_radius):
    """Test MetricsCollector skips subsystems without MongoDB collections."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        # Create a BugCase with non-MongoDB subsystems
        bugcase = BugCase(
            case_id="case_3",
            status=CaseStatus.OPEN,
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Test Case 3",
            summary="Test Summary 3",
            dedupe_key="test_3",
            source_types=["test"],
            root_subsystem=BugOpsSubsystem.SCHEDULER.value,  # No MongoDB collection
            blast_radius=[BugOpsSubsystem.WORKER.value, BugOpsSubsystem.DATABASE.value],  # No collections
            first_seen_at=datetime.utcnow() - timedelta(minutes=15),
            last_seen_at=datetime.utcnow(),
        )

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()
        mock_db.__getitem__ = AsyncMock()

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        await collector.collect(bugcase, "pack_1", mock_store, ref_allocator)

        # Verify store was called
        assert mock_store.update_evidence_pack_section.called

        call_args = mock_store.update_evidence_pack_section.call_args
        update_data = call_args[0][1]
        metrics = update_data["subsystem_metrics"]

        # Should have no metrics since no subsystems have MongoDB collections
        assert len(metrics) == 0


@pytest.mark.asyncio
async def test_metrics_collector_uses_ref_allocator(mock_store, mock_settings, bugcase_with_blast_radius):
    """Test MetricsCollector uses ref_allocator for evidence references."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()

        async def mock_find_one(sort=None, projection=None):
            return {"created_at": datetime.utcnow() - timedelta(minutes=30)}

        async def mock_count_documents(query):
            return 1

        articles_collection = AsyncMock()
        articles_collection.find_one = mock_find_one
        articles_collection.count_documents = mock_count_documents

        signals_collection = AsyncMock()
        signals_collection.find_one = mock_find_one
        signals_collection.count_documents = mock_count_documents

        narratives_collection = AsyncMock()
        narratives_collection.find_one = mock_find_one
        narratives_collection.count_documents = mock_count_documents

        collections_dict = {
            "articles": articles_collection,
            "signals": signals_collection,
            "narratives": narratives_collection,
        }
        mock_db.__getitem__.side_effect = lambda name: collections_dict.get(name)

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        initial_count = ref_allocator.current_count()
        await collector.collect(bugcase_with_blast_radius, "pack_1", mock_store, ref_allocator)

        # Verify allocator was used
        final_count = ref_allocator.current_count()
        assert final_count > initial_count

        # Verify evidence references follow the pattern E-001, E-002, etc.
        call_args = mock_store.update_evidence_pack_section.call_args
        update_data = call_args[0][1]
        evidence_references = update_data["evidence_references"]

        for ref_id in evidence_references.keys():
            assert ref_id.startswith("E-")
            assert ref_id[2:].isdigit()


@pytest.mark.asyncio
async def test_metrics_collector_with_only_root_subsystem(mock_store, mock_settings, bugcase_with_no_blast_radius):
    """Test MetricsCollector with only root_subsystem and no blast_radius."""
    with patch("crypto_news_aggregator.bugops.evidence.collectors.metrics.get_settings") as mock_get_settings:
        mock_get_settings.return_value = mock_settings

        collector = MetricsCollector()

        # Setup mock database responses
        mock_db = await mock_store.mongo_manager.get_async_database()

        async def mock_find_one(sort=None, projection=None):
            return {"generated_at": datetime.utcnow() - timedelta(minutes=45)}

        async def mock_count_documents(query):
            return 3

        briefings_collection = AsyncMock()
        briefings_collection.find_one = mock_find_one
        briefings_collection.count_documents = mock_count_documents

        collections_dict = {
            "briefings": briefings_collection,
        }
        mock_db.__getitem__.side_effect = lambda name: collections_dict.get(name)

        # Run collector
        ref_allocator = EvidenceReferenceAllocator()
        await collector.collect(bugcase_with_no_blast_radius, "pack_1", mock_store, ref_allocator)

        # Verify only briefings metrics collected
        call_args = mock_store.update_evidence_pack_section.call_args
        update_data = call_args[0][1]
        metrics = update_data["subsystem_metrics"]

        assert len(metrics) == 1
        assert metrics[0]["subsystem"] == BugOpsSubsystem.BRIEFINGS.value
        assert metrics[0]["artifact_count"] == 3
