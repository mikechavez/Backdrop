"""Tests for pipeline heartbeat tracking."""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from crypto_news_aggregator.services.heartbeat import record_heartbeat, get_heartbeat


@pytest.mark.asyncio
async def test_record_heartbeat_creates_new_document():
    """Test that record_heartbeat creates a new heartbeat document."""
    mock_db = AsyncMock()
    mock_db.pipeline_heartbeats = AsyncMock()

    await record_heartbeat(
        mock_db,
        stage="fetch_news",
        duration_seconds=45.2,
        summary="Fetched 127 articles from 8 feeds",
    )

    # Verify update_one was called with upsert=True
    mock_db.pipeline_heartbeats.update_one.assert_called_once()
    call_args = mock_db.pipeline_heartbeats.update_one.call_args

    # Check filter
    assert call_args[0][0] == {"_id": "fetch_news"}

    # Check update dict contains expected fields
    update_dict = call_args[0][1]
    assert "$set" in update_dict
    assert "last_success" in update_dict["$set"]
    assert update_dict["$set"]["last_duration_seconds"] == 45.2
    assert "Fetched 127 articles" in update_dict["$set"]["last_result_summary"]

    # Check upsert flag
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_record_heartbeat_handles_exception():
    """Test that record_heartbeat doesn't break on exception."""
    mock_db = AsyncMock()
    mock_db.pipeline_heartbeats = AsyncMock()
    mock_db.pipeline_heartbeats.update_one.side_effect = Exception("DB error")

    # Should not raise
    await record_heartbeat(
        mock_db,
        stage="fetch_news",
        duration_seconds=45.2,
        summary="Test",
    )


@pytest.mark.asyncio
async def test_get_heartbeat_returns_document():
    """Test that get_heartbeat retrieves a document."""
    mock_db = AsyncMock()
    expected_doc = {
        "_id": "fetch_news",
        "last_success": datetime.now(timezone.utc),
        "last_duration_seconds": 45.2,
        "last_result_summary": "Fetched 127 articles",
    }
    mock_db.pipeline_heartbeats = AsyncMock()
    mock_db.pipeline_heartbeats.find_one.return_value = expected_doc

    result = await get_heartbeat(mock_db, "fetch_news")

    assert result == expected_doc
    mock_db.pipeline_heartbeats.find_one.assert_called_once_with({"_id": "fetch_news"})


@pytest.mark.asyncio
async def test_get_heartbeat_returns_none_if_not_found():
    """Test that get_heartbeat returns None if stage not found."""
    mock_db = AsyncMock()
    mock_db.pipeline_heartbeats = AsyncMock()
    mock_db.pipeline_heartbeats.find_one.return_value = None

    result = await get_heartbeat(mock_db, "nonexistent_stage")

    assert result is None


@pytest.mark.asyncio
async def test_get_heartbeat_handles_exception():
    """Test that get_heartbeat returns None on exception."""
    mock_db = AsyncMock()
    mock_db.pipeline_heartbeats = AsyncMock()
    mock_db.pipeline_heartbeats.find_one.side_effect = Exception("DB error")

    result = await get_heartbeat(mock_db, "fetch_news")

    assert result is None


@pytest.mark.asyncio
async def test_record_heartbeat_truncates_summary():
    """Test that record_heartbeat truncates summary to 500 chars."""
    mock_db = AsyncMock()
    mock_db.pipeline_heartbeats = AsyncMock()

    long_summary = "x" * 600

    await record_heartbeat(
        mock_db,
        stage="fetch_news",
        duration_seconds=45.2,
        summary=long_summary,
    )

    call_args = mock_db.pipeline_heartbeats.update_one.call_args
    update_dict = call_args[0][1]
    summary = update_dict["$set"]["last_result_summary"]

    assert len(summary) == 500
    assert summary == "x" * 500
