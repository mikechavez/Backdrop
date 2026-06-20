"""Tests for DeployContextCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from crypto_news_aggregator.bugops.evidence.collectors.deploy_context import DeployContextCollector
from crypto_news_aggregator.bugops.models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    EvidenceReferenceAllocator,
)


@pytest.fixture
def mock_railway_client():
    """Create a mock RailwayClient."""
    client = AsyncMock()
    client.get_recent_deployments = AsyncMock()
    return client


@pytest.fixture
def mock_store():
    """Create a mock BugOpsStore."""
    store = AsyncMock()
    store.update_evidence_pack_section = AsyncMock()
    return store


@pytest.fixture
def bugcase():
    """Create a BugCase for testing."""
    from crypto_news_aggregator.bugops.models import BugOpsSubsystem

    return BugCase(
        case_id="case_123",
        status=CaseStatus.OPEN,
        severity=AlertSeverity.HIGH,
        alert_type="test",
        title="Deploy Issue",
        summary="Issue summary",
        dedupe_key="test_deploy",
        source_types=["test"],
        root_subsystem=BugOpsSubsystem.ARTICLES,
        blast_radius=[BugOpsSubsystem.WORKER],
        affected_subsystems=[],
        first_seen_at=datetime.utcnow() - timedelta(hours=2),
        last_seen_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_collector_with_deployments_all_services(mock_railway_client, mock_store, bugcase):
    """Test DeployContextCollector with deployments from all services."""
    fastapi_deployments = [
        {
            "deployment_id": "deploy_fastapi_1",
            "status": "SUCCESS",
            "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "updated_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }
    ]
    celery_worker_deployments = [
        {
            "deployment_id": "deploy_worker_1",
            "status": "SUCCESS",
            "created_at": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
            "updated_at": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
        }
    ]
    celery_scheduler_deployments = []

    # Mock get_recent_deployments to return different results per service
    async def mock_get_recent_deployments(service_name, since):
        if service_name == "fastapi":
            return fastapi_deployments
        elif service_name == "celery_worker":
            return celery_worker_deployments
        else:
            return celery_scheduler_deployments

    mock_railway_client.get_recent_deployments.side_effect = mock_get_recent_deployments

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    # Verify get_recent_deployments was called for all three services
    assert mock_railway_client.get_recent_deployments.call_count == 3
    calls = [call[1] for call in mock_railway_client.get_recent_deployments.call_args_list]
    service_names = [call["service_name"] for call in calls]
    assert set(service_names) == {"fastapi", "celery_worker", "celery_scheduler"}

    # Verify window_start is correct (24 hours before first_seen_at)
    for call in calls:
        assert call["since"] == bugcase.first_seen_at - timedelta(hours=24)

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify deployments collected
    assert "deploy_context" in section_data
    deployments = section_data["deploy_context"]
    assert len(deployments) == 2
    # Should be sorted by created_at descending (fastapi first since it's more recent)
    assert deployments[0]["service"] == "fastapi"
    assert deployments[1]["service"] == "celery_worker"

    # Verify timestamp
    assert "deploy_context_collected_at" in section_data
    assert isinstance(section_data["deploy_context_collected_at"], datetime)

    # Verify evidence reference
    assert "evidence_references" in section_data
    refs = section_data["evidence_references"]
    assert len(refs) == 1
    ref_id = list(refs.keys())[0]
    assert "2 deployments" in refs[ref_id]["description"]
    assert refs[ref_id]["section"] == "deploy_context"

    # Verify no sections_missing when all succeed
    assert "sections_missing" not in section_data


@pytest.mark.asyncio
async def test_collector_with_no_deployments(mock_railway_client, mock_store, bugcase):
    """Test DeployContextCollector when no deployments found."""
    mock_railway_client.get_recent_deployments.return_value = []

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify empty deployments list
    assert "deploy_context" in section_data
    assert section_data["deploy_context"] == []

    # Verify timestamp is written
    assert "deploy_context_collected_at" in section_data

    # Verify evidence reference states "No deployments"
    assert "evidence_references" in section_data
    refs = section_data["evidence_references"]
    ref_id = list(refs.keys())[0]
    assert "No deployments" in refs[ref_id]["description"]


@pytest.mark.asyncio
async def test_collector_with_single_service_failure(mock_railway_client, mock_store, bugcase):
    """Test DeployContextCollector when one service fails."""
    fastapi_deployments = [
        {
            "deployment_id": "deploy_fastapi_1",
            "status": "SUCCESS",
            "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "updated_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }
    ]

    async def mock_get_recent_deployments(service_name, since):
        if service_name == "fastapi":
            return fastapi_deployments
        elif service_name == "celery_worker":
            raise Exception("API timeout")
        else:
            return []

    mock_railway_client.get_recent_deployments.side_effect = mock_get_recent_deployments

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify deployments from successful services
    assert "deploy_context" in section_data
    assert len(section_data["deploy_context"]) == 1
    assert section_data["deploy_context"][0]["service"] == "fastapi"

    # Verify sections_missing records the failure
    assert "sections_missing" in section_data
    missing = section_data["sections_missing"]
    assert len(missing) == 1
    assert "celery_worker" in missing[0]["section"]
    assert "API timeout" in missing[0]["reason"]


@pytest.mark.asyncio
async def test_collector_with_all_services_unavailable(mock_railway_client, mock_store, bugcase):
    """Test DeployContextCollector when all services fail."""
    async def mock_get_recent_deployments(service_name, since):
        raise Exception("Railway API unavailable")

    mock_railway_client.get_recent_deployments.side_effect = mock_get_recent_deployments

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    # Verify update was called
    mock_store.update_evidence_pack_section.assert_called_once()
    section_data = mock_store.update_evidence_pack_section.call_args[0][1]

    # Verify empty deployments list
    assert "deploy_context" in section_data
    assert section_data["deploy_context"] == []

    # Verify sections_missing records all three failures
    assert "sections_missing" in section_data
    missing = section_data["sections_missing"]
    assert len(missing) == 3
    missing_services = {m["section"] for m in missing}
    assert missing_services == {
        "deploy_context.fastapi",
        "deploy_context.celery_worker",
        "deploy_context.celery_scheduler",
    }


@pytest.mark.asyncio
async def test_collector_deployments_sorted_descending(mock_railway_client, mock_store, bugcase):
    """Test that deployments are sorted by created_at descending."""
    deployment_1 = {
        "deployment_id": "deploy_1",
        "status": "SUCCESS",
        "created_at": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
        "updated_at": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
    }
    deployment_2 = {
        "deployment_id": "deploy_2",
        "status": "SUCCESS",
        "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        "updated_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
    }
    deployment_3 = {
        "deployment_id": "deploy_3",
        "status": "FAILED",
        "created_at": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
        "updated_at": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
    }

    # Return in mixed order
    mock_railway_client.get_recent_deployments.side_effect = [
        [deployment_1, deployment_3],  # fastapi
        [deployment_2],  # celery_worker
        [],  # celery_scheduler
    ]

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    deployments = section_data["deploy_context"]

    # Verify sorted by created_at descending (most recent first)
    assert deployments[0]["deployment_id"] == "deploy_3"  # 30 min ago
    assert deployments[1]["deployment_id"] == "deploy_2"  # 1 hour ago
    assert deployments[2]["deployment_id"] == "deploy_1"  # 3 hours ago


@pytest.mark.asyncio
async def test_collector_uses_ref_allocator(mock_railway_client, mock_store, bugcase):
    """Test that collector uses ref_allocator for reference IDs."""
    mock_railway_client.get_recent_deployments.return_value = []

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    refs = section_data["evidence_references"]

    # Verify reference ID format (should be E-001, E-002, etc.)
    ref_id = list(refs.keys())[0]
    assert ref_id.startswith("E-")


@pytest.mark.asyncio
async def test_collector_name_attribute(mock_railway_client):
    """Test that collector has correct collector_name attribute."""
    collector = DeployContextCollector(mock_railway_client)
    assert collector.collector_name == "deploy_context"


@pytest.mark.asyncio
async def test_collector_handles_missing_fields(mock_railway_client, mock_store, bugcase):
    """Test that collector handles deployments with missing fields gracefully."""
    deployments = [
        {
            "deployment_id": "deploy_1",
            "status": "SUCCESS",
            # missing created_at
            "updated_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        },
        {
            "deployment_id": "deploy_2",
            "status": "FAILED",
            "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            # missing updated_at
        },
    ]

    mock_railway_client.get_recent_deployments.side_effect = [
        deployments,  # fastapi
        [],  # celery_worker
        [],  # celery_scheduler
    ]

    collector = DeployContextCollector(mock_railway_client)
    ref_allocator = EvidenceReferenceAllocator()

    # Should not raise
    await collector.collect(bugcase, "pack_123", mock_store, ref_allocator)

    section_data = mock_store.update_evidence_pack_section.call_args[0][1]
    assert "deploy_context" in section_data
    assert len(section_data["deploy_context"]) == 2
