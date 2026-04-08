"""
Tests for TASK-039: Wire health.py Through LLM Gateway

Verifies that health.py check_llm() calls the gateway instead of making
direct httpx requests, and handles spend cap gracefully.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from crypto_news_aggregator.api.v1.health import check_llm
from crypto_news_aggregator.llm.exceptions import LLMError
from crypto_news_aggregator.llm.gateway import GatewayResponse


@pytest.mark.asyncio
async def test_health_check_calls_gateway():
    """Verify check_llm() calls gateway.call() with correct parameters."""
    mock_response = GatewayResponse(
        text="ok",
        input_tokens=1,
        output_tokens=1,
        cost=0.00001,
        model="claude-haiku-4-5-20251001",
        operation="health_check",
        trace_id="test-trace-id",
    )

    with patch("crypto_news_aggregator.api.v1.health.get_gateway") as mock_get_gateway:
        mock_gateway = AsyncMock()
        mock_gateway.call = AsyncMock(return_value=mock_response)
        mock_get_gateway.return_value = mock_gateway

        result = await check_llm()

        # Verify gateway.call was invoked with correct parameters
        mock_gateway.call.assert_called_once()
        call_kwargs = mock_gateway.call.call_args.kwargs
        assert call_kwargs["operation"] == "health_check"
        assert call_kwargs["max_tokens"] == 1
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["messages"] == [{"role": "user", "content": "ok"}]

        # Verify response format
        assert result["status"] == "ok"
        assert "model" in result
        assert "latency_ms" in result


@pytest.mark.asyncio
async def test_health_check_spend_cap_returns_degraded():
    """Verify spend_limit error returns degraded status, not error."""
    spend_limit_error = LLMError(
        "Daily spend limit reached (soft)",
        error_type="spend_limit",
        model="claude-haiku-4-5-20251001",
    )

    with patch("crypto_news_aggregator.api.v1.health.get_gateway") as mock_get_gateway:
        mock_gateway = AsyncMock()
        mock_gateway.call = AsyncMock(side_effect=spend_limit_error)
        mock_get_gateway.return_value = mock_gateway

        result = await check_llm()

        # Verify degraded status is returned (not error)
        assert result["status"] == "degraded"
        assert result["reason"] == "spend_cap"
        assert "model" in result
        assert "latency_ms" in result


@pytest.mark.asyncio
async def test_health_check_api_error_returns_error():
    """Verify other LLMError types return error status."""
    server_error = LLMError(
        "Internal server error",
        error_type="server_error",
        model="claude-haiku-4-5-20251001",
    )

    with patch("crypto_news_aggregator.api.v1.health.get_gateway") as mock_get_gateway:
        mock_gateway = AsyncMock()
        mock_gateway.call = AsyncMock(side_effect=server_error)
        mock_get_gateway.return_value = mock_gateway

        result = await check_llm()

        # Verify error status is returned for non-spend_limit errors
        assert result["status"] == "error"
        assert "model" in result
        assert "latency_ms" in result
        assert "error" in result


@pytest.mark.asyncio
async def test_health_check_unexpected_exception_returns_error():
    """Verify unexpected exceptions return error status."""
    with patch("crypto_news_aggregator.api.v1.health.get_gateway") as mock_get_gateway:
        mock_gateway = AsyncMock()
        mock_gateway.call = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        mock_get_gateway.return_value = mock_gateway

        result = await check_llm()

        # Verify error status is returned
        assert result["status"] == "error"
        assert "model" in result
        assert "latency_ms" in result
        assert "error" in result
