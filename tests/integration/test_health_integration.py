"""Integration tests for the /api/v1/health endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_all_healthy():
    """Patch all subsystem checks to return healthy."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 5.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 2.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


@pytest.fixture
def mock_database_down():
    """Patch database check to fail, others healthy."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "error", "latency_ms": 5000.0, "error": "Connection refused"},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 2.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


@pytest.fixture
def mock_redis_down():
    """Patch redis to fail, others healthy -- should produce degraded."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 5.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "error", "latency_ms": 5000.0, "error": "Connection refused"},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


class TestHealthEndpoint:
    """Integration tests for GET /api/v1/health."""

    @pytest.mark.asyncio
    async def test_healthy_response_structure(self, mock_all_healthy):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "checks" in data
        assert set(data["checks"].keys()) == {
            "database", "redis", "llm", "data_freshness"
        }

    @pytest.mark.asyncio
    async def test_unhealthy_when_database_down(self, mock_database_down):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_degraded_when_redis_down(self, mock_redis_down):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_auth_required(self, mock_all_healthy):
        """Health endpoint must work without any API key header."""
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Deliberately no X-API-Key header
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
