"""
Tests for the optimized LLM integration in RSS fetcher.

Tests verify:
1. Selective processor correctly decides LLM vs regex
2. Optimized LLM factory works correctly
3. RSS fetcher uses cost-optimized processing
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.crypto_news_aggregator.background import rss_fetcher
from src.crypto_news_aggregator.services.selective_processor import (
    SelectiveArticleProcessor,
    create_processor,
)
from src.crypto_news_aggregator.models.article import ArticleMetrics


class FakeLLMProvider:
    """Fake LLM provider for testing sentiment/relevance (not entity extraction)."""

    def __init__(self, relevance: float = 0.8, sentiment: float = 0.6, themes=None):
        self._relevance = relevance
        self._sentiment = sentiment
        self._themes = themes or ["Bitcoin", "Market"]

    def analyze_sentiment(self, text: str) -> float:
        return self._sentiment

    def extract_themes(self, texts):
        return self._themes

    def score_relevance(self, text: str) -> float:
        return self._relevance

    async def enrich_articles_batch(self, articles):
        """Batch enrich articles with relevance, sentiment, and themes."""
        results = []
        for article in articles:
            results.append({
                "id": article["id"],
                "relevance_score": self._relevance,
                "sentiment_score": self._sentiment,
                "themes": self._themes
            })
        return results

    def extract_entities_batch(self, articles):
        """Extract entities from batch of articles."""
        results = []
        for article in articles:
            results.append({
                "article_id": article.get("article_id"),
                "primary_entities": [],
                "context_entities": [],
                "sentiment": "neutral"
            })
        return {"results": results}


class FakeOptimizedLLM:
    """Fake optimized LLM for testing entity extraction."""
    
    HAIKU_MODEL = "claude-3-5-haiku-20241022"
    
    def __init__(self):
        self.extract_calls = []
    
    async def extract_entities_batch(self, articles):
        """Track calls and return mock entities."""
        self.extract_calls.append(articles)
        
        results = []
        for article in articles:
            title = article.get("title", "").lower()
            entities = []
            
            # Simple mock entity extraction
            if "bitcoin" in title or "btc" in title:
                entities.append({
                    "name": "Bitcoin",
                    "type": "cryptocurrency",
                    "confidence": 0.95,
                    "is_primary": True
                })
            if "ethereum" in title or "eth" in title:
                entities.append({
                    "name": "Ethereum",
                    "type": "cryptocurrency",
                    "confidence": 0.9,
                    "is_primary": False
                })
            
            results.append({"entities": entities})
        
        return results
    
    async def enrich_articles_batch(self, articles):
        """Mock enrichment batch call for testing."""
        results = []
        for article in articles:
            results.append({
                "id": article["id"],
                "relevance_score": 0.8,
                "sentiment_score": 0.5,
                "themes": ["Bitcoin", "Market"]
            })
        return results

    async def get_cache_stats(self):
        return {
            "active_entries": 10,
            "hit_rate_percent": 25.0,
            "total_requests": 100,
            "cache_hits": 25
        }

    async def get_cost_summary(self):
        return {
            "month_to_date": 0.50,
            "projected_monthly": 5.00,
            "total_calls": 100
        }


class TestSelectiveProcessor:
    """Tests for SelectiveArticleProcessor decision logic."""
    
    def test_premium_source_always_uses_llm(self):
        """Premium sources should always use LLM."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        premium_sources = ["coindesk", "cointelegraph", "decrypt", "theblock"]
        for source in premium_sources:
            article = {"source": source, "title": "Some article title"}
            assert processor.should_use_llm(article) is True, f"{source} should use LLM"
    
    def test_skip_llm_source_never_uses_llm(self):
        """Low-priority sources should never use LLM."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        skip_sources = ["bitcoinmagazine", "cryptoslate", "cryptopotato", "newsbtc"]
        for source in skip_sources:
            article = {"source": source, "title": "Bitcoin reaches new high"}
            assert processor.should_use_llm(article) is False, f"{source} should not use LLM"
    
    def test_mid_tier_with_important_keywords_uses_llm(self):
        """Mid-tier sources with important keywords should use LLM."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        # Unknown source with important keyword
        article = {"source": "unknown_source", "title": "SEC approves Bitcoin ETF"}
        assert processor.should_use_llm(article) is True
        
        article = {"source": "unknown_source", "title": "Major hack exploits DeFi protocol"}
        assert processor.should_use_llm(article) is True
    
    def test_mid_tier_without_keywords_skips_llm(self):
        """Mid-tier sources without important keywords should skip LLM."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        article = {"source": "unknown_source", "title": "Weekly newsletter update"}
        assert processor.should_use_llm(article) is False
    
    @pytest.mark.asyncio
    async def test_regex_extraction_finds_entities(self):
        """Regex extraction should find common crypto entities."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        article = {
            "title": "Bitcoin and Ethereum lead market rally",
            "text": "BTC surged 5% while ETH gained 3%. Solana also saw gains."
        }
        
        from bson import ObjectId
        article_id = ObjectId()
        
        entities = await processor.extract_entities_simple(article_id, article)
        
        entity_names = [e["entity"] for e in entities]
        assert "Bitcoin" in entity_names
        assert "Ethereum" in entity_names
        assert "Solana" in entity_names
    
    def test_processing_stats(self):
        """Should return correct processing statistics."""
        processor = SelectiveArticleProcessor(MagicMock())
        stats = processor.get_processing_stats()
        
        assert "premium_sources" in stats
        assert "skip_llm_sources" in stats
        assert "important_keywords_count" in stats
        assert "tracked_entities" in stats
        assert stats["expected_llm_percentage"] == "~50%"


class TestOptimizedLLMFactory:
    """Tests for the optimized LLM factory function."""
    
    @pytest.mark.asyncio
    async def test_get_optimized_llm_requires_api_key(self, mongo_db):
        """Should raise error if API key is not configured."""
        from src.crypto_news_aggregator.llm.factory import get_optimized_llm
        
        with patch("src.crypto_news_aggregator.llm.factory.get_settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY = ""
            
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
                await get_optimized_llm(mongo_db)


class TestRSSFetcherOptimizedIntegration:
    """Tests for RSS fetcher with optimized LLM integration."""
    
    @pytest.mark.asyncio
    async def test_process_articles_uses_selective_processing(self, mongo_db, monkeypatch):
        """Should use selective processing when optimized LLM is available."""
        # Mock the standard LLM provider
        monkeypatch.setattr(
            rss_fetcher,
            "get_llm_provider",
            lambda: FakeLLMProvider(themes=["Bitcoin", "ETF"]),
        )
        
        # Mock the optimized LLM
        fake_optimized_llm = FakeOptimizedLLM()
        
        async def mock_get_optimized_llm(db):
            return fake_optimized_llm
        
        monkeypatch.setattr(
            rss_fetcher,
            "get_optimized_llm",
            mock_get_optimized_llm,
        )
        
        # Clear and insert test articles
        await mongo_db.articles.delete_many({})
        
        # Premium source article (should use LLM)
        premium_article = {
            "title": "Bitcoin ETF sees record inflows",
            "source_id": "test-premium-1",
            "source": "coindesk",  # Premium source
            "text": "Bitcoin ETFs attracted $1B in inflows today.",
            "url": "https://example.com/btc-etf",
            "lang": "en",
            "metrics": ArticleMetrics().model_dump(),
            "keywords": [],
            "relevance_score": None,
            "sentiment_score": None,
            "sentiment_label": None,
            "raw_data": {},
            "published_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        # Low-priority source article (should use regex)
        low_priority_article = {
            "title": "Bitcoin price update",
            "source_id": "test-low-1",
            "source": "bitcoinmagazine",  # Skip LLM source
            "text": "Bitcoin traded at $50,000 today.",
            "url": "https://example.com/btc-price",
            "lang": "en",
            "metrics": ArticleMetrics().model_dump(),
            "keywords": [],
            "relevance_score": None,
            "sentiment_score": None,
            "sentiment_label": None,
            "raw_data": {},
            "published_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        await mongo_db.articles.insert_many([premium_article, low_priority_article])
        
        # Process articles
        await rss_fetcher.process_new_articles_from_mongodb()
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Verify LLM was called for premium source
        assert len(fake_optimized_llm.extract_calls) >= 1, "LLM should be called for premium source"
        
        # Verify articles were enriched
        premium_stored = await mongo_db.articles.find_one({"source_id": "test-premium-1"})
        assert premium_stored is not None
        assert premium_stored.get("relevance_score") is not None
        assert premium_stored.get("relevance_tier") == 1  # Premium source should be tier 1

        # Low-priority article should have tier assigned but NO enrichment
        # (TASK-062: Tier 1 only enrichment - tier 2-3 skip LLM calls)
        low_stored = await mongo_db.articles.find_one({"source_id": "test-low-1"})
        assert low_stored is not None
        assert low_stored.get("relevance_tier") is not None  # Tier should be assigned
        assert low_stored.get("relevance_score") is None  # But no enrichment (tier 2-3)
    
    @pytest.mark.asyncio
    async def test_fallback_to_standard_llm_on_error(self, mongo_db, monkeypatch):
        """Should fall back to standard LLM if optimized LLM fails to initialize."""
        # Mock the standard LLM provider
        monkeypatch.setattr(
            rss_fetcher,
            "get_llm_provider",
            lambda: FakeLLMProvider(themes=["Bitcoin"]),
        )
        
        # Mock optimized LLM to fail
        async def mock_get_optimized_llm_fail(db):
            raise Exception("API key invalid")
        
        monkeypatch.setattr(
            rss_fetcher,
            "get_optimized_llm",
            mock_get_optimized_llm_fail,
        )
        
        # Clear and insert test article
        await mongo_db.articles.delete_many({})
        
        article = {
            "title": "Bitcoin ETF Approval by SEC",
            "source_id": "test-fallback-1",
            "source": "coindesk",
            "text": "Bitcoin ETF approval marks a major milestone for cryptocurrency adoption.",
            "url": "https://example.com/test",
            "lang": "en",
            "metrics": ArticleMetrics().model_dump(),
            "keywords": [],
            "relevance_score": None,
            "sentiment_score": None,
            "sentiment_label": None,
            "raw_data": {},
            "published_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        await mongo_db.articles.insert_one(article)

        # Should not raise - falls back to standard processing
        await rss_fetcher.process_new_articles_from_mongodb()

        # Verify article was still processed and enriched (should be tier 1)
        stored = await mongo_db.articles.find_one({"source_id": "test-fallback-1"})
        assert stored is not None
        assert stored.get("relevance_tier") == 1, "Article should be tier 1"
        assert stored.get("relevance_score") is not None, "Tier 1 article should have relevance_score"


class TestCostSavingsCalculation:
    """Tests to verify cost savings logic."""
    
    def test_expected_llm_percentage_around_50(self):
        """Verify that roughly 50% of articles would use LLM."""
        processor = SelectiveArticleProcessor(MagicMock())
        
        # Simulate a mix of articles
        test_articles = [
            # Premium sources (always LLM)
            {"source": "coindesk", "title": "Bitcoin news"},
            {"source": "cointelegraph", "title": "Ethereum update"},
            {"source": "decrypt", "title": "Crypto market"},
            {"source": "theblock", "title": "DeFi news"},
            
            # Skip LLM sources (never LLM)
            {"source": "bitcoinmagazine", "title": "Bitcoin analysis"},
            {"source": "cryptoslate", "title": "Crypto roundup"},
            {"source": "cryptopotato", "title": "Market update"},
            {"source": "newsbtc", "title": "Price analysis"},
            
            # Mid-tier with keywords (LLM)
            {"source": "unknown", "title": "SEC approves new regulation"},
            {"source": "unknown", "title": "Major hack exploits protocol"},
            
            # Mid-tier without keywords (no LLM)
            {"source": "unknown", "title": "Weekly newsletter"},
            {"source": "unknown", "title": "Community update"},
        ]
        
        llm_count = sum(1 for a in test_articles if processor.should_use_llm(a))
        llm_percentage = llm_count / len(test_articles) * 100
        
        # Should be around 50% (6 out of 12 = 50%)
        assert 40 <= llm_percentage <= 60, f"Expected ~50% LLM usage, got {llm_percentage}%"
