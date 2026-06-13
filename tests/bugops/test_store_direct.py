"""Tests for BugOpsStore direct case creation and observation attachment."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import (
    BugCaseCreate,
    BugCase,
    AlertSeverity,
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
async def test_create_case_direct_calls_insert_one(store):
    """Test create_case_direct calls insert_one and returns BugCase."""
    case = BugCaseCreate(
        case_id="case_1",
        status="open",
        severity=AlertSeverity.HIGH,
        alert_type="cost_runaway",
        title="Cost Runaway",
        summary="Cost exceeded",
        dedupe_key="cost_1",
        source_types=["llm_traces"],
    )

    obj_id = ObjectId()
    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = obj_id
    store.cases_collection.insert_one = mock_insert

    result = await store.create_case_direct(case)

    assert result.case_id == "case_1"
    assert result.status == CaseStatus.OPEN
    assert result.severity == AlertSeverity.HIGH
    assert isinstance(result.id, str)
    assert result.id == str(obj_id)
    mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_case_direct_with_sprint020_fields(store):
    """Test create_case_direct with all Sprint 020 optional fields populated."""
    now = datetime.utcnow()
    case = BugCaseCreate(
        case_id="case_1",
        status="open",
        severity=AlertSeverity.HIGH,
        alert_type="article_freshness",
        title="Article Freshness Failure",
        summary="No articles inserted for 42 minutes",
        dedupe_key="article_freshness:articles",
        source_types=["freshness"],
        root_subsystem="articles",
        affected_subsystems=["signals", "narratives"],
        first_seen_at=now,
        last_seen_at=now,
        observation_count=1,
        detection_type="startup",
    )

    obj_id = ObjectId()
    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = obj_id
    store.cases_collection.insert_one = mock_insert

    result = await store.create_case_direct(case)

    assert result.case_id == "case_1"
    assert result.root_subsystem == "articles"
    assert result.affected_subsystems == ["signals", "narratives"]
    assert result.observation_count == 1
    assert result.detection_type == "startup"


@pytest.mark.asyncio
async def test_create_case_direct_normalizes_objectid(store):
    """Test create_case_direct normalizes ObjectId _id to string."""
    case = BugCaseCreate(
        case_id="case_1",
        status="open",
        severity=AlertSeverity.HIGH,
        alert_type="cost_runaway",
        title="Test",
        summary="Test",
        dedupe_key="test_1",
        source_types=["llm_traces"],
    )

    obj_id = ObjectId()
    mock_insert = AsyncMock()
    mock_insert.return_value.inserted_id = obj_id
    store.cases_collection.insert_one = mock_insert

    result = await store.create_case_direct(case)

    assert isinstance(result.id, str)
    assert result.id == str(obj_id)


@pytest.mark.asyncio
async def test_attach_observation_to_case_increments_observation_count(store):
    """Test attach_observation_to_case uses $inc on observation_count."""
    now = datetime.utcnow()
    case_doc = {
        "_id": ObjectId(),
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "alert_type": "cost_runaway",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1"],
        "observation_count": 1,
        "correlation_keys": [],
        "metric": {},
        "created_at": now,
        "updated_at": now,
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_observation_to_case("case_1", now)

    # Verify $inc was used
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$inc" in update_doc
    assert update_doc["$inc"]["observation_count"] == 1


@pytest.mark.asyncio
async def test_attach_observation_to_case_sets_last_seen_at(store):
    """Test attach_observation_to_case sets last_seen_at correctly."""
    now = datetime.utcnow()
    case_doc = {
        "_id": ObjectId(),
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "alert_type": "cost_runaway",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": [],
        "observation_count": 1,
        "correlation_keys": [],
        "metric": {},
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_observation_to_case("case_1", now)

    # Verify $set was used for last_seen_at
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$set" in update_doc
    assert "last_seen_at" in update_doc["$set"]
    assert "updated_at" in update_doc["$set"]


@pytest.mark.asyncio
async def test_attach_observation_to_case_with_affected_subsystems(store):
    """Test attach_observation_to_case with affected_subsystems uses $addToSet."""
    now = datetime.utcnow()
    case_doc = {
        "_id": ObjectId(),
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "alert_type": "article_freshness",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "root_subsystem": "articles",
        "affected_subsystems": ["signals"],
        "source_types": ["freshness"],
        "alert_ids": [],
        "observation_count": 1,
        "correlation_keys": [],
        "metric": {},
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_observation_to_case(
        "case_1",
        now,
        affected_subsystems=["narratives", "briefings"]
    )

    # Verify $addToSet was used with $each
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$addToSet" in update_doc
    assert "affected_subsystems" in update_doc["$addToSet"]
    assert "$each" in update_doc["$addToSet"]["affected_subsystems"]
    assert update_doc["$addToSet"]["affected_subsystems"]["$each"] == [
        "narratives", "briefings"
    ]


@pytest.mark.asyncio
async def test_attach_observation_to_case_without_affected_subsystems(store):
    """Test attach_observation_to_case with affected_subsystems=None doesn't include $addToSet."""
    now = datetime.utcnow()
    case_doc = {
        "_id": ObjectId(),
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "alert_type": "cost_runaway",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": [],
        "observation_count": 1,
        "correlation_keys": [],
        "metric": {},
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    await store.attach_observation_to_case("case_1", now, affected_subsystems=None)

    # Verify $addToSet is NOT included
    call_args = mock_find_one_and_update.call_args[0]
    update_doc = call_args[1]
    assert "$addToSet" not in update_doc
    assert "$inc" in update_doc
    assert "$set" in update_doc


@pytest.mark.asyncio
async def test_attach_observation_to_case_raises_on_not_found(store):
    """Test attach_observation_to_case raises ValueError when case not found."""
    now = datetime.utcnow()
    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = None
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    with pytest.raises(ValueError, match="Case case_1 not found"):
        await store.attach_observation_to_case("case_1", now)


@pytest.mark.asyncio
async def test_attach_observation_to_case_returns_bugcase(store):
    """Test attach_observation_to_case returns updated BugCase."""
    now = datetime.utcnow()
    obj_id = ObjectId()
    case_doc = {
        "_id": obj_id,
        "case_id": "case_1",
        "status": "open",
        "severity": "high",
        "alert_type": "cost_runaway",
        "title": "Test",
        "summary": "Test",
        "dedupe_key": "test_1",
        "source_types": ["llm_traces"],
        "alert_ids": ["alert_1"],
        "observation_count": 2,
        "correlation_keys": [],
        "metric": {},
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }

    mock_find_one_and_update = AsyncMock()
    mock_find_one_and_update.return_value = case_doc
    store.cases_collection.find_one_and_update = mock_find_one_and_update

    result = await store.attach_observation_to_case("case_1", now)

    assert isinstance(result, BugCase)
    assert result.case_id == "case_1"
    assert result.observation_count == 2
    assert isinstance(result.id, str)
    assert result.id == str(obj_id)
