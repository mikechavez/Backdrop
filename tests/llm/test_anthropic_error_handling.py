"""Tests for anthropic.py error handling using pytest-httpx."""

import pytest
import httpx
from unittest.mock import Mock, patch

from crypto_news_aggregator.llm.anthropic import AnthropicProvider
from crypto_news_aggregator.llm.exceptions import LLMError


class TestAnthropicErrorHandling:
    """Test AnthropicProvider error handling."""

    @pytest.fixture
    def provider(self):
        """Create an AnthropicProvider instance for testing."""
        return AnthropicProvider(api_key="test-key")

    def test_get_completion_timeout_raises_llm_error(self, provider):
        """_get_completion should raise LLMError on timeout."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = (
                httpx.TimeoutException("Request timed out")
            )

            with pytest.raises(LLMError) as exc_info:
                provider._get_completion("test prompt")

            error = exc_info.value
            assert error.error_type == "timeout"
            assert error.model == provider.model_name
            assert "timed out" in str(error).lower()

    def test_get_completion_403_raises_auth_error(self, provider):
        """_get_completion should raise LLMError with auth_error on 403."""
        with patch("httpx.Client") as mock_client:
            response = Mock(spec=httpx.Response)
            response.status_code = 403
            response.json.return_value = {"error": {"message": "Invalid API key"}}
            response.text = '{"error": {"message": "Invalid API key"}}'

            # Create actual HTTPStatusError
            error = httpx.HTTPStatusError("403", request=Mock(), response=response)
            mock_client.return_value.__enter__.return_value.post.side_effect = error

            with pytest.raises(LLMError) as exc_info:
                provider._get_completion("test prompt")

            llm_error = exc_info.value
            assert llm_error.error_type == "auth_error"
            assert llm_error.status_code == 403
            assert llm_error.model == provider.model_name

    def test_get_completion_429_raises_rate_limit(self, provider):
        """_get_completion should raise LLMError with rate_limit on 429."""
        with patch("httpx.Client") as mock_client:
            response = Mock(spec=httpx.Response)
            response.status_code = 429
            response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
            response.text = '{"error": {"message": "Rate limit exceeded"}}'

            error = httpx.HTTPStatusError("429", request=Mock(), response=response)
            mock_client.return_value.__enter__.return_value.post.side_effect = error

            with pytest.raises(LLMError) as exc_info:
                provider._get_completion("test prompt")

            llm_error = exc_info.value
            assert llm_error.error_type == "rate_limit"
            assert llm_error.status_code == 429

    def test_get_completion_500_raises_server_error(self, provider):
        """_get_completion should raise LLMError with server_error on 5xx."""
        with patch("httpx.Client") as mock_client:
            response = Mock(spec=httpx.Response)
            response.status_code = 500
            response.json.return_value = {"error": {"message": "Internal server error"}}
            response.text = '{"error": {"message": "Internal server error"}}'

            error = httpx.HTTPStatusError("500", request=Mock(), response=response)
            mock_client.return_value.__enter__.return_value.post.side_effect = error

            with pytest.raises(LLMError) as exc_info:
                provider._get_completion("test prompt")

            llm_error = exc_info.value
            assert llm_error.error_type == "server_error"
            assert llm_error.status_code == 500

    def test_get_completion_happy_path(self, provider):
        """_get_completion should return text on success."""
        with patch("httpx.Client") as mock_client:
            response = Mock()
            response.json.return_value = {"content": [{"text": "test response"}]}
            response.status_code = 200

            mock_client.return_value.__enter__.return_value.post.return_value = response

            result = provider._get_completion("test prompt")

            assert result == "test response"

    def test_get_completion_with_usage_timeout(self, provider):
        """_get_completion_with_usage should raise LLMError on timeout."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = (
                httpx.TimeoutException("Request timed out")
            )

            with pytest.raises(LLMError) as exc_info:
                provider._get_completion_with_usage("test prompt")

            error = exc_info.value
            assert error.error_type == "timeout"

    def test_get_completion_with_usage_happy_path(self, provider):
        """_get_completion_with_usage should return text and usage on success."""
        with patch("httpx.Client") as mock_client:
            response = Mock()
            response.json.return_value = {
                "content": [{"text": "test response"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

            mock_client.return_value.__enter__.return_value.post.return_value = response

            text, usage = provider._get_completion_with_usage("test prompt")

            assert text == "test response"
            assert usage == {"input_tokens": 10, "output_tokens": 5}

    def test_analyze_sentiment_llm_error_returns_zero(self, provider):
        """analyze_sentiment should return 0.0 on LLMError."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.side_effect = LLMError(
                "API error", error_type="server_error"
            )

            result = provider.analyze_sentiment("test text")

            assert result == 0.0

    def test_analyze_sentiment_happy_path(self, provider):
        """analyze_sentiment should extract float from response."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.return_value = "0.75"

            result = provider.analyze_sentiment("test text")

            assert result == 0.75

    def test_score_relevance_llm_error_returns_zero(self, provider):
        """score_relevance should return 0.0 on LLMError."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.side_effect = LLMError(
                "API error", error_type="timeout"
            )

            result = provider.score_relevance("test text")

            assert result == 0.0

    def test_score_relevance_happy_path(self, provider):
        """score_relevance should extract float from response."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.return_value = "0.85"

            result = provider.score_relevance("test text")

            assert result == 0.85

    def test_extract_themes_llm_error_returns_empty_list(self, provider):
        """extract_themes should return [] on LLMError."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.side_effect = LLMError(
                "API error", error_type="auth_error"
            )

            result = provider.extract_themes(["text1", "text2"])

            assert result == []

    def test_extract_themes_happy_path(self, provider):
        """extract_themes should split and strip response."""
        with patch.object(provider, "_get_completion") as mock_get:
            mock_get.return_value = "Bitcoin, DeFi, Regulation"

            result = provider.extract_themes(["text1", "text2"])

            assert result == ["Bitcoin", "DeFi", "Regulation"]
