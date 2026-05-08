"""Tests for LLM traces cost signal source."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.signal_sources.llm_traces import LLMTraceCostSignalSource
from crypto_news_aggregator.bugops.models import AlertSeverity


@pytest.fixture
def source():
    """Create a cost signal source instance."""
    return LLMTraceCostSignalSource()


def create_mock_settings():
    """Create mock settings with threshold values."""
    settings = MagicMock()
    settings.BUGOPS_COST_5MIN_THRESHOLD_USD = 0.25
    settings.BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD = 1.00
    return settings


@pytest.mark.asyncio
async def test_no_traces_returns_empty_list(source):
    """Test that no traces returns empty alert list."""
    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_collection = AsyncMock()
        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=[])
        mock_collection.find = MagicMock(return_value=mock_find)
        mock_db.llm_traces = mock_collection

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert result == []


@pytest.mark.asyncio
async def test_spend_below_thresholds_returns_empty_list(source):
    """Test that spend below thresholds returns no alert."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=2),
            "cost": 0.05,
            "operation": "test_op",
            "model": "test_model",
        },
        {
            "timestamp": now - timedelta(minutes=3),
            "cost": 0.03,
            "operation": "test_op",
            "model": "test_model",
        },
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert result == []


@pytest.mark.asyncio
async def test_projected_hourly_threshold_warning_alert(source):
    """Test warning alert when projected hourly threshold breached."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=2),
            "cost": 0.10,
            "operation": "narrative_generate",
            "model": "claude-haiku",
        },
        {
            "timestamp": now - timedelta(minutes=3),
            "cost": 0.11,
            "operation": "narrative_generate",
            "model": "claude-haiku",
        },
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]
        assert event.severity == AlertSeverity.WARNING
        assert event.alert_type == "cost_runaway"
        assert event.source_type == "llm_traces"
        assert event.source_id == "llm_traces.cost_runaway"
        assert event.domain == ["llm", "cost"]
        assert "domain:llm" in event.correlation_keys
        assert "domain:cost" in event.correlation_keys


@pytest.mark.asyncio
async def test_5min_threshold_critical_alert(source):
    """Test critical alert when 5-minute threshold breached."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.15,
            "operation": "entity_extraction",
            "model": "deepseek-v4",
        },
        {
            "timestamp": now - timedelta(minutes=2),
            "cost": 0.12,
            "operation": "entity_extraction",
            "model": "deepseek-v4",
        },
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]
        assert event.severity == AlertSeverity.CRITICAL
        assert event.alert_type == "cost_runaway"


@pytest.mark.asyncio
async def test_dedupe_key_format(source):
    """Test dedupe key uses UTC date and hour format."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.30,
            "operation": "test",
            "model": "test",
        }
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]
        dedupe_key = event.dedupe_key

        assert dedupe_key.startswith("llm_traces:cost_runaway:")
        parts = dedupe_key.split(":")
        assert len(parts) == 4
        assert parts[0] == "llm_traces"
        assert parts[1] == "cost_runaway"
        assert len(parts[2]) == 10
        assert parts[2].count("-") == 2
        assert len(parts[3]) == 2
        assert parts[3].isdigit()


@pytest.mark.asyncio
async def test_metric_payload_includes_required_fields(source):
    """Test metric payload includes all required fields."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.30,
            "operation": "briefing_generate",
            "model": "claude-haiku",
        }
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]
        metric = event.metric

        assert "last_5_min_spend" in metric
        assert "last_60_min_spend" in metric
        assert "projected_hourly_spend" in metric
        assert "threshold_5min" in metric
        assert "threshold_projected_hourly" in metric
        assert "top_operations" in metric
        assert "top_models" in metric
        assert "window_start" in metric
        assert "window_end" in metric

        assert isinstance(metric["last_5_min_spend"], float)
        assert isinstance(metric["last_60_min_spend"], float)
        assert isinstance(metric["projected_hourly_spend"], float)
        assert isinstance(metric["top_operations"], list)
        assert isinstance(metric["top_models"], list)


@pytest.mark.asyncio
async def test_top_operations_and_models_populated(source):
    """Test that top operations and models are populated in metric and correlation_keys."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.15,
            "operation": "entity_extraction",
            "model": "deepseek-v4",
        },
        {
            "timestamp": now - timedelta(minutes=2),
            "cost": 0.12,
            "operation": "narrative_generate",
            "model": "claude-haiku",
        },
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]

        assert len(event.metric["top_operations"]) > 0
        assert len(event.metric["top_models"]) > 0

        assert event.operation is not None
        assert event.model is not None

        assert f"operation:{event.operation}" in event.correlation_keys
        assert f"model:{event.model}" in event.correlation_keys


@pytest.mark.asyncio
async def test_correlation_keys_include_domain(source):
    """Test that correlation keys include domain and optionally operation/model."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.30,
            "operation": "test_op",
            "model": "test_model",
        }
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        event = result[0]

        assert "domain:llm" in event.correlation_keys
        assert "domain:cost" in event.correlation_keys


@pytest.mark.asyncio
async def test_handles_missing_operation_field(source):
    """Test that source handles traces with missing operation field."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.30,
            "model": "test_model",
        }
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        assert result[0].operation is None


@pytest.mark.asyncio
async def test_handles_missing_model_field(source):
    """Test that source handles traces with missing model field."""
    now = datetime.now(timezone.utc)
    traces = [
        {
            "timestamp": now - timedelta(minutes=1),
            "cost": 0.30,
            "operation": "test_op",
        }
    ]

    with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.mongo_manager") as mock_mongo:
        mock_db = AsyncMock()
        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        mock_find = AsyncMock()
        mock_find.to_list = AsyncMock(return_value=traces)
        mock_db.llm_traces.find = MagicMock(return_value=mock_find)

        with patch("crypto_news_aggregator.bugops.signal_sources.llm_traces.get_settings", return_value=create_mock_settings()):
            result = await source.collect()

        assert len(result) == 1
        assert result[0].model is None
