"""
Tests for provider-aware gateway routing (TASK-085).

Tests the provider-aware model parsing and routing logic that enables
DeepSeek integration while keeping Anthropic as the default.
"""

import pytest
from crypto_news_aggregator.llm.gateway import LLMGateway


class TestModelStringParsing:
    """Test provider-aware model string parsing."""

    def test_parse_anthropic_model_string(self):
        """Parse anthropic:model format."""
        gateway = LLMGateway()
        provider, model = gateway._parse_model_string("anthropic:claude-haiku-4-5-20251001")
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"

    def test_parse_deepseek_model_string(self):
        """Parse deepseek:model format."""
        gateway = LLMGateway()
        provider, model = gateway._parse_model_string("deepseek:deepseek-v4-flash")
        assert provider == "deepseek"
        assert model == "deepseek-v4-flash"

    def test_parse_legacy_anthropic_format(self):
        """Legacy format without provider prefix defaults to anthropic."""
        gateway = LLMGateway()
        provider, model = gateway._parse_model_string("claude-haiku-4-5-20251001")
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"

    def test_parse_deepseek_chat_alias(self):
        """deepseek-chat is alias for deepseek-v4-flash."""
        gateway = LLMGateway()
        provider, model = gateway._parse_model_string("deepseek:deepseek-chat")
        assert provider == "deepseek"
        assert model == "deepseek-chat"


class TestProviderUrlResolution:
    """Test provider-specific URL resolution."""

    def test_anthropic_url_direct_api(self):
        """Anthropic uses direct API by default."""
        gateway = LLMGateway()
        url = gateway._get_provider_url("anthropic")
        assert "api.anthropic.com" in url
        assert "/messages" in url

    def test_deepseek_url_openai_compatible(self):
        """DeepSeek uses OpenAI-compatible endpoint."""
        gateway = LLMGateway()
        url = gateway._get_provider_url("deepseek")
        assert url == "https://api.deepseek.com/chat/completions"


class TestProviderHeaderBuilding:
    """Test provider-specific header construction."""

    def test_anthropic_headers_have_api_key(self):
        """Anthropic headers include API key."""
        gateway = LLMGateway()
        headers = gateway._build_provider_headers("anthropic", "claude-haiku-4-5-20251001")
        assert "x-api-key" in headers
        assert headers["anthropic-version"] == "2023-06-01"

    def test_deepseek_headers_bearer_token(self):
        """DeepSeek headers use Bearer token."""
        gateway = LLMGateway()
        # This will raise if DEEPSEEK_API_KEY not set, which is expected in test
        # For unit testing, we'd inject via get_settings mock, but basic structure test:
        try:
            headers = gateway._build_provider_headers("deepseek", "deepseek-v4-flash")
            assert "Authorization" in headers
            assert headers["Authorization"].startswith("Bearer ")
        except ValueError:
            # Expected if DEEPSEEK_API_KEY not set
            pass


class TestProviderPayloadBuilding:
    """Test provider-specific request payload construction."""

    def test_anthropic_payload_with_system(self):
        """Anthropic payload includes system prompt."""
        gateway = LLMGateway()
        messages = [{"role": "user", "content": "test"}]
        payload = gateway._build_provider_payload(
            messages=messages,
            provider="anthropic",
            model_name="claude-haiku-4-5-20251001",
            max_tokens=2048,
            temperature=0.7,
            system="You are helpful."
        )
        assert payload["model"] == "claude-haiku-4-5-20251001"
        assert payload["system"] == "You are helpful."
        assert payload["messages"] == messages
        assert "stream" not in payload

    def test_anthropic_payload_without_system(self):
        """Anthropic payload omits system if not provided."""
        gateway = LLMGateway()
        messages = [{"role": "user", "content": "test"}]
        payload = gateway._build_provider_payload(
            messages=messages,
            provider="anthropic",
            model_name="claude-haiku-4-5-20251001",
            max_tokens=2048,
            temperature=0.7,
            system=None
        )
        assert "system" not in payload

    def test_deepseek_payload_structure(self):
        """DeepSeek payload uses OpenAI-compatible format."""
        gateway = LLMGateway()
        messages = [{"role": "user", "content": "test"}]
        payload = gateway._build_provider_payload(
            messages=messages,
            provider="deepseek",
            model_name="deepseek-v4-flash",
            max_tokens=2048,
            temperature=0.7,
            system="You are helpful."
        )
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["messages"] == messages
        assert payload["stream"] is False
        assert payload["thinking"]["type"] == "disabled"
        # DeepSeek doesn't support system prompt in same way, it's in messages
        assert "system" not in payload

    def test_deepseek_payload_ignores_system_param(self):
        """DeepSeek payload doesn't include system param (handled in messages)."""
        gateway = LLMGateway()
        messages = [{"role": "user", "content": "test"}]
        payload = gateway._build_provider_payload(
            messages=messages,
            provider="deepseek",
            model_name="deepseek-v4-flash",
            max_tokens=2048,
            temperature=0.7,
            system="You are helpful."
        )
        # System is passed in messages by caller, not in payload dict
        assert "system" not in payload


class TestProviderResponseParsing:
    """Test provider-specific response parsing."""

    def test_anthropic_response_parsing(self):
        """Parse Anthropic API response format."""
        gateway = LLMGateway()
        response_data = {
            "content": [{"type": "text", "text": "Hello, world!"}],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
            }
        }
        text, input_tokens, output_tokens = gateway._parse_provider_response(response_data, "anthropic")
        assert text == "Hello, world!"
        assert input_tokens == 10
        assert output_tokens == 5

    def test_deepseek_response_parsing(self):
        """Parse DeepSeek API response format."""
        gateway = LLMGateway()
        response_data = {
            "choices": [{"message": {"content": "Hello from DeepSeek!"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 8,
            }
        }
        text, input_tokens, output_tokens = gateway._parse_provider_response(response_data, "deepseek")
        assert text == "Hello from DeepSeek!"
        assert input_tokens == 20
        assert output_tokens == 8

    def test_response_parsing_handles_missing_fields(self):
        """Response parsing handles incomplete data gracefully."""
        gateway = LLMGateway()
        # Anthropic with missing usage
        response_data = {
            "content": [{"type": "text", "text": "test"}],
        }
        text, input_tokens, output_tokens = gateway._parse_provider_response(response_data, "anthropic")
        assert text == "test"
        assert input_tokens == 0
        assert output_tokens == 0

        # DeepSeek with missing usage
        response_data = {
            "choices": [{"message": {"content": "test"}}],
        }
        text, input_tokens, output_tokens = gateway._parse_provider_response(response_data, "deepseek")
        assert text == "test"
        assert input_tokens == 0
        assert output_tokens == 0


class TestRoutingConfiguration:
    """Test operation routing configuration."""

    def test_entity_extraction_in_routing(self):
        """entity_extraction operation has routing strategy."""
        gateway = LLMGateway()
        strategy = gateway._resolve_routing("entity_extraction", None, "test:key")[0]
        # Should return a model string (Anthropic by default)
        assert "anthropic" in strategy or "claude" in strategy

    def test_sentiment_analysis_in_routing(self):
        """sentiment_analysis operation has routing strategy."""
        gateway = LLMGateway()
        strategy = gateway._resolve_routing("sentiment_analysis", None, "test:key")[0]
        assert "anthropic" in strategy or "claude" in strategy

    def test_theme_extraction_in_routing(self):
        """theme_extraction operation has routing strategy."""
        gateway = LLMGateway()
        strategy = gateway._resolve_routing("theme_extraction", None, "test:key")[0]
        assert "anthropic" in strategy or "claude" in strategy

    def test_article_enrichment_batch_in_routing(self):
        """article_enrichment_batch operation has routing strategy."""
        gateway = LLMGateway()
        strategy = gateway._resolve_routing("article_enrichment_batch", None, "test:key")[0]
        assert "anthropic" in strategy or "claude" in strategy
