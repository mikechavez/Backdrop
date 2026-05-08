"""Tests for alert-to-case flow (FEATURE-059)."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.bugops.models import (
    BugAlertEventCreate,
    BugAlertEvent,
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


@pytest.fixture
def sample_alert_event():
    """Create a sample alert event for testing."""
    return BugAlertEventCreate(
        alert_id="alert_1",
        source_type="llm_traces",
        source_id="llm_traces.cost_runaway",
        alert_type="cost_runaway",
        severity=AlertSeverity.HIGH,
        title="Cost Runaway Detected",
        summary="LLM cost exceeded threshold in same UTC hour",
        domain=["llm", "cost"],
        service="openai",
        operation="completion",
        model="gpt-4",
        dedupe_key="cost_hourly_2026_05_08_14",
        correlation_keys=["service:openai", "model:gpt-4"],
        metric={"cost_usd": 45.67, "threshold_usd": 40.0},
    )


class TestProcessAlertEventNewCase:
    """Test that process_alert_event creates a new case for new dedupe_key."""

    @pytest.mark.asyncio
    async def test_new_alert_creates_case(self, store, sample_alert_event):
        """Test: First alert event for a dedupe_key creates a new case."""
        # Setup: mock create_alert_event to return an alert
        alert_doc = {
            "_id": "alert_obj_id",
            **sample_alert_event.model_dump(by_alias=False),
        }
        alert = BugAlertEvent(**alert_doc)

        # Setup: mock find_open_case_by_dedupe_key to return None (no existing case)
        case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_alert_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": sample_alert_event.title,
            "summary": sample_alert_event.summary,
            "dedupe_key": sample_alert_event.dedupe_key,
            "source_types": [sample_alert_event.source_type],
            "alert_ids": [sample_alert_event.alert_id],
            "correlation_keys": sample_alert_event.correlation_keys,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        case = BugCase(**case_doc)

        # Mock the store methods
        store.create_alert_event = AsyncMock(return_value=alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=case)

        # Execute
        result = await store.process_alert_event(sample_alert_event)

        # Verify
        assert result.case_id == "case_alert_1"
        assert result.status == CaseStatus.OPEN
        assert sample_alert_event.alert_id in result.alert_ids
        assert result.dedupe_key == sample_alert_event.dedupe_key
        store.create_alert_event.assert_called_once()
        store.find_open_case_by_dedupe_key.assert_called_once_with(
            sample_alert_event.dedupe_key
        )
        store.create_case_from_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_correlation_keys_preserved_in_new_case(
        self, store, sample_alert_event
    ):
        """Test: Correlation keys are preserved in newly created case."""
        alert_doc = {
            "_id": "alert_obj_id",
            **sample_alert_event.model_dump(by_alias=False),
        }
        alert = BugAlertEvent(**alert_doc)

        case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_alert_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": sample_alert_event.title,
            "summary": sample_alert_event.summary,
            "dedupe_key": sample_alert_event.dedupe_key,
            "source_types": [sample_alert_event.source_type],
            "alert_ids": [sample_alert_event.alert_id],
            "correlation_keys": sample_alert_event.correlation_keys,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        case = BugCase(**case_doc)

        store.create_alert_event = AsyncMock(return_value=alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=case)

        # Execute
        result = await store.process_alert_event(sample_alert_event)

        # Verify correlation keys preserved
        assert result.correlation_keys == sample_alert_event.correlation_keys
        assert "service:openai" in result.correlation_keys
        assert "model:gpt-4" in result.correlation_keys


class TestProcessAlertEventReusesOpenCase:
    """Test that process_alert_event reuses existing open cases."""

    @pytest.mark.asyncio
    async def test_same_dedupe_key_attaches_to_existing_case(self, store):
        """Test: Second alert with same dedupe_key attaches to existing open case."""
        # Setup: first alert that created a case
        first_alert_event = BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
        )

        # Second alert with same dedupe_key
        second_alert_event = BugAlertEventCreate(
            alert_id="alert_2",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded again",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
        )

        # Alert document for second alert
        second_alert_doc = {
            "_id": "alert_obj_id_2",
            **second_alert_event.model_dump(by_alias=False),
        }
        second_alert = BugAlertEvent(**second_alert_doc)

        # Existing open case
        existing_case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_alert_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_1"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        existing_case = BugCase(**existing_case_doc)

        # Case after attaching second alert
        updated_case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_alert_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_1", "alert_2"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        updated_case = BugCase(**updated_case_doc)

        # Mock the store methods
        store.create_alert_event = AsyncMock(return_value=second_alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=existing_case)
        store.attach_alert_to_case = AsyncMock(return_value=updated_case)

        # Execute
        result = await store.process_alert_event(second_alert_event)

        # Verify
        assert result.case_id == "case_alert_1"
        assert "alert_1" in result.alert_ids
        assert "alert_2" in result.alert_ids
        assert len(result.alert_ids) == 2
        store.create_alert_event.assert_called_once()
        store.find_open_case_by_dedupe_key.assert_called_once_with(
            "cost_hourly_2026_05_08_14"
        )
        store.attach_alert_to_case.assert_called_once_with(
            "case_alert_1", "alert_2"
        )


class TestProcessAlertEventClosedCaseHandling:
    """Test that process_alert_event does not reuse resolved/closed cases."""

    @pytest.mark.asyncio
    async def test_creates_new_case_if_prior_case_is_resolved(self, store):
        """Test: Creates new case if prior case is resolved."""
        alert_event = BugAlertEventCreate(
            alert_id="alert_3",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
        )

        alert_doc = {
            "_id": "alert_obj_id_3",
            **alert_event.model_dump(by_alias=False),
        }
        alert = BugAlertEvent(**alert_doc)

        new_case_doc = {
            "_id": "case_obj_id_new",
            "case_id": "case_alert_3",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_3"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        new_case = BugCase(**new_case_doc)

        # Mock: find_open_case_by_dedupe_key returns None because prior case
        # is resolved, not open
        store.create_alert_event = AsyncMock(return_value=alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=new_case)

        # Execute
        result = await store.process_alert_event(alert_event)

        # Verify
        assert result.case_id == "case_alert_3"
        assert result.status == CaseStatus.OPEN
        assert "alert_3" in result.alert_ids
        store.create_case_from_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_new_case_if_prior_case_is_closed(self, store):
        """Test: Creates new case if prior case is closed."""
        alert_event = BugAlertEventCreate(
            alert_id="alert_4",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
        )

        alert_doc = {
            "_id": "alert_obj_id_4",
            **alert_event.model_dump(by_alias=False),
        }
        alert = BugAlertEvent(**alert_doc)

        new_case_doc = {
            "_id": "case_obj_id_new",
            "case_id": "case_alert_4",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_4"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        new_case = BugCase(**new_case_doc)

        # Mock: find_open_case_by_dedupe_key returns None because prior case
        # is closed, not open
        store.create_alert_event = AsyncMock(return_value=alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=new_case)

        # Execute
        result = await store.process_alert_event(alert_event)

        # Verify
        assert result.case_id == "case_alert_4"
        assert result.status == CaseStatus.OPEN
        store.create_case_from_alert.assert_called_once()


class TestProcessAlertEventCorrelationKeys:
    """Test that correlation keys are preserved but not used for matching."""

    @pytest.mark.asyncio
    async def test_correlation_keys_not_used_for_matching(self, store):
        """Test: Alerts with same dedupe_key but different correlation_keys reuse case."""
        # First alert with certain correlation keys
        first_alert_event = BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
            correlation_keys=["service:openai", "model:gpt-4"],
        )

        # Second alert with same dedupe_key but different correlation keys
        second_alert_event = BugAlertEventCreate(
            alert_id="alert_2",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            dedupe_key="cost_hourly_2026_05_08_14",
            correlation_keys=["service:deepseek", "model:r1"],
        )

        second_alert_doc = {
            "_id": "alert_obj_id_2",
            **second_alert_event.model_dump(by_alias=False),
        }
        second_alert = BugAlertEvent(**second_alert_doc)

        existing_case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_1"],
            "correlation_keys": ["service:openai", "model:gpt-4"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        existing_case = BugCase(**existing_case_doc)

        updated_case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_1", "alert_2"],
            "correlation_keys": ["service:openai", "model:gpt-4"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        updated_case = BugCase(**updated_case_doc)

        store.create_alert_event = AsyncMock(return_value=second_alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=existing_case)
        store.attach_alert_to_case = AsyncMock(return_value=updated_case)

        # Execute
        result = await store.process_alert_event(second_alert_event)

        # Verify: reused same case despite different correlation keys
        assert result.case_id == "case_1"
        assert "alert_1" in result.alert_ids
        assert "alert_2" in result.alert_ids
        # Matching was only by dedupe_key, not correlation keys
        store.find_open_case_by_dedupe_key.assert_called_once_with(
            "cost_hourly_2026_05_08_14"
        )


class TestProcessAlertEventNoFuzzyCorrelation:
    """Test that no fuzzy correlation logic is implemented."""

    @pytest.mark.asyncio
    async def test_no_time_window_correlation(self, store):
        """Test: Alerts in different time windows create separate cases."""
        # Two alerts with same service/model but different hourly dedupe keys
        first_alert_event = BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            service="openai",
            operation="completion",
            model="gpt-4",
            dedupe_key="cost_hourly_2026_05_08_14",
        )

        second_alert_event = BugAlertEventCreate(
            alert_id="alert_2",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            service="openai",
            operation="completion",
            model="gpt-4",
            dedupe_key="cost_hourly_2026_05_08_15",  # Different hour
        )

        first_alert_doc = {
            "_id": "alert_obj_id_1",
            **first_alert_event.model_dump(by_alias=False),
        }
        first_alert = BugAlertEvent(**first_alert_doc)

        second_alert_doc = {
            "_id": "alert_obj_id_2",
            **second_alert_event.model_dump(by_alias=False),
        }
        second_alert = BugAlertEvent(**second_alert_doc)

        first_case_doc = {
            "_id": "case_obj_id_1",
            "case_id": "case_1",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_14",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_1"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        first_case = BugCase(**first_case_doc)

        second_case_doc = {
            "_id": "case_obj_id_2",
            "case_id": "case_2",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "cost_hourly_2026_05_08_15",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_2"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        second_case = BugCase(**second_case_doc)

        # When second alert is processed, no open case exists for its dedupe_key
        store.create_alert_event = AsyncMock(return_value=second_alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=second_case)

        # Execute
        result = await store.process_alert_event(second_alert_event)

        # Verify: created new case, no fuzzy matching by service/model
        assert result.case_id == "case_2"
        assert result.dedupe_key == "cost_hourly_2026_05_08_15"
        store.create_case_from_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_service_correlation(self, store):
        """Test: Alerts with same service but different dedupe_key create separate cases."""
        # Two alerts with same service but different dedupe keys
        first_event = BugAlertEventCreate(
            alert_id="alert_1",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            service="openai",
            dedupe_key="openai_key_1",
        )

        second_event = BugAlertEventCreate(
            alert_id="alert_2",
            source_type="llm_traces",
            source_id="llm_traces.cost_runaway",
            alert_type="cost_runaway",
            severity=AlertSeverity.HIGH,
            title="Cost Runaway",
            summary="Cost exceeded",
            domain=["llm", "cost"],
            service="openai",
            dedupe_key="openai_key_2",
        )

        second_alert_doc = {
            "_id": "alert_obj_id_2",
            **second_event.model_dump(by_alias=False),
        }
        second_alert = BugAlertEvent(**second_alert_doc)

        new_case_doc = {
            "_id": "case_obj_id",
            "case_id": "case_2",
            "status": CaseStatus.OPEN,
            "severity": AlertSeverity.HIGH,
            "title": "Cost Runaway",
            "summary": "Cost exceeded",
            "dedupe_key": "openai_key_2",
            "source_types": ["llm_traces"],
            "alert_ids": ["alert_2"],
            "correlation_keys": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        new_case = BugCase(**new_case_doc)

        store.create_alert_event = AsyncMock(return_value=second_alert)
        store.find_open_case_by_dedupe_key = AsyncMock(return_value=None)
        store.create_case_from_alert = AsyncMock(return_value=new_case)

        # Execute
        result = await store.process_alert_event(second_event)

        # Verify: created separate case, service not used for matching
        assert result.case_id == "case_2"
        assert result.dedupe_key == "openai_key_2"
        store.find_open_case_by_dedupe_key.assert_called_once_with("openai_key_2")
