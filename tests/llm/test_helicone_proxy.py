"""
Tests for Helicone proxy configuration and URL switching (TASK-074).
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from crypto_news_aggregator.llm.gateway import LLMGateway
from crypto_news_aggregator.core.config import Settings


class TestHeliconeConfiguration:
    """Test Helicone configuration settings."""

    def test_helicone_settings_defaults(self):
        """Test that Helicone settings have sensible defaults."""
        with patch.dict(os.environ, {}, clear=False):
            settings = Settings()
            assert settings.USE_HELICONE_PROXY is False
            assert settings.HELICONE_API_KEY is None

    def test_helicone_settings_env_override(self):
        """Test that Helicone settings can be overridden via env vars."""
        with patch.dict(os.environ, {
            "USE_HELICONE_PROXY": "true",
            "HELICONE_API_KEY": "test-key-12345"
        }, clear=False):
            settings = Settings()
            assert settings.USE_HELICONE_PROXY is True
            assert settings.HELICONE_API_KEY == "test-key-12345"

    def test_helicone_proxy_disabled_by_default(self):
        """Test that proxy is disabled by default (safe default)."""
        settings = Settings()
        assert settings.USE_HELICONE_PROXY is False


class TestHeliconeURLSelection:
    """Test dynamic URL selection based on proxy configuration."""

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_get_anthropic_url_direct_api_when_disabled(self, mock_get_settings):
        """Test that direct Anthropic URL is used when proxy disabled."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = False
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")
        url = gateway._get_anthropic_url()

        assert url == "https://api.anthropic.com/v1/messages"

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_get_anthropic_url_helicone_when_enabled(self, mock_get_settings):
        """Test that Helicone URL is used when proxy enabled."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = True
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")
        url = gateway._get_anthropic_url()

        assert url == "https://api.helicone.ai/anthropic/v1/messages"

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_url_selection_on_runtime_toggle(self, mock_get_settings):
        """Test that URL switches correctly when proxy setting changes."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")

        # Start with proxy disabled
        mock_settings.USE_HELICONE_PROXY = False
        assert gateway._get_anthropic_url() == "https://api.anthropic.com/v1/messages"

        # Toggle proxy enabled
        mock_settings.USE_HELICONE_PROXY = True
        assert gateway._get_anthropic_url() == "https://api.helicone.ai/anthropic/v1/messages"

        # Toggle proxy disabled again
        mock_settings.USE_HELICONE_PROXY = False
        assert gateway._get_anthropic_url() == "https://api.anthropic.com/v1/messages"


class TestHeliconeHeaders:
    """Test Helicone authentication header construction."""

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_no_helicone_header_when_disabled(self, mock_get_settings):
        """Test that Helicone-Auth header is not added when proxy disabled."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = False
        mock_settings.HELICONE_API_KEY = "test-key"
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-anthropic-key")
        headers = gateway._build_headers()

        assert "Helicone-Auth" not in headers
        assert headers["x-api-key"] == "test-anthropic-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_helicone_header_when_enabled_with_key(self, mock_get_settings):
        """Test that Helicone-Auth header is added when proxy enabled and key provided."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = True
        mock_settings.HELICONE_API_KEY = "hc-test-key-12345"
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-anthropic-key")
        headers = gateway._build_headers()

        assert "Helicone-Auth" in headers
        assert headers["Helicone-Auth"] == "Bearer hc-test-key-12345"
        assert headers["x-api-key"] == "test-anthropic-key"

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_no_helicone_header_when_enabled_without_key(self, mock_get_settings):
        """Test that Helicone-Auth header is not added if proxy enabled but key missing."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = True
        mock_settings.HELICONE_API_KEY = None
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-anthropic-key")
        headers = gateway._build_headers()

        assert "Helicone-Auth" not in headers
        assert headers["x-api-key"] == "test-anthropic-key"

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_helicone_header_format(self, mock_get_settings):
        """Test that Helicone-Auth header uses correct Bearer token format."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = True
        mock_settings.HELICONE_API_KEY = "my-secret-key"
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")
        headers = gateway._build_headers()

        # Verify Bearer token format
        assert headers["Helicone-Auth"].startswith("Bearer ")
        assert headers["Helicone-Auth"] == "Bearer my-secret-key"


class TestHeliconeProxyToggling:
    """Test runtime toggling of Helicone proxy without code changes."""

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_proxy_toggle_url_switches(self, mock_get_settings):
        """Test that toggling USE_HELICONE_PROXY changes the URL used."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")

        # Verify proxy off → direct API
        mock_settings.USE_HELICONE_PROXY = False
        mock_settings.HELICONE_API_KEY = None
        url_1 = gateway._get_anthropic_url()
        assert "api.anthropic.com" in url_1

        # Verify proxy on → Helicone proxy
        mock_settings.USE_HELICONE_PROXY = True
        mock_settings.HELICONE_API_KEY = "key-123"
        url_2 = gateway._get_anthropic_url()
        assert "api.helicone.ai" in url_2

        # Verify they're different
        assert url_1 != url_2

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_proxy_toggle_headers_change(self, mock_get_settings):
        """Test that toggling proxy changes headers without restart."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")

        # Proxy off → no Helicone header
        mock_settings.USE_HELICONE_PROXY = False
        mock_settings.HELICONE_API_KEY = "key-123"
        headers_1 = gateway._build_headers()
        assert "Helicone-Auth" not in headers_1

        # Proxy on → Helicone header added
        mock_settings.USE_HELICONE_PROXY = True
        mock_settings.HELICONE_API_KEY = "key-123"
        headers_2 = gateway._build_headers()
        assert "Helicone-Auth" in headers_2

        # Both should have standard headers
        assert "x-api-key" in headers_1
        assert "x-api-key" in headers_2


class TestHeliconeBackwardCompatibility:
    """Test that Helicone configuration doesn't break existing behavior."""

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_existing_gateway_tests_unchanged(self, mock_get_settings):
        """Test that existing gateway behavior is unchanged with proxy disabled."""
        mock_settings = MagicMock()
        mock_settings.USE_HELICONE_PROXY = False
        mock_settings.HELICONE_API_KEY = None
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="test-key")

        # URL should be unchanged
        assert gateway._get_anthropic_url() == "https://api.anthropic.com/v1/messages"

        # Headers should have no Helicone additions
        headers = gateway._build_headers()
        assert "Helicone-Auth" not in headers
        assert len(headers) == 3  # x-api-key, anthropic-version, content-type

    @patch('crypto_news_aggregator.llm.gateway.get_settings')
    def test_proxy_disabled_default_behavior(self, mock_get_settings):
        """Test that default (proxy disabled) behavior is backward compatible."""
        mock_settings = MagicMock()
        # Explicitly test default values
        mock_settings.USE_HELICONE_PROXY = False
        mock_settings.HELICONE_API_KEY = None
        mock_get_settings.return_value = mock_settings

        gateway = LLMGateway(api_key="anthropic-key-test")
        url = gateway._get_anthropic_url()

        # Default should always use direct Anthropic API
        assert url == "https://api.anthropic.com/v1/messages"
