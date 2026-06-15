"""Tests for ArticleFreshness signal source."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.signal_sources.article_freshness import (
    ArticleFreshnessSignalSource,
)
from crypto_news_aggregator.bugops.models import BugOpsSubsystem, AlertSeverity


class TestArticleFreshnessSignalSource:
    """Tests for ArticleFreshnessSignalSource."""

    @pytest.fixture
    def signal_source(self):
        """Create a signal source instance."""
        return ArticleFreshnessSignalSource()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = AsyncMock()
        db.articles = MagicMock()
        return db

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES = 60
        settings.BUGOPS_ARTICLE_FETCH_LOOKBACK_MINUTES = 90
        settings.BUGOPS_ARTICLE_HISTORY_LOOKBACK_DAYS = 7
        return settings

    def test_class_attributes(self, signal_source):
        """Test that class attributes are correctly set."""
        assert signal_source.source_type == "article_freshness"
        assert signal_source.root_subsystem == BugOpsSubsystem.ARTICLES.value
        assert signal_source.severity == AlertSeverity.HIGH
        assert signal_source.dedupe_key == "article_freshness:articles"
        assert "RSS ingestion health" in signal_source.suggested_manual_check

    @pytest.mark.asyncio
    async def test_check_failure_no_fetch_activity(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns False when no articles fetched recently."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.articles.find_one = AsyncMock(return_value=None)
            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_failure_no_historical_activity(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns False when articles fetched but no historical activity at this hour."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            fetch_doc = {
                "fetched_at": now - timedelta(minutes=30),
                "_id": "test_fetch",
            }

            # Setup: first call (fetch activity check) returns a document
            # Second call (historical activity check) returns empty list
            mock_db.articles.find_one = AsyncMock(return_value=fetch_doc)
            mock_db.articles.find.return_value.to_list = AsyncMock(
                return_value=[]
            )

            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_failure_articles_are_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns False when articles are fresh (recent created_at)."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            fetch_doc = {
                "fetched_at": now - timedelta(minutes=30),
                "_id": "test_fetch",
            }
            historical_doc = {
                "created_at": now - timedelta(hours=1),
                "_id": "test_historical",
            }
            fresh_doc = {
                "created_at": now - timedelta(minutes=30),
                "_id": "test_fresh",
            }

            call_count = [0]

            async def find_one_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return fetch_doc  # First call: fetch activity
                return fresh_doc  # Second call: freshness check

            mock_db.articles.find_one = AsyncMock(side_effect=find_one_side_effect)
            mock_db.articles.find.return_value.to_list = AsyncMock(
                return_value=[historical_doc]
            )

            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_failure_stale_articles_with_preconditions(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns True when fetch activity exists, historical activity exists, and no recent articles."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            current_hour = now.hour

            fetch_doc = {
                "fetched_at": now - timedelta(minutes=30),
                "_id": "test_fetch",
            }
            # Historical doc with same hour as now
            historical_doc = {
                "created_at": now - timedelta(days=2, hours=0),
                "_id": "test_historical",
            }
            historical_doc["created_at"] = historical_doc["created_at"].replace(
                hour=current_hour
            )

            # Use AsyncMock for find_one to properly handle await
            call_count = [0]

            async def find_one_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return fetch_doc  # First call: fetch activity
                return None  # Second call: freshness check (no fresh articles)

            mock_db.articles.find_one = AsyncMock(side_effect=find_one_side_effect)
            mock_db.articles.find.return_value.to_list = AsyncMock(
                return_value=[historical_doc]
            )

            result = await signal_source.check_failure(mock_db)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_recovery_returns_true_when_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """check_recovery returns True when a fresh article exists."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            fresh_doc = {
                "created_at": now - timedelta(minutes=30),
                "_id": "test_fresh",
            }

            mock_db.articles.find_one = AsyncMock(return_value=fresh_doc)

            result = await signal_source.check_recovery(mock_db)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_recovery_returns_false_when_no_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """check_recovery returns False when no fresh article exists."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.articles.find_one = AsyncMock(return_value=None)

            result = await signal_source.check_recovery(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_tolerance_buffer_30_seconds(
        self, signal_source, mock_db, mock_settings
    ):
        """An article arriving 30 seconds after window boundary is not treated as stale."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            current_hour = now.hour

            # Article created exactly at the window boundary + 30 seconds
            article_time = now - timedelta(
                minutes=mock_settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES,
                seconds=30,
            )

            fetch_doc = {
                "fetched_at": now - timedelta(minutes=30),
                "_id": "test_fetch",
            }
            historical_doc = {
                "created_at": now - timedelta(days=2),
                "_id": "test_historical",
            }
            historical_doc["created_at"] = historical_doc["created_at"].replace(
                hour=current_hour
            )
            fresh_doc = {
                "created_at": article_time,
                "_id": "test_fresh",
            }

            call_count = [0]

            async def find_one_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return fetch_doc  # First call: fetch activity
                return fresh_doc  # Second call: freshness check (article within tolerance)

            mock_db.articles.find_one = AsyncMock(side_effect=find_one_side_effect)
            mock_db.articles.find.return_value.to_list = AsyncMock(
                return_value=[historical_doc]
            )

            result = await signal_source.check_failure(mock_db)
            # Should be False because article is fresh (within window + 60s tolerance)
            assert result is False

    @pytest.mark.asyncio
    async def test_collect_returns_empty_list(self, signal_source):
        """collect() returns empty list."""
        result = await signal_source.collect()
        assert result == []

    @pytest.mark.asyncio
    async def test_check_failure_handles_exception(
        self, signal_source, mock_db, mock_settings
    ):
        """check_failure catches exceptions and returns False."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.articles.find_one = AsyncMock(side_effect=Exception("DB error"))

            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_recovery_handles_exception(
        self, signal_source, mock_db, mock_settings
    ):
        """check_recovery catches exceptions and returns False."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.article_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.articles.find_one = AsyncMock(side_effect=Exception("DB error"))

            result = await signal_source.check_recovery(mock_db)
            assert result is False
