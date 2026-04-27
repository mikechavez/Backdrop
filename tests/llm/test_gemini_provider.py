"""Tests for GeminiProvider implementation."""

import os
import pytest
from unittest import mock

from crypto_news_aggregator.llm.gemini import GeminiProvider
from crypto_news_aggregator.llm.factory import get_llm_provider, PROVIDER_MAP
from crypto_news_aggregator.core.config import Settings


class TestGeminiProviderInstantiation:
    """Test GeminiProvider instantiation."""

    def test_gemini_provider_instantiation(self):
        """GeminiProvider instantiates with valid API key."""
        provider = GeminiProvider(api_key="test_key_12345")
        assert provider.api_key == "test_key_12345"
        assert provider.provider_name == "gemini"

    def test_gemini_provider_rejects_empty_key(self):
        """GeminiProvider raises ValueError if API key is empty."""
        with pytest.raises(ValueError, match="GEMINI_API_KEY must be set"):
            GeminiProvider(api_key="")

    def test_gemini_provider_rejects_none_key(self):
        """GeminiProvider raises ValueError if API key is None."""
        with pytest.raises(ValueError, match="GEMINI_API_KEY must be set"):
            GeminiProvider(api_key=None)


class TestGeminiProviderNotImplemented:
    """Test that GeminiProvider methods raise NotImplementedError."""

    def test_gemini_provider_analyze_sentiment_not_implemented(self):
        """GeminiProvider.analyze_sentiment() raises NotImplementedError."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.analyze_sentiment("test text")

    def test_gemini_provider_extract_themes_not_implemented(self):
        """GeminiProvider.extract_themes() raises NotImplementedError."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.extract_themes(["test text"])

    def test_gemini_provider_generate_insight_not_implemented(self):
        """GeminiProvider.generate_insight() raises NotImplementedError."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.generate_insight({"sentiment": 0.5})

    def test_gemini_provider_score_relevance_not_implemented(self):
        """GeminiProvider.score_relevance() raises NotImplementedError."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.score_relevance("test text")

    def test_gemini_provider_extract_entities_batch_not_implemented(self):
        """GeminiProvider.extract_entities_batch() raises NotImplementedError."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.extract_entities_batch([{"id": "1", "title": "test", "text": "test"}])

    def test_gemini_provider_call_not_implemented(self):
        """GeminiProvider.call() raises NotImplementedError with clear message."""
        provider = GeminiProvider(api_key="test_key")
        with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
            provider.call(
                model="gemini-2.5-flash",
                prompt="test",
                messages=[]
            )


class TestFactoryGeminiIntegration:
    """Test factory integration with GeminiProvider."""

    def test_provider_map_includes_gemini(self):
        """PROVIDER_MAP includes "gemini" key."""
        assert "gemini" in PROVIDER_MAP
        assert PROVIDER_MAP["gemini"] == GeminiProvider

    def test_factory_gemini_provider_instantiation(self):
        """factory.get_llm_provider("gemini") returns GeminiProvider instance."""
        with mock.patch("crypto_news_aggregator.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.GEMINI_API_KEY = "test_key"
            provider = get_llm_provider("gemini")
            assert isinstance(provider, GeminiProvider)
            assert provider.api_key == "test_key"

    def test_factory_gemini_provider_no_key(self):
        """factory.get_llm_provider("gemini") raises if GEMINI_API_KEY not set."""
        with mock.patch("crypto_news_aggregator.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.GEMINI_API_KEY = None
            with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
                get_llm_provider("gemini")

    def test_factory_gemini_provider_case_insensitive(self):
        """factory.get_llm_provider("GEMINI") works (case insensitive)."""
        with mock.patch("crypto_news_aggregator.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.GEMINI_API_KEY = "test_key"
            provider = get_llm_provider("GEMINI")
            assert isinstance(provider, GeminiProvider)
            assert provider.api_key == "test_key"


class TestConfigGeminiApiKey:
    """Test configuration loading of GEMINI_API_KEY."""

    def test_config_gemini_api_key_loaded(self):
        """config.Settings loads GEMINI_API_KEY from env."""
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "env_key_abc"}):
            settings = Settings()
            assert settings.GEMINI_API_KEY == "env_key_abc"

    def test_config_gemini_api_key_optional_default(self):
        """config.Settings defaults GEMINI_API_KEY to None when not set."""
        # Ensure GEMINI_API_KEY is not in environment
        with mock.patch.dict(os.environ, {}, clear=False):
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
            settings = Settings()
            assert settings.GEMINI_API_KEY is None
