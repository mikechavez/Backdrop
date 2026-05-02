"""
Tests for LLM Gateway — single entry point for all Anthropic API calls.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, call
from datetime import datetime, timezone

from src.crypto_news_aggregator.llm.gateway import (
    LLMGateway,
    GatewayResponse,
    get_gateway,
)
from src.crypto_news_aggregator.llm.exceptions import LLMError


class TestGatewayResponse:
    """Test GatewayResponse dataclass."""

    def test_gateway_response_creation(self):
        """Test creating a GatewayResponse."""
        response = GatewayResponse(
            text="Hello world",
            input_tokens=10,
            output_tokens=20,
            cost=0.05,
            model="claude-sonnet-4-5-20250929",
            operation="test_operation",
            trace_id="trace-123",
        )
        assert response.text == "Hello world"
        assert response.input_tokens == 10
        assert response.output_tokens == 20
        assert response.cost == 0.05
        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.operation == "test_operation"
        assert response.trace_id == "trace-123"


class TestLLMGatewayInit:
    """Test LLMGateway initialization."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_init_with_env_key(self, mock_settings):
        """Test initialization with API key from settings."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key-123"
        gateway = LLMGateway()
        assert gateway.api_key == "test-key-123"

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_init_with_provided_key(self, mock_settings):
        """Test initialization with provided API key."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "env-key"
        gateway = LLMGateway(api_key="provided-key")
        assert gateway.api_key == "provided-key"

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_init_no_key_raises_error(self, mock_settings):
        """Test initialization without API key raises ValueError."""
        mock_settings.return_value.ANTHROPIC_API_KEY = None
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
            LLMGateway()


class TestBudgetCheck:
    """Test budget checking in the gateway."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    def test_budget_check_allowed(self, mock_budget_check, mock_settings):
        """Test budget check when operation is allowed."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (True, "ok")

        gateway = LLMGateway()
        # Should not raise
        gateway._check_budget("test_operation")
        mock_budget_check.assert_called_once_with("test_operation")

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    def test_budget_check_blocked_hard_limit(self, mock_budget_check, mock_settings):
        """Test budget check when hard limit is reached."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (False, "hard_limit")

        gateway = LLMGateway()
        with pytest.raises(LLMError) as exc_info:
            gateway._check_budget("test_operation")

        assert exc_info.value.error_type == "spend_limit"
        assert "hard_limit" in str(exc_info.value)

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    def test_budget_check_blocked_soft_limit(self, mock_budget_check, mock_settings):
        """Test budget check when soft limit is reached."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (False, "soft_limit")

        gateway = LLMGateway()
        with pytest.raises(LLMError) as exc_info:
            gateway._check_budget("non_critical_operation")

        assert exc_info.value.error_type == "spend_limit"
        assert "soft_limit" in str(exc_info.value)


class TestHeadersAndPayload:
    """Test header and payload building."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_build_headers(self, mock_settings):
        """Test building API headers."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        gateway = LLMGateway()

        headers = gateway._build_headers()
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_build_payload_with_system(self, mock_settings):
        """Test building payload with system prompt."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        gateway = LLMGateway()

        messages = [{"role": "user", "content": "Hello"}]
        payload = gateway._build_payload(
            messages=messages,
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            temperature=0.5,
            system="You are helpful.",
        )

        assert payload["model"] == "claude-sonnet-4-5-20250929"
        assert payload["max_tokens"] == 1024
        assert payload["temperature"] == 0.5
        assert payload["system"] == "You are helpful."
        assert payload["messages"] == messages

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_build_payload_without_system(self, mock_settings):
        """Test building payload without system prompt."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        gateway = LLMGateway()

        messages = [{"role": "user", "content": "Hello"}]
        payload = gateway._build_payload(
            messages=messages,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            temperature=0.3,
            system=None,
        )

        assert "system" not in payload
        assert payload["model"] == "claude-haiku-4-5-20251001"


class TestParseResponse:
    """Test response parsing."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_parse_response_valid(self, mock_settings):
        """Test parsing a valid API response."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        gateway = LLMGateway()

        data = {
            "content": [{"type": "text", "text": "Hello world"}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }

        text, input_tokens, output_tokens = gateway._parse_response(data)
        assert text == "Hello world"
        assert input_tokens == 10
        assert output_tokens == 20

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_parse_response_missing_fields(self, mock_settings):
        """Test parsing response with missing fields."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        gateway = LLMGateway()

        data = {}
        text, input_tokens, output_tokens = gateway._parse_response(data)
        assert text == ""
        assert input_tokens == 0
        assert output_tokens == 0


class TestAsyncCall:
    """Test async call method."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    @patch("src.crypto_news_aggregator.llm.gateway.httpx.AsyncClient")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_call_success(
        self, mock_mongo, mock_client, mock_budget_check, mock_refresh, mock_settings
    ):
        """Test successful async call."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (True, "ok")
        mock_refresh = AsyncMock()

        # Mock HTTP response - json() is synchronous in httpx
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Test response"}],
            "usage": {"input_tokens": 5, "output_tokens": 10},
        }
        mock_response.raise_for_status.return_value = None

        # Mock the AsyncClient context manager
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock MongoDB
        mock_db = AsyncMock()
        mock_db.llm_cache.find_one = AsyncMock(return_value=None)  # Cache miss
        mock_db.llm_cache.update_one = AsyncMock()  # Cache save
        mock_db.llm_traces.insert_one = AsyncMock()
        mock_mongo.get_async_database.return_value = mock_db

        gateway = LLMGateway()
        response = await gateway.call(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-sonnet-4-5-20250929",
            operation="test_operation",
        )

        # Verify response contains expected fields (cost tracking may fail in test due to mocking)
        assert response.text == "Test response"
        assert response.input_tokens == 5
        assert response.output_tokens == 10
        assert response.operation == "test_operation"
        assert response.trace_id  # Should be populated
        # With routing strategy, model gets overridden from requested to actual
        assert response.requested_model == "claude-sonnet-4-5-20250929"
        assert response.actual_model == "anthropic:claude-haiku-4-5-20251001"
        assert response.model_overridden is True
        assert response.model == "anthropic:claude-haiku-4-5-20251001"  # actual_model used for call

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    async def test_call_budget_blocked(
        self, mock_budget_check, mock_refresh, mock_settings
    ):
        """Test async call blocked by budget."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (False, "hard_limit")
        mock_refresh.return_value = None

        gateway = LLMGateway()
        with pytest.raises(LLMError) as exc_info:
            await gateway.call(
                messages=[{"role": "user", "content": "Test"}],
                model="claude-sonnet-4-5-20250929",
                operation="test_operation",
            )

        assert exc_info.value.error_type == "spend_limit"

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    @patch("src.crypto_news_aggregator.llm.gateway.httpx.AsyncClient")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_call_api_error_403(
        self, mock_mongo, mock_client, mock_budget_check, mock_refresh, mock_settings
    ):
        """Test async call with 403 auth error."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (True, "ok")
        mock_refresh = AsyncMock()

        # Mock HTTP 403 error response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Unauthorized"

        import httpx as httpx_module
        error = httpx_module.HTTPStatusError("403 Forbidden", request=None, response=mock_response)

        # Mock the AsyncClient context manager to raise the error
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = error
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock MongoDB for trace write
        mock_db = AsyncMock()
        mock_mongo.get_async_database.return_value = mock_db

        with patch(
            "src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale",
            mock_refresh,
        ):
            gateway = LLMGateway()
            with pytest.raises(LLMError) as exc_info:
                await gateway.call(
                    messages=[{"role": "user", "content": "Test"}],
                    model="claude-sonnet-4-5-20250929",
                    operation="test_operation",
                )

            assert exc_info.value.error_type == "auth_error"
            assert exc_info.value.status_code == 403


class TestSyncCall:
    """Test sync call method."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    @patch("src.crypto_news_aggregator.llm.gateway.httpx.Client")
    def test_call_sync_success(self, mock_client, mock_budget_check, mock_settings):
        """Test successful sync call."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (True, "ok")

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Sync response"}],
            "usage": {"input_tokens": 8, "output_tokens": 12},
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        gateway = LLMGateway()
        response = gateway.call_sync(
            messages=[{"role": "user", "content": "Test"}],
            model="claude-haiku-4-5-20251001",
            operation="sync_operation",
        )

        assert response.text == "Sync response"
        assert response.input_tokens == 8
        assert response.output_tokens == 12
        assert response.operation == "sync_operation"
        # With routing strategy, model gets routed to actual (default Haiku for unknown operations)
        assert response.requested_model == "claude-haiku-4-5-20251001"
        assert response.actual_model == "anthropic:claude-haiku-4-5-20251001"
        assert response.model_overridden is True  # String differs (provider prefix added)
        assert response.model == "anthropic:claude-haiku-4-5-20251001"

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    def test_call_sync_budget_blocked(self, mock_budget_check, mock_settings):
        """Test sync call blocked by budget."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (False, "soft_limit")

        gateway = LLMGateway()
        with pytest.raises(LLMError) as exc_info:
            gateway.call_sync(
                messages=[{"role": "user", "content": "Test"}],
                model="claude-sonnet-4-5-20250929",
                operation="sync_operation",
            )

        assert exc_info.value.error_type == "spend_limit"


class TestCacheMethods:
    """Test cache methods for async calls."""

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_get_from_cache_hit(self, mock_mongo, mock_settings):
        """Test cache hit on get_from_cache."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

        # Mock MongoDB - cache hit
        mock_db = AsyncMock()
        mock_db.llm_cache.find_one = AsyncMock(
            return_value={
                "_id": "cache-id-1",
                "cached_response": "Cached result",
                "cached_count": 3,
            }
        )
        mock_db.llm_cache.update_one = AsyncMock()

        async def mock_get_db():
            return mock_db
        mock_mongo.get_async_database = mock_get_db

        gateway = LLMGateway()
        result = await gateway._get_from_cache("narrative_generate", "hash-abc123")

        assert result == "Cached result"
        mock_db.llm_cache.update_one.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_get_from_cache_miss(self, mock_mongo, mock_settings):
        """Test cache miss on get_from_cache."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

        # Mock MongoDB - cache miss
        mock_db = AsyncMock()
        mock_db.llm_cache.find_one = AsyncMock(return_value=None)

        async def mock_get_db():
            return mock_db
        mock_mongo.get_async_database = mock_get_db

        gateway = LLMGateway()
        result = await gateway._get_from_cache("narrative_generate", "hash-unknown")

        assert result is None

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_save_to_cache(self, mock_mongo, mock_settings):
        """Test saving response to cache."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

        # Mock MongoDB
        mock_db = AsyncMock()
        mock_db.llm_cache.update_one = AsyncMock()

        async def mock_get_db():
            return mock_db
        mock_mongo.get_async_database = mock_get_db

        gateway = LLMGateway()
        await gateway._save_to_cache("narrative_generate", "hash-abc123", "Test response")

        mock_db.llm_cache.update_one.assert_called_once()
        call_args = mock_db.llm_cache.update_one.call_args
        assert call_args[1]["upsert"] is True

    @pytest.mark.asyncio
    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    @patch("src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale")
    @patch("src.crypto_news_aggregator.llm.gateway.check_llm_budget")
    @patch("src.crypto_news_aggregator.llm.gateway.mongo_manager")
    async def test_call_cache_hit(
        self, mock_mongo, mock_budget_check, mock_refresh, mock_settings
    ):
        """Test async call returns cached result without API call."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"
        mock_budget_check.return_value = (True, "ok")
        mock_refresh = AsyncMock()

        # Mock MongoDB - cache hit
        mock_db = AsyncMock()
        mock_db.llm_cache.find_one = AsyncMock(
            return_value={
                "_id": "cache-id-1",
                "cached_response": "Cached test response",
                "cached_count": 2,
            }
        )
        mock_db.llm_cache.update_one = AsyncMock()
        mock_db.llm_traces.insert_one = AsyncMock()

        async def mock_get_db():
            return mock_db
        mock_mongo.get_async_database = mock_get_db

        with patch(
            "src.crypto_news_aggregator.llm.gateway.refresh_budget_if_stale",
            mock_refresh,
        ):
            gateway = LLMGateway()
            response = await gateway.call(
                messages=[{"role": "user", "content": "Test"}],
                model="claude-haiku-4-5-20251001",
                operation="narrative_generate",
            )

            assert response.text == "Cached test response"
            assert response.input_tokens == 0
            assert response.output_tokens == 0
            assert response.cost == 0.0
            assert response.provider == "anthropic"  # Regression check for BUG-092
            assert response.cached is True


class TestSingleton:
    """Test module-level singleton."""

    @patch("src.crypto_news_aggregator.llm.gateway.get_settings")
    def test_get_gateway_singleton(self, mock_settings):
        """Test that get_gateway returns the same instance."""
        mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

        # Import fresh to reset the module
        import src.crypto_news_aggregator.llm.gateway as gateway_module
        gateway_module._gateway = None

        gateway1 = gateway_module.get_gateway()
        gateway2 = gateway_module.get_gateway()

        assert gateway1 is gateway2
