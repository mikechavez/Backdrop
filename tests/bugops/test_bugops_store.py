"""Tests for BugOps store."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
    AlertSeverity,
    AlertStatus,
    CaseStatus,
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


@pytest.mark.asyncio
async def test_create_alert_event(store):
    """Test creating an alert event."""
    # Setup
    event = BugAlertEventCreate(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.HIGH,
        title="Cost Runaway",
        summary="Cost exceeded",
        domain=["llm", "cost"],
        dedupe_key="cost_1",
    )

    # Mock insert_one
    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = "object_id_1"
    store.alert_events_collection.insert_one = mock_insert

    # Execute
    result = await store.create_alert_event(event)

    # Verify
    assert result.alert_id == "alert_1"
    assert result.severity == AlertSeverity.HIGH
    assert mock_insert.called


@pytest.mark.asyncio
async def test_find_open_case_by_dedupe_key_returns_open_case(store):
    """Test find_open_case_by_dedupe_key returns open case."""
    # Setup
    case_doc = {
        "_id": "id_1",
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1"],
        "correlation_keys": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_find_one = AsyncMock()
    mock_find_one.return_value = case_doc
    store.cases_collection.find_one = mock_find_one

    # Execute
    result = await store.find_open_case_by_dedupe_key("test_1")

    # Verify
    assert result is not None
    assert result.case_id == "case_1"
    assert result.status == CaseStatus.OPEN
    mock_find_one.assert_called_once_with({
        "dedupe_key": "test_1",
        "status": "open"
    })


@pytest.mark.asyncio
async def test_find_open_case_by_dedupe_key_ignores_resolved_cases(store):
    """Test find_open_case_by_dedupe_key ignores resolved cases."""
    # Setup
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None  # No open case found
    store.cases_collection.find_one = mock_find_one

    # Execute
    result = await store.find_open_case_by_dedupe_key("test_1")

    # Verify
    assert result is None
    # Verify it searched for "open" status only
    mock_find_one.assert_called_once_with({
        "dedupe_key": "test_1",
        "status": "open"
    })


@pytest.mark.asyncio
async def test_find_open_case_by_dedupe_key_ignores_closed_cases(store):
    """Test find_open_case_by_dedupe_key ignores closed cases."""
    # This is verified by the status filter in the query
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    store.cases_collection.find_one = mock_find_one

    result = await store.find_open_case_by_dedupe_key("test_1")

    assert result is None
    # Verify query filters for "open" status
    call_args = mock_find_one.call_args[0][0]
    assert call_args["status"] == "open"


@pytest.mark.asyncio
async def test_create_case_from_alert(store):
    """Test creating a case from an alert."""
    # Setup
    alert = BugAlertEvent(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.HIGH,
        title="Cost Runaway",
        summary="Cost exceeded",
        domain=["llm", "cost"],
        dedupe_key="cost_1",
    )

    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = "case_object_id"
    store.cases_collection.insert_one = mock_insert

    # Execute
    result = await store.create_case_from_alert(alert)

    # Verify
    assert result.status == CaseStatus.OPEN
    assert alert.alert_id in result.alert_ids
    assert result.severity == AlertSeverity.HIGH
    assert mock_insert.called


@pytest.mark.asyncio
async def test_create_case_from_alert_creates_open_status(store):
    """Test create_case_from_alert creates status=open."""
    alert = BugAlertEvent(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.HIGH,
        title="Test",
        summary="Test",
        domain=["llm"],
        dedupe_key="test_1",
    )

    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = "id"
    store.cases_collection.insert_one = mock_insert

    result = await store.create_case_from_alert(alert)

    assert result.status == CaseStatus.OPEN


@pytest.mark.asyncio
async def test_attach_alert_to_case(store):
    """Test attaching an alert to an existing case."""
    # Setup
    case_doc = {
        "_id": "id_1",
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1", "alert_2"],
        "correlation_keys": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    # Execute
    result = await store.attach_alert_to_case("case_1", "alert_2")

    # Verify
    assert result.case_id == "case_1"
    assert "alert_2" in result.alert_ids
    assert mock_find_one_and_update.called


@pytest.mark.asyncio
async def test_attach_alert_to_case_appends_alert_id(store):
    """Test attach_alert_to_case appends alert ID."""
    case_doc = {
        "_id": "id",
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1"],
        "correlation_keys": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_alert_to_case("case_1", "alert_2")

    # Verify $addToSet was used
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$addToSet" in update_doc


@pytest.mark.asyncio
async def test_attach_alert_to_case_updates_timestamp(store):
    """Test attach_alert_to_case updates timestamp."""
    case_doc = {
        "_id": "id",
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": [],
        "correlation_keys": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_alert_to_case("case_1", "alert_1")

    # Verify $set was used for updated_at
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$set" in update_doc
    assert "updated_at" in update_doc["$set"]


@pytest.mark.asyncio
async def test_get_case(store):
    """Test getting a case by case_id."""
    # Setup
    case_doc = {
        "_id": "id_1",
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1"],
        "correlation_keys": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_find_one = AsyncMock()
    mock_find_one.return_value = case_doc
    store.cases_collection.find_one = mock_find_one

    # Execute
    result = await store.get_case("case_1")

    # Verify
    assert result is not None
    assert result.case_id == "case_1"
    mock_find_one.assert_called_once_with({"case_id": "case_1"})


@pytest.mark.asyncio
async def test_get_case_returns_none_if_not_found(store):
    """Test get_case returns None if case not found."""
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    store.cases_collection.find_one = mock_find_one

    result = await store.get_case("nonexistent")

    assert result is None
