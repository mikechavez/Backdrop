"""Tests for health endpoint pipeline heartbeat checks.

Note: These tests are integration tests that verify the health endpoint correctly
integrates pipeline heartbeat checks. Full end-to-end testing requires running
against a real MongoDB instance. For unit testing the heartbeat module itself,
see tests/services/test_heartbeat.py.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from crypto_news_aggregator.main import app


def test_health_endpoint_includes_pipeline_checks():
    """Test health endpoint includes pipeline heartbeat checks in response."""
    client = TestClient(app)

    # Just verify the endpoint is accessible and returns valid JSON
    # Full testing requires actual MongoDB connection
    response = client.get("/api/v1/health")

    assert response.status_code in [200, 500]  # May be 500 if pipeline is stale
    data = response.json()
    assert "checks" in data
    # Pipeline checks should be present
    assert "pipeline" in data["checks"]
