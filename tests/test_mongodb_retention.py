"""Focused tests for storage thresholds and bounded cleanup behavior."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from crypto_news_aggregator.services.mongodb_retention import (
    _bounded_delete,
    classify_storage_usage,
    storage_report,
)
from crypto_news_aggregator.tasks.mongodb_retention import cleanup_mongodb_retention
from crypto_news_aggregator.bugops.signal_sources.mongodb_storage import MongoStorageSignalSource
from crypto_news_aggregator.api.v1.health import check_mongodb_retention_indexes


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(None, None), (74.9, None), (75, "warning"), (89.9, "warning"), (90, "critical")],
)
def test_classify_storage_usage_thresholds(percent, expected):
    assert classify_storage_usage(percent, 75, 90) == expected


@pytest.mark.asyncio
async def test_storage_report_labels_db_stats_as_estimate():
    db = AsyncMock()
    db.command.return_value = {
        "db": "crypto_news",
        "collections": 4,
        "dataSize": 100,
        "storageSize": 200,
        "indexSize": 100,
    }

    report = await storage_report(db, 1 / (1024 * 1024))

    assert report["estimated_used_bytes"] == 300
    assert report["estimated_percent_used"] == pytest.approx(30_000)
    assert "estimate" in report["measurement"]


@pytest.mark.asyncio
async def test_missing_storage_metrics_are_not_reported_as_zero():
    db = AsyncMock()
    db.command.return_value = {"db": "crypto_news"}

    report = await storage_report(db, 512)

    assert report["estimated_percent_used"] is None
    assert report["estimated_used_bytes"] is None
    assert classify_storage_usage(report["estimated_percent_used"], 75, 90) is None


@pytest.mark.asyncio
async def test_bounded_delete_dry_run_never_deletes():
    collection = AsyncMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"_id": "a"}, {"_id": "b"}])
    collection.find = MagicMock(return_value=cursor)
    collection.count_documents.return_value = 20
    db = MagicMock()
    db.__getitem__.return_value = collection

    result = await _bounded_delete(db, "llm_traces", {"x": 1}, 2, dry_run=True)

    assert result["matched_count"] == 20
    assert result["selected_count"] == 2
    assert result["deleted_count"] == 0
    collection.delete_many.assert_not_awaited()
    cursor.limit.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_bounded_delete_only_deletes_selected_ids():
    collection = AsyncMock()
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"_id": "safe-id"}])
    collection.find = MagicMock(return_value=cursor)
    collection.count_documents.return_value = 1
    collection.delete_many.return_value.deleted_count = 1
    db = MagicMock()
    db.__getitem__.return_value = collection

    result = await _bounded_delete(db, "llm_cache", {"expired": True}, 10, dry_run=False)

    assert result["deleted_count"] == 1
    collection.delete_many.assert_awaited_once_with({"_id": {"$in": ["safe-id"]}})


def test_manual_task_requires_explicit_confirmation_for_deletion():
    with pytest.raises(ValueError, match="confirm=True"):
        cleanup_mongodb_retention.run(dry_run=False, confirm=False)


def test_retention_task_is_scheduled_daily():
    from crypto_news_aggregator.tasks.celery_config import get_beat_schedule

    schedule = get_beat_schedule()["mongodb-retention-cleanup"]
    assert schedule["task"] == "mongodb_retention_cleanup"
    assert schedule["kwargs"] == {"dry_run": False, "confirm": True}


@pytest.mark.asyncio
async def test_storage_signal_uses_bugops_event_and_discloses_estimate(monkeypatch):
    from crypto_news_aggregator.bugops.signal_sources import mongodb_storage

    class FakeSettings:
        MONGODB_STORAGE_QUOTA_MB = 512
        MONGODB_STORAGE_WARNING_PERCENT = 75
        MONGODB_STORAGE_CRITICAL_PERCENT = 90

    db = AsyncMock()
    db.command.return_value = {
        "db": "crypto_news", "collections": 1, "dataSize": 0,
        "storageSize": 400, "indexSize": 100,
    }
    monkeypatch.setattr(mongodb_storage, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(mongodb_storage.mongo_manager, "get_async_database", AsyncMock(return_value=db))

    events = await MongoStorageSignalSource().collect()

    assert events == []  # Small byte count is below configured estimate thresholds.

    db.command.return_value.update(storageSize=400 * 1024 * 1024, indexSize=100 * 1024 * 1024)
    events = await MongoStorageSignalSource().collect()
    assert len(events) == 1
    assert events[0].severity.value == "critical"
    assert "estimate" in events[0].summary
    assert events[0].metric["measurement"].startswith("MongoDB dbStats estimate")


@pytest.mark.asyncio
async def test_health_retention_check_reports_missing_ttl_as_warning(monkeypatch):
    from crypto_news_aggregator.api.v1 import health

    class FakeSettings:
        LLM_TRACE_RETENTION_DAYS = 30

    trace_collection = AsyncMock()
    trace_collection.index_information.return_value = {}
    cache_collection = AsyncMock()
    cache_collection.index_information.return_value = {}
    db = MagicMock()
    db.llm_traces = trace_collection
    db.llm_cache = cache_collection
    monkeypatch.setattr(health, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(health.mongo_manager, "get_async_database", AsyncMock(return_value=db))

    result = await check_mongodb_retention_indexes()

    assert result["status"] == "warning"
    assert result["llm_traces_ttl_seconds"] is None
    assert result["llm_cache_ttl_seconds"] is None
