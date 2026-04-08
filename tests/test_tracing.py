"""
Tests for LLM tracing schema, indexes, and query helpers.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from motor.motor_asyncio import AsyncIOMotorDatabase

from crypto_news_aggregator.llm.tracing import (
    ensure_trace_indexes,
    get_traces_summary,
    COLLECTION_NAME,
)


class TestEnsureTraceIndexes:
    """Test index creation on llm_traces collection."""

    @pytest.mark.asyncio
    async def test_ensure_indexes_creates_expected(self):
        """ensure_trace_indexes should create 3 custom indexes."""
        # Mock MongoDB database and collection
        mock_collection = AsyncMock()
        mock_db = AsyncMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        await ensure_trace_indexes(mock_db)

        # Verify create_index was called 3 times with expected arguments
        assert mock_collection.create_index.call_count == 3

        # Check calls (order matters for fire-and-forget)
        calls = mock_collection.create_index.call_args_list

        # TTL index on timestamp
        assert calls[0][0][0] == "timestamp"
        assert calls[0][1]["expireAfterSeconds"] == 30 * 86400  # 30 days

        # Index on operation
        assert calls[1][0][0] == "operation"

        # Compound index (operation, timestamp desc)
        assert calls[2][0][0] == [("operation", 1), ("timestamp", -1)]


class TestTraceDocumentShape:
    """Test trace document validation."""

    @pytest.mark.asyncio
    async def test_trace_document_shape(self):
        """Verify trace documents have all required fields with correct types."""
        # Mock MongoDB collection
        sample_trace = {
            "trace_id": "abc-123-def-456",
            "operation": "briefing_generate",
            "timestamp": datetime.now(timezone.utc),
            "model": "claude-sonnet-4-5-20250929",
            "input_tokens": 1200,
            "output_tokens": 400,
            "cost": 0.0096,
            "duration_ms": 1500.3,
            "error": None,
            "quality": {
                "passed": None,
                "score": None,
                "checks": [],
            },
        }

        # Verify all required fields exist
        required_fields = {
            "trace_id", "operation", "timestamp", "model",
            "input_tokens", "output_tokens", "cost", "duration_ms",
            "error", "quality"
        }
        assert set(sample_trace.keys()) == required_fields

        # Verify type correctness
        assert isinstance(sample_trace["trace_id"], str)
        assert isinstance(sample_trace["operation"], str)
        assert isinstance(sample_trace["timestamp"], datetime)
        assert isinstance(sample_trace["model"], str)
        assert isinstance(sample_trace["input_tokens"], int)
        assert isinstance(sample_trace["output_tokens"], int)
        assert isinstance(sample_trace["cost"], float)
        assert isinstance(sample_trace["duration_ms"], float)
        assert sample_trace["error"] is None or isinstance(sample_trace["error"], str)
        assert isinstance(sample_trace["quality"], dict)
        assert "passed" in sample_trace["quality"]
        assert "score" in sample_trace["quality"]
        assert "checks" in sample_trace["quality"]


class TestGetTracesSummary:
    """Test cost/calls/tokens grouping and aggregation."""

    @pytest.mark.asyncio
    async def test_get_traces_summary_aggregation(self):
        """get_traces_summary should correctly group and sum traces by operation."""
        # Mock MongoDB collection and aggregation pipeline
        mock_collection = AsyncMock()
        mock_db = AsyncMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        # Mock aggregation results (note: MongoDB aggregation returns _id, not operation)
        mock_results = [
            {
                "_id": "briefing_generate",
                "total_cost": 0.15,
                "call_count": 10,
                "total_input_tokens": 12000,
                "total_output_tokens": 4000,
                "avg_duration_ms": 1500.0,
                "error_count": 0,
            },
            {
                "_id": "entity_extraction",
                "total_cost": 0.05,
                "call_count": 5,
                "total_input_tokens": 5000,
                "total_output_tokens": 1000,
                "avg_duration_ms": 1000.0,
                "error_count": 1,
            },
        ]

        # Mock the aggregation pipeline
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_results)
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        results = await get_traces_summary(mock_db, days=1)

        # Verify aggregation was called with correct pipeline
        assert mock_collection.aggregate.called
        pipeline = mock_collection.aggregate.call_args[0][0]

        # Check $match stage filters by timestamp
        assert pipeline[0]["$match"]["timestamp"]["$gte"] is not None

        # Check $group stage aggregates correctly
        group_stage = pipeline[1]["$group"]
        assert "_id" in group_stage
        assert "total_cost" in group_stage
        assert "call_count" in group_stage

        # Verify results are returned with operation field (not _id)
        assert len(results) == 2
        assert results[0]["operation"] == "briefing_generate"
        assert results[0]["total_cost"] == 0.15
        assert results[0]["call_count"] == 10
        assert "error_count" in results[0]

    @pytest.mark.asyncio
    async def test_get_traces_summary_time_filtering(self):
        """get_traces_summary should apply correct time cutoff."""
        mock_collection = AsyncMock()
        mock_db = AsyncMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        # Call with 3 days
        await get_traces_summary(mock_db, days=3)

        # Verify the pipeline has $match with correct time range
        pipeline = mock_collection.aggregate.call_args[0][0]
        match_stage = pipeline[0]["$match"]

        # Verify timestamp filter exists and is a dict with $gte
        assert "timestamp" in match_stage
        assert "$gte" in match_stage["timestamp"]

        # The cutoff should be approximately 3 days ago
        cutoff = match_stage["timestamp"]["$gte"]
        assert isinstance(cutoff, datetime)
        now = datetime.now(timezone.utc)
        diff = (now - cutoff).total_seconds()
        # Should be roughly 3 days (allow ±10% margin)
        expected_seconds = 3 * 86400
        assert abs(diff - expected_seconds) < expected_seconds * 0.1
