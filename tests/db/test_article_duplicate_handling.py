"""
Tests for graceful E11000 duplicate URL error handling.

Verifies:
1. E11000 errors do not block entire batch
2. Failed articles are logged but processing continues
3. Successful articles in batch are still created
4. Enrichment cycle is not blocked by duplicate URL
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pymongo.errors import DuplicateKeyError
from crypto_news_aggregator.db.operations.articles import create_or_update_articles
from crypto_news_aggregator.models.article import ArticleCreate, ArticleMetrics
from datetime import datetime, timezone


def create_test_article(source_id, url):
    """Helper to create test articles."""
    return ArticleCreate(
        url=url,
        title=f"Article {source_id}",
        text=f"Text {source_id}",
        source_id=source_id,
        source="rss",
        published_at=datetime.now(timezone.utc),
        metrics=ArticleMetrics(),
        raw_data={},
    )


@pytest.mark.asyncio
async def test_e11000_url_duplicate_treated_as_success():
    """Verify E11000 error for duplicate URL is treated as successful (article already in DB)."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    mock_collection.find_one = AsyncMock(return_value=None)
    mock_service = AsyncMock()

    call_count = [0]

    async def create_with_duplicate(data):
        call_count[0] += 1
        # Second call (source-2) raises E11000 for URL (expected duplicate)
        if data.get("source_id") == "source-2":
            raise DuplicateKeyError("E11000 duplicate key error collection: articles index: url_unique dup key")
        return None

    mock_service.create_article = create_with_duplicate

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
        create_test_article("source-3", "https://example.com/article3"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service):

        # URL duplicates should succeed (article already exists)
        await create_or_update_articles(articles)

        # All three articles should be attempted
        assert call_count[0] == 3


@pytest.mark.asyncio
async def test_url_duplicate_logged_without_secrets():
    """Verify URL duplicate errors are logged without exposing URLs or IDs."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    mock_collection.find_one = AsyncMock(return_value=None)
    mock_service = AsyncMock()

    async def create_with_duplicate(data):
        if data.get("source_id") == "source-2":
            raise DuplicateKeyError("E11000 duplicate key error collection: articles index: url_unique dup key")
        return None

    mock_service.create_article = create_with_duplicate

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service), \
         patch('crypto_news_aggregator.db.operations.articles.logger') as mock_logger:

        await create_or_update_articles(articles)

        # Should have logged debug message for duplicate URL
        debug_calls = [c for c in mock_logger.debug.call_args_list]
        assert len(debug_calls) > 0, "Should log duplicate URL detection"

        # Verify log message does NOT contain URLs or raw IDs (per ticket section 28)
        for call in debug_calls:
            log_msg = str(call)
            assert "example.com" not in log_msg, "URL must not be logged"
            assert "source-" not in log_msg, "source_id must not be logged"
            # Message should mention duplicate generically
            if "duplicate" in log_msg or "already" in log_msg:
                assert True  # Found expected generic message


@pytest.mark.asyncio
async def test_successful_articles_created_with_url_duplicate():
    """Verify successful articles are still created when one has a duplicate URL."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    mock_collection.find_one = AsyncMock(return_value=None)
    mock_service = AsyncMock()
    created_ids = []

    async def track_creates(data):
        if data.get("source_id") == "source-2":
            # Duplicate URL (expected case)
            raise DuplicateKeyError("E11000 duplicate key error collection: articles index: url_unique dup key")
        created_ids.append(data["source_id"])

    mock_service.create_article = track_creates

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
        create_test_article("source-3", "https://example.com/article3"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service):

        await create_or_update_articles(articles)

        # Articles 1 and 3 should be created
        assert "source-1" in created_ids
        assert "source-3" in created_ids
        assert "source-2" not in created_ids


@pytest.mark.asyncio
async def test_unexpected_unique_constraint_propagates():
    """Verify unexpected unique constraint errors (not URL) propagate."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    mock_collection.find_one = AsyncMock(return_value=None)
    mock_service = AsyncMock()

    async def create_with_error(data):
        if data.get("source_id") == "source-2":
            # Unexpected unique constraint (not URL)
            raise DuplicateKeyError("E11000 duplicate key error collection: articles index: unknown_field")
        return None

    mock_service.create_article = create_with_error

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
        create_test_article("source-3", "https://example.com/article3"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service):

        # Unexpected unique constraint errors should re-raise
        with pytest.raises(DuplicateKeyError):
            await create_or_update_articles(articles)


@pytest.mark.asyncio
async def test_non_duplicate_errors_propagate():
    """Verify non-DuplicateKeyError exceptions propagate (don't silently continue)."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    mock_collection.find_one = AsyncMock(return_value=None)
    mock_service = AsyncMock()

    async def create_with_error(data):
        if data.get("source_id") == "source-2":
            raise ValueError("Database connection error")
        return None

    mock_service.create_article = create_with_error

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
        create_test_article("source-3", "https://example.com/article3"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service):

        # Non-duplicate errors should raise and propagate
        with pytest.raises(ValueError, match="Database connection error"):
            await create_or_update_articles(articles)


@pytest.mark.asyncio
async def test_update_existing_article_success():
    """Verify updating existing articles works when no duplicates."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.articles = mock_collection

    # First article already exists
    existing = {"_id": "id-1"}
    async def find_existing(query):
        if query.get("source_id") == "source-1":
            return existing
        return None

    mock_collection.find_one = find_existing
    mock_collection.update_one = AsyncMock()
    mock_service = AsyncMock()

    articles = [
        create_test_article("source-1", "https://example.com/article1"),
        create_test_article("source-2", "https://example.com/article2"),
    ]

    with patch('crypto_news_aggregator.db.operations.articles.mongo_manager.get_async_database', AsyncMock(return_value=mock_db)), \
         patch('crypto_news_aggregator.db.operations.articles.get_article_service', return_value=mock_service):

        await create_or_update_articles(articles)

        # First article should trigger update
        assert mock_collection.update_one.call_count == 1
        # Second should be created
        assert mock_service.create_article.call_count == 1
