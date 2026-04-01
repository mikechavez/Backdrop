"""Unit tests for health endpoint logic."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta


# --- Overall status logic tests ---


class TestHealthStatusLogic:
    """Test the overall status determination: healthy / degraded / unhealthy."""

    def _compute_status(self, checks: dict) -> str:
        """Mirror the logic from the health endpoint."""
        CRITICAL = {"database", "llm"}
        critical_failed = any(
            checks[name]["status"] == "error"
            for name in CRITICAL
            if name in checks
        )
        any_issue = any(
            checks[name]["status"] in ("error", "warning")
            for name in checks
        )
        if critical_failed:
            return "unhealthy"
        elif any_issue:
            return "degraded"
        return "healthy"

    def test_all_ok_returns_healthy(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "healthy"

    def test_redis_error_returns_degraded(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "error"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "degraded"

    def test_data_freshness_warning_returns_degraded(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "warning"},
        }
        assert self._compute_status(checks) == "degraded"

    def test_database_error_returns_unhealthy(self):
        checks = {
            "database": {"status": "error"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "unhealthy"

    def test_llm_error_returns_unhealthy(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "error"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "unhealthy"

    def test_both_critical_fail_returns_unhealthy(self):
        checks = {
            "database": {"status": "error"},
            "redis": {"status": "error"},
            "llm": {"status": "error"},
            "data_freshness": {"status": "error"},
        }
        assert self._compute_status(checks) == "unhealthy"


# --- Individual check tests ---


class TestCheckDatabase:
    """Test database health check handles success and failure."""

    @pytest.mark.asyncio
    async def test_database_ok(self):
        from crypto_news_aggregator.api.v1.health import check_database

        mock_db = AsyncMock()
        mock_db.command = AsyncMock(return_value={"ok": 1})

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_database()

        assert result["status"] == "ok"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_database_error(self):
        from crypto_news_aggregator.api.v1.health import check_database

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            result = await check_database()

        assert result["status"] == "error"
        assert "error" in result


class TestCheckRedis:
    """Test Redis health check handles success and failure."""

    @pytest.mark.asyncio
    async def test_redis_ok(self):
        from crypto_news_aggregator.api.v1.health import check_redis

        with patch(
            "crypto_news_aggregator.api.v1.health.redis_client"
        ) as mock_redis:
            mock_redis.ping.return_value = True
            result = await check_redis()

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_redis_error(self):
        from crypto_news_aggregator.api.v1.health import check_redis

        with patch(
            "crypto_news_aggregator.api.v1.health.redis_client"
        ) as mock_redis:
            mock_redis.ping.side_effect = Exception("Connection refused")
            result = await check_redis()

        assert result["status"] == "error"


class TestCheckLLM:
    """Test LLM health check uses cheap model and handles failure."""

    @pytest.mark.asyncio
    async def test_llm_ok(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch(
            "crypto_news_aggregator.api.v1.health.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await check_llm()

        assert result["status"] == "ok"
        assert result["model"] == "claude-haiku-4-5-20251001"

        # Verify max_tokens=1 (cost control)
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 1

    @pytest.mark.asyncio
    async def test_llm_no_api_key(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        with patch(
            "crypto_news_aggregator.api.v1.health.get_settings"
        ) as mock_settings:
            mock_s = MagicMock()
            mock_s.ANTHROPIC_API_KEY = ""
            mock_settings.return_value = mock_s

            result = await check_llm()

        assert result["status"] == "error"
        assert "not set" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_timeout(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        with patch(
            "crypto_news_aggregator.api.v1.health.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await check_llm()

        assert result["status"] == "error"


class TestCheckDataFreshness:
    """Test data freshness check handles various states."""

    @pytest.mark.asyncio
    async def test_fresh_data(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"published_at": recent_time, "title": "Test Article"}
        )
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "ok"
        assert result["latest_article_age_hours"] < 24

    @pytest.mark.asyncio
    async def test_stale_data(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"published_at": old_time, "title": "Old Article"}
        )
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "warning"
        assert result["latest_article_age_hours"] > 24

    @pytest.mark.asyncio
    async def test_no_articles(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "warning"
