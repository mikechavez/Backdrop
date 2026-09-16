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
    def __init__(self, articles, feed_results=None):
        self._articles = articles
        self._feed_results = feed_results if feed_results is not None else {"rss": True}

    async def fetch_all_feeds(self):
        await asyncio.sleep(0)
        return self._articles

    async def fetch_all_feeds_with_results(self):
        await asyncio.sleep(0)
        return self._articles, self._feed_results


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
    await mongo_db.scheduler_locks.delete_many({})

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

    monkeypatch.setattr(rss_fetcher, "RSSService", lambda: FakeRSSService([article]))

    await rss_fetcher.fetch_and_process_rss_feeds()

    # Wait a bit for enrichment to complete
    await asyncio.sleep(0.1)

    stored = await mongo_db.articles.find_one({"source_id": "test-article-2"})
    assert stored is not None
    assert stored["relevance_score"] == pytest.approx(0.8)
    assert stored["sentiment_score"] == pytest.approx(0.6)
    assert stored["sentiment_label"] == "positive"
    assert stored["themes"] == ["ETFs", "Institutional"]

    # BUG-110: the canonical production ingestion path must record a
    # fetch_news heartbeat so /health reflects real fetch activity.
    heartbeat = await mongo_db.pipeline_heartbeats.find_one({"_id": "fetch_news"})
    assert heartbeat is not None
    assert heartbeat["last_success"] is not None
    assert "feeds ok" in heartbeat["last_result_summary"]


@pytest.mark.asyncio
async def test_fetch_and_process_rss_feeds_records_heartbeat_with_failed_feeds(
    mongo_db, monkeypatch
):
    """A partial feed failure should still record a heartbeat and surface
    which feeds failed in the summary, instead of only ever reporting
    aggregate article counts (BUG-110)."""
    monkeypatch.setattr(
        rss_fetcher,
        "get_llm_provider",
        lambda: FakeLLMProvider(themes=["ETFs"]),
    )

    async def mock_get_optimized_llm(db):
        return FakeOptimizedLLM()

    monkeypatch.setattr(rss_fetcher, "get_optimized_llm", mock_get_optimized_llm)

    await mongo_db.articles.delete_many({})
    await mongo_db.pipeline_heartbeats.delete_many({})
    await mongo_db.scheduler_locks.delete_many({})

    article = ArticleCreate(
        title="Only one feed responded",
        source_id="test-article-partial-feed-failure",
        source="rss",
        text="One feed succeeded while another failed to parse.",
        author=None,
        url="https://example.com/partial-failure",
        lang="en",
        metrics=ArticleMetrics(),
        keywords=[],
        relevance_score=None,
        sentiment_score=None,
        sentiment_label=None,
        raw_data={},
        published_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        rss_fetcher,
        "RSSService",
        lambda: FakeRSSService(
            [article], feed_results={"coindesk": True, "decrypt": False}
        ),
    )

    await rss_fetcher.fetch_and_process_rss_feeds()
    await asyncio.sleep(0.1)

    heartbeat = await mongo_db.pipeline_heartbeats.find_one({"_id": "fetch_news"})
    assert heartbeat is not None
    assert "1/2 feeds ok" in heartbeat["last_result_summary"]


@pytest.mark.asyncio
async def test_fetch_and_process_rss_feeds_skips_when_lock_held_by_another_replica(
    mongo_db, monkeypatch
):
    """BUG-110: if another replica already holds the rss_fetch scheduler
    lock, this cycle must be skipped entirely -- no fetch, no upsert, no
    heartbeat -- rather than running concurrently or waiting."""
    from datetime import timedelta

    await mongo_db.articles.delete_many({})
    await mongo_db.pipeline_heartbeats.delete_many({})
    await mongo_db.scheduler_locks.delete_many({})

    now = datetime.now(timezone.utc)
    await mongo_db.scheduler_locks.insert_one(
        {
            "_id": "rss_fetch",
            "owner_token": "other-replica-owns-this",
            "acquired_at": now,
            "expires_at": now + timedelta(seconds=600),
        }
    )

    fetch_called = False

    class ExplodingRSSService:
        async def fetch_all_feeds_with_results(self):
            nonlocal fetch_called
            fetch_called = True
            raise AssertionError("fetch must not run while another replica holds the lock")

    monkeypatch.setattr(rss_fetcher, "RSSService", lambda: ExplodingRSSService())

    await rss_fetcher.fetch_and_process_rss_feeds()

    assert fetch_called is False
    assert await mongo_db.articles.count_documents({}) == 0
    assert await mongo_db.pipeline_heartbeats.find_one({"_id": "fetch_news"}) is None

    # The other replica's lock must be left untouched.
    lock_doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert lock_doc["owner_token"] == "other-replica-owns-this"


@pytest.mark.asyncio
async def test_fetch_and_process_rss_feeds_releases_lock_after_success(
    mongo_db, monkeypatch
):
    """The lock must be released once a cycle completes, so the next
    scheduled cycle on this (or another) replica can acquire it."""
    monkeypatch.setattr(
        rss_fetcher, "get_llm_provider", lambda: FakeLLMProvider(themes=["ETFs"])
    )

    async def mock_get_optimized_llm(db):
        return FakeOptimizedLLM()

    monkeypatch.setattr(rss_fetcher, "get_optimized_llm", mock_get_optimized_llm)

    await mongo_db.articles.delete_many({})
    await mongo_db.scheduler_locks.delete_many({})

    article = ArticleCreate(
        title="Lock release check",
        source_id="test-article-lock-release",
        source="rss",
        text="Verifies the scheduler lock is released after a completed cycle.",
        author=None,
        url="https://example.com/lock-release",
        lang="en",
        metrics=ArticleMetrics(),
        keywords=[],
        relevance_score=None,
        sentiment_score=None,
        sentiment_label=None,
        raw_data={},
        published_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(rss_fetcher, "RSSService", lambda: FakeRSSService([article]))

    await rss_fetcher.fetch_and_process_rss_feeds()
    await asyncio.sleep(0.1)

    assert await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"}) is None


@pytest.mark.asyncio
async def test_fetch_and_process_rss_feeds_releases_lock_after_upsert_failure(
    mongo_db, monkeypatch
):
    """The lock must be released even when a stage fails, via the `finally`
    block, so one failed cycle can't permanently starve ingestion."""
    await mongo_db.articles.delete_many({})
    await mongo_db.scheduler_locks.delete_many({})

    article = ArticleCreate(
        title="Upsert failure",
        source_id="test-article-upsert-failure",
        source="rss",
        text="Triggers a simulated upsert failure.",
        author=None,
        url="https://example.com/upsert-failure",
        lang="en",
        metrics=ArticleMetrics(),
        keywords=[],
        relevance_score=None,
        sentiment_score=None,
        sentiment_label=None,
        raw_data={},
        published_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(rss_fetcher, "RSSService", lambda: FakeRSSService([article]))

    async def failing_create_or_update_articles(articles):
        raise RuntimeError("simulated MongoDB upsert failure")

    monkeypatch.setattr(
        rss_fetcher, "create_or_update_articles", failing_create_or_update_articles
    )

    with pytest.raises(RuntimeError, match="simulated MongoDB upsert failure"):
        await rss_fetcher.fetch_and_process_rss_feeds()

    assert await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"}) is None


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
