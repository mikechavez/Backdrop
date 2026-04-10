import asyncio
from datetime import datetime, timezone

import pytest

from src.crypto_news_aggregator.background import rss_fetcher
from src.crypto_news_aggregator.services.rss_service import RSSService
from src.crypto_news_aggregator.models.article import (
    ArticleCreate,
    ArticleMetrics,
    ArticleAuthor,
)


class FakeLLMProvider:
    def __init__(self, relevance: float = 0.8, sentiment: float = 0.6, themes=None):
        self._relevance = relevance
        self._sentiment = sentiment
        self._themes = themes or ["Bitcoin", "Market"]

    def analyze_sentiment(self, text: str) -> float:
        return self._sentiment

    def extract_themes(self, texts):
        return self._themes

    def generate_insight(self, data):
        raise NotImplementedError

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

    async def extract_entities_batch(self, articles):
        """Return mock entities based on article content."""
        results = []
        for article in articles:
            title = article.get("title", "").lower()
            entities = []
            if "bitcoin" in title or "btc" in title:
                entities.append({"name": "Bitcoin", "type": "cryptocurrency", "confidence": 0.95, "is_primary": True})
            if "ethereum" in title or "eth" in title:
                entities.append({"name": "Ethereum", "type": "cryptocurrency", "confidence": 0.9, "is_primary": False})
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
        return {"active_entries": 0, "hit_rate_percent": 0.0}

    async def get_cost_summary(self):
        return {"month_to_date": 0.0, "projected_monthly": 0.0}


class FakeRSSService:
    def __init__(self, articles):
        self._articles = articles

    async def fetch_all_feeds(self):
        await asyncio.sleep(0)
        return self._articles


@pytest.mark.asyncio
async def test_process_new_articles_from_mongodb_enriches_articles(
    mongo_db, monkeypatch
):
    monkeypatch.setattr(
        rss_fetcher,
        "get_llm_provider",
        lambda: FakeLLMProvider(themes=["ETFs", "Institutional"]),
    )
    
    # Mock optimized LLM
    async def mock_get_optimized_llm(db):
        return FakeOptimizedLLM()
    monkeypatch.setattr(rss_fetcher, "get_optimized_llm", mock_get_optimized_llm)

    await mongo_db.articles.delete_many({})
    article_doc = {
        "title": "BTC surges as ETFs see inflows",
        "source_id": "test-article-1",
        "source": "rss",
        "text": "Bitcoin rallied above $70k amid renewed ETF demand.",
        "author": None,
        "url": "https://example.com/btc-surges",
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
    insert_result = await mongo_db.articles.insert_one(article_doc)

    await rss_fetcher.process_new_articles_from_mongodb()

    # Wait a bit for enrichment to complete
    await asyncio.sleep(0.1)

    stored = await mongo_db.articles.find_one({"source_id": "test-article-1"})
    assert stored is not None
    assert stored["relevance_score"] == pytest.approx(0.8)
    assert stored["sentiment_score"] == pytest.approx(0.6)
    assert stored["sentiment_label"] == "positive"
    assert stored["themes"] == ["ETFs", "Institutional"]


@pytest.mark.asyncio
async def test_fetch_and_process_rss_feeds_persists_and_enriches(mongo_db, monkeypatch):
    monkeypatch.setattr(
        rss_fetcher,
        "get_llm_provider",
        lambda: FakeLLMProvider(themes=["ETFs", "Institutional"]),
    )
    
    # Mock optimized LLM
    async def mock_get_optimized_llm(db):
        return FakeOptimizedLLM()
    monkeypatch.setattr(rss_fetcher, "get_optimized_llm", mock_get_optimized_llm)
    
    await mongo_db.articles.delete_many({})

    article = ArticleCreate(
        title="Institutional flows drive crypto rally",
        source_id="test-article-2",
        source="rss",
        text="Large investors poured capital into Bitcoin ETFs, lifting prices.",
        author=None,
        url="https://example.com/etf-flows",
        lang="en",
        metrics=ArticleMetrics(),
        keywords=[],
        relevance_score=None,
        sentiment_score=None,
        sentiment_label=None,
        raw_data={},
        published_at=datetime.now(timezone.utc),
    )

    from src.crypto_news_aggregator.services import rss_service

    monkeypatch.setattr(rss_service, "RSSService", lambda: FakeRSSService([article]))

    await rss_fetcher.fetch_and_process_rss_feeds()

    # Wait a bit for enrichment to complete
    await asyncio.sleep(0.1)

    stored = await mongo_db.articles.find_one({"source_id": "test-article-2"})
    assert stored is not None
    assert stored["relevance_score"] == pytest.approx(0.8)
    assert stored["sentiment_score"] == pytest.approx(0.6)
    assert stored["sentiment_label"] == "positive"
    assert stored["themes"] == ["ETFs", "Institutional"]


def test_rss_service_has_correct_feed_count():
    """Verify that RSSService has the expected number of RSS feeds configured."""
    rss_service = RSSService()
    
    # Should have 13 total feeds:
    # - 4 original (coindesk, cointelegraph, decrypt, bitcoinmagazine)
    # - 6 News & General (theblock, cryptoslate, benzinga, bitcoin.com, dlnews, watcherguru)
    # - 2 Research & Analysis (glassnode, messari)
    # - 1 DeFi-Focused (thedefiant)
    assert len(rss_service.feed_urls) == 13, f"Expected 13 RSS feeds, got {len(rss_service.feed_urls)}"
    
    # Verify key sources are present
    expected_sources = [
        "coindesk", "cointelegraph", "decrypt", "bitcoinmagazine",  # Original
        "theblock", "cryptoslate", "benzinga", "bitcoin.com", "dlnews", "watcherguru",  # News & General
        "glassnode", "messari",  # Research
        "thedefiant",  # DeFi
    ]
    
    for source in expected_sources:
        assert source in rss_service.feed_urls, f"Expected source '{source}' not found in feed_urls"
    
    # Verify all URLs are valid strings
    for source, url in rss_service.feed_urls.items():
        assert isinstance(url, str), f"URL for {source} is not a string"
        assert url.startswith("http"), f"URL for {source} does not start with http"


def test_rss_source_names_match_article_model():
    """
    Validate that all RSS source names are valid according to ArticleCreate model.
    This prevents runtime validation errors when creating articles from RSS feeds.
    """
    from typing import get_args
    from crypto_news_aggregator.models.article import ArticleBase
    
    rss_service = RSSService()
    
    # Get the valid source values from the ArticleBase Literal type
    # ArticleBase has the 'source' field with Literal type
    source_field = ArticleBase.model_fields['source']
    valid_sources = get_args(source_field.annotation)
    
    # Check that all RSS source names are in the valid sources list
    for source_name in rss_service.feed_urls.keys():
        assert source_name in valid_sources, (
            f"RSS source '{source_name}' is not in ArticleCreate model's valid sources. "
            f"Valid sources are: {valid_sources}"
        )
