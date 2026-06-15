"""Tests for SignalFreshness signal source."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from crypto_news_aggregator.bugops.signal_sources.signal_freshness import (
    SignalFreshnessSignalSource,
)
from crypto_news_aggregator.bugops.models import BugOpsSubsystem, AlertSeverity


class TestSignalFreshnessSignalSource:
    """Tests for SignalFreshnessSignalSource."""

    @pytest.fixture
    def signal_source(self):
        """Create a signal source instance."""
        return SignalFreshnessSignalSource()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = AsyncMock()
        db.articles = MagicMock()
        db.signal_scores = MagicMock()
        return db

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES = 90
        return settings

    def test_class_attributes(self, signal_source):
        """Test that class attributes are correctly set."""
        assert signal_source.source_type == "signal_freshness"
        assert signal_source.root_subsystem == BugOpsSubsystem.SIGNALS.value
        assert signal_source.severity == AlertSeverity.HIGH
        assert signal_source.dedupe_key == "signal_freshness:signals"
        assert "signal generation worker health" in signal_source.suggested_manual_check

    @pytest.mark.asyncio
    async def test_check_failure_no_recent_articles(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns False when no articles exist recently (legitimate idle)."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.articles.find_one = AsyncMock(return_value=None)

            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_failure_articles_and_signals_are_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns False when articles and signals are both fresh."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            article_doc = {
                "created_at": now - timedelta(minutes=30),
                "_id": "test_article",
            }
            signal_doc = {
                "last_updated": now - timedelta(minutes=30),
                "_id": "test_signal",
            }

            call_count = [0]

            async def find_one_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return article_doc  # First call: article check
                return signal_doc  # Second call: signal freshness check

            mock_db.articles.find_one = AsyncMock(side_effect=find_one_side_effect)
            mock_db.signal_scores.find_one = AsyncMock(return_value=signal_doc)

            result = await signal_source.check_failure(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_failure_articles_exist_but_no_fresh_signals(
        self, signal_source, mock_db, mock_settings
    ):
        """Returns True when articles are fresh but signals are stale."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            article_doc = {
                "created_at": now - timedelta(minutes=30),
                "_id": "test_article",
            }

            mock_db.articles.find_one = AsyncMock(return_value=article_doc)
            mock_db.signal_scores.find_one = AsyncMock(return_value=None)

            result = await signal_source.check_failure(mock_db)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_recovery_returns_true_when_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """check_recovery returns True when a fresh signal exists."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)
            signal_doc = {
                "last_updated": now - timedelta(minutes=30),
                "_id": "test_signal",
            }

            mock_db.signal_scores.find_one = AsyncMock(return_value=signal_doc)

            result = await signal_source.check_recovery(mock_db)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_recovery_returns_false_when_no_fresh(
        self, signal_source, mock_db, mock_settings
    ):
        """check_recovery returns False when no fresh signal exists."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.signal_scores.find_one = AsyncMock(return_value=None)

            result = await signal_source.check_recovery(mock_db)
            assert result is False

    @pytest.mark.asyncio
    async def test_tolerance_buffer_30_seconds(
        self, signal_source, mock_db, mock_settings
    ):
        """A signal arriving 30 seconds after window boundary is treated as fresh."""
        with patch(
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            now = datetime.now(timezone.utc)

            # Article created recently (to trigger failure condition check)
            article_doc = {
                "created_at": now - timedelta(minutes=30),
                "_id": "test_article",
            }

            # Signal created exactly at the window boundary + 30 seconds
            signal_time = now - timedelta(
                minutes=mock_settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES,
                seconds=30,
            )
            signal_doc = {
                "last_updated": signal_time,
                "_id": "test_signal",
            }

            mock_db.articles.find_one = AsyncMock(return_value=article_doc)
            mock_db.signal_scores.find_one = AsyncMock(return_value=signal_doc)

            result = await signal_source.check_failure(mock_db)
            # Should be False because signal is fresh (within window + 60s tolerance)
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
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
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
            "crypto_news_aggregator.bugops.signal_sources.signal_freshness.get_settings",
            return_value=mock_settings,
        ):
            mock_db.signal_scores.find_one = AsyncMock(side_effect=Exception("DB error"))

            result = await signal_source.check_recovery(mock_db)
            assert result is False
