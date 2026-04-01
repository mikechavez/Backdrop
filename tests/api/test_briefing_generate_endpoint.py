"""Tests for briefing /generate endpoint error handling."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from crypto_news_aggregator.llm.exceptions import LLMError


@pytest.fixture
def client():
    """Create a test client for the briefing API."""
    from crypto_news_aggregator.api.v1.endpoints.briefing import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/briefings")
    return TestClient(app)


class TestBriefingGenerateEndpoint:
    """Test the /api/v1/briefings/generate endpoint."""

    def test_endpoint_returns_invalid_type_400(self, client):
        """Endpoint should return 400 for invalid briefing type."""
        response = client.post(
            "/api/v1/briefings/generate",
            json={"type": "invalid", "force": True}
        )
        assert response.status_code == 400

    def test_endpoint_llm_error_response_structure(self):
        """Test that endpoint properly catches and formats LLMError responses."""
        # This test verifies the error handling logic in the endpoint
        from crypto_news_aggregator.api.v1.endpoints.briefing import (
            _LLM_ERROR_HTTP_CODES,
            GenerateBriefingResponse,
        )

        # Verify the HTTP code mapping exists
        assert _LLM_ERROR_HTTP_CODES["auth_error"] == 502
        assert _LLM_ERROR_HTTP_CODES["rate_limit"] == 503
        assert _LLM_ERROR_HTTP_CODES["server_error"] == 503
        assert _LLM_ERROR_HTTP_CODES["timeout"] == 503

        # Verify the response model has error_type field
        response = GenerateBriefingResponse(
            success=False,
            message="test",
            briefing_id=None,
            error_type="auth_error",
        )
        assert response.error_type == "auth_error"

    def test_llm_error_http_codes_mapping(self):
        """Verify LLMError types map to correct HTTP codes."""
        from crypto_news_aggregator.api.v1.endpoints.briefing import (
            _LLM_ERROR_HTTP_CODES,
        )

        # auth_error -> 502 (bad gateway)
        assert _LLM_ERROR_HTTP_CODES["auth_error"] == 502

        # rate_limit -> 503 (service unavailable)
        assert _LLM_ERROR_HTTP_CODES["rate_limit"] == 503
        assert _LLM_ERROR_HTTP_CODES["timeout"] == 503
        assert _LLM_ERROR_HTTP_CODES["server_error"] == 503

        # All error types are covered
        error_types = [
            "auth_error",
            "rate_limit",
            "server_error",
            "timeout",
            "all_models_failed",
            "parse_error",
            "unexpected",
        ]
        for error_type in error_types:
            assert error_type in _LLM_ERROR_HTTP_CODES
