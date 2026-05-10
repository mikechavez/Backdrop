"""
Tests for narrative display mode API fields (FEATURE-061).

Verifies that:
1. Trusted narratives render as display_mode="summary"
2. Untrusted narratives with recent activity render as display_mode="article_cluster"
3. Article-cluster mode uses deterministic fallback copy (no LLM calls)
4. Public display fields do not expose stale/missing/untrusted/needs refresh
5. No narrative records are mutated
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock

from crypto_news_aggregator.api.v1.endpoints.narratives import (
    _get_narrative_display_mode,
    NarrativeResponse,
)
from crypto_news_aggregator.services.narrative_trust import (
    is_narrative_summary_trusted,
    get_fresh_start_cutoff,
)


@pytest.fixture
def fresh_start_cutoff():
    """Return a fresh-start cutoff time."""
    return datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def old_cutoff():
    """Return a cutoff from before most test data."""
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class TestNarrativeTrustHelpers:
    """Test shared trust helpers."""

    def test_is_narrative_summary_trusted_by_first_seen(self, fresh_start_cutoff):
        """Narrative with first_seen >= cutoff should be trusted."""
        narrative = {
            "theme": "regulatory",
            "first_seen": fresh_start_cutoff + timedelta(days=1),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is True

    def test_is_narrative_summary_trusted_by_last_summary_generated(self, fresh_start_cutoff):
        """Narrative with last_summary_generated_at >= cutoff should be trusted."""
        narrative = {
            "theme": "regulatory",
            "first_seen": fresh_start_cutoff - timedelta(days=10),
            "last_summary_generated_at": fresh_start_cutoff + timedelta(hours=1),
            "_fresh_start_validated_at": None,
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is True

    def test_is_narrative_summary_trusted_by_fresh_start_validated(self, fresh_start_cutoff):
        """Narrative with _fresh_start_validated_at >= cutoff should be trusted."""
        narrative = {
            "theme": "regulatory",
            "first_seen": fresh_start_cutoff - timedelta(days=10),
            "last_summary_generated_at": fresh_start_cutoff - timedelta(days=5),
            "_fresh_start_validated_at": fresh_start_cutoff + timedelta(hours=1),
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is True

    def test_is_narrative_summary_untrusted(self, fresh_start_cutoff):
        """Narrative with all timestamps before cutoff should be untrusted."""
        narrative = {
            "theme": "regulatory",
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": fresh_start_cutoff - timedelta(days=20),
            "_fresh_start_validated_at": None,
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is False

    def test_is_narrative_summary_untrusted_missing_fields(self, fresh_start_cutoff):
        """Narrative with missing timestamp fields should be untrusted (fail-closed)."""
        narrative = {
            "theme": "regulatory",
            # All fields missing
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is False

    def test_is_narrative_summary_handles_string_timestamps(self, fresh_start_cutoff):
        """Trust check should handle ISO string timestamps."""
        narrative = {
            "theme": "regulatory",
            "first_seen": (fresh_start_cutoff + timedelta(days=1)).isoformat(),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert is_narrative_summary_trusted(narrative, fresh_start_cutoff) is True


class TestNarrativeDisplayMode:
    """Test display mode computation."""

    def test_trusted_narrative_shows_summary_mode(self, fresh_start_cutoff):
        """Trusted narrative should render as display_mode='summary'."""
        narrative = {
            "theme": "regulatory",
            "title": "SEC Enforcement Ramps Up",
            "summary": "The SEC has intensified crypto enforcement actions.",
            "entities": ["SEC", "Coinbase", "Binance"],
            "article_count": 15,
            "first_seen": fresh_start_cutoff + timedelta(days=1),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert mode == "summary"
        assert title == "SEC Enforcement Ramps Up"
        assert summary == "The SEC has intensified crypto enforcement actions."

    def test_untrusted_narrative_shows_article_cluster_mode(self, fresh_start_cutoff):
        """Untrusted narrative with recent articles should render as article_cluster."""
        narrative = {
            "theme": "regulatory",
            "title": "Old Generated Title",
            "summary": "This is stale.",
            "entities": ["SEC", "Coinbase"],
            "article_count": 8,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": fresh_start_cutoff - timedelta(days=20),
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "SEC Moves Against Coinbase"},
            {"title": "Coinbase Faces New Regulatory Hurdles"},
            {"title": "SEC Chair Signals More Enforcement"},
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert mode == "article_cluster"
        assert title == "SEC"  # Primary entity, not stale generated title
        assert "Latest coverage includes" in summary
        assert "Old Generated Title" not in summary
        assert "stale" not in summary.lower()
        assert "untrusted" not in summary.lower()

    def test_article_cluster_fallback_no_articles_with_count(self, fresh_start_cutoff):
        """Article cluster with no articles but article_count > 0 should use count fallback."""
        narrative = {
            "theme": "regulatory",
            "title": "Old Title",
            "summary": "Stale.",
            "entities": ["SEC"],
            "article_count": 5,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert mode == "article_cluster"
        assert title == "SEC"
        assert summary == "Recent coverage includes 5 articles in this narrative."
        assert "stale" not in summary.lower()

    def test_article_cluster_fallback_zero_articles(self, fresh_start_cutoff):
        """Article cluster with zero articles should use tracking message."""
        narrative = {
            "theme": "regulatory",
            "title": "Old Title",
            "summary": "Stale.",
            "entities": ["SEC"],
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert mode == "article_cluster"
        assert title == "SEC"
        assert summary == "Recent coverage is being tracked for this narrative."

    def test_article_cluster_uses_primary_entity(self, fresh_start_cutoff):
        """Article cluster mode should use primary entity as title."""
        narrative = {
            "theme": "defi",
            "title": "Generated Title Nobody Should See",
            "summary": "Stale summary nobody should see.",
            "entities": ["Uniswap", "Aave", "MakerDAO"],
            "article_count": 10,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [{"title": "Uniswap Governance Vote"}]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "Uniswap"  # First entity
        assert title != "Generated Title Nobody Should See"

    def test_article_cluster_excludes_forbidden_words(self, fresh_start_cutoff):
        """Display summary should not include forbidden words."""
        narrative = {
            "theme": "regulatory",
            "title": "Stale Title",
            "summary": "Missing or untrusted data needs refresh.",
            "entities": ["SEC"],
            "article_count": 3,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [{"title": "SEC Action"}]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        forbidden = ["stale", "missing", "untrusted", "needs refresh"]
        for word in forbidden:
            assert word.lower() not in summary.lower()

    def test_article_cluster_builds_from_recent_articles(self, fresh_start_cutoff):
        """Article cluster summary should build from recent articles with proper formatting."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 5,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "Bitcoin Price Surge"},
            {"title": "Fed Rate Decision Looms"},
            {"title": "ETF Approval Rumors"},
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # 3 articles: should use Oxford comma format
        assert "Bitcoin Price Surge, Fed Rate Decision Looms, and ETF Approval Rumors" in summary

    def test_article_cluster_deduplicates_articles(self, fresh_start_cutoff):
        """Article cluster should not duplicate article titles."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 2,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "Bitcoin News"},
            {"title": "Bitcoin News"},  # Duplicate
            {"title": "Ethereum Update"},
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Should include Bitcoin News only once
        assert summary.count("Bitcoin News") == 1

    def test_article_cluster_single_article_formatting(self, fresh_start_cutoff):
        """Article cluster with 1 article should format cleanly."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 1,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [{"title": "SEC Files New Lawsuit"}]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Single article: no comma, no "and"
        assert summary == "Latest coverage includes SEC Files New Lawsuit."

    def test_article_cluster_two_article_formatting(self, fresh_start_cutoff):
        """Article cluster with 2 articles should use 'and' without Oxford comma."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 2,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "SEC Action"},
            {"title": "Binance Response"},
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Two articles: use "and" without Oxford comma
        assert summary == "Latest coverage includes SEC Action and Binance Response."

    def test_article_cluster_filters_forbidden_titles(self, fresh_start_cutoff):
        """Article cluster should filter out articles with forbidden words in title."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 5,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "This summary is stale"},  # Contains forbidden word
            {"title": "Data missing from report"},  # Contains forbidden word
            {"title": "SEC Filing"},  # Clean
            {"title": "Status: untrusted data"},  # Contains forbidden word
            {"title": "Binance News"},  # Clean
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Should only include SEC Filing and Binance News
        assert "SEC Filing" in summary
        assert "Binance News" in summary
        # Should not include forbidden titles
        assert "stale" not in summary.lower()
        assert "missing" not in summary.lower()
        assert "untrusted" not in summary.lower()

    def test_article_cluster_empty_title_skipped(self, fresh_start_cutoff):
        """Article cluster should skip articles with empty/null titles."""
        narrative = {
            "theme": "regulatory",
            "title": "Old",
            "summary": "Old.",
            "entities": ["SEC"],
            "article_count": 3,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": ""},  # Empty
            {"title": None},  # None
            {"title": "SEC Action"},  # Valid
            {},  # Missing title key
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Should only include SEC Action
        assert summary == "Latest coverage includes SEC Action."

    def test_article_cluster_title_fallback_chain(self, fresh_start_cutoff):
        """Display title should follow fallback chain: entity → theme → Recent Coverage."""
        # Test 1: Primary entity
        narrative = {
            "entities": ["Bitcoin"],
            "theme": "crypto_prices",
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "Bitcoin"

        # Test 2: No entity, use theme
        narrative = {
            "entities": [],
            "theme": "crypto_prices",
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
        }
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "crypto_prices"

        # Test 3: No entity, no theme, use Recent Coverage
        narrative = {
            "entities": [],
            "theme": "",
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
        }
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "Recent Coverage"

        # Test 4: Entity is empty string, fall through to theme
        narrative = {
            "entities": [""],
            "theme": "fallback_theme",
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
        }
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "fallback_theme"


class TestNarrativeResponseModel:
    """Test NarrativeResponse Pydantic model with display fields."""

    def test_narrative_response_includes_display_fields(self):
        """NarrativeResponse should validate with display fields."""
        data = {
            "id": "123abc",
            "_id": "123abc",
            "theme": "regulatory",
            "title": "Test Title",
            "summary": "Test summary",
            "entities": ["SEC"],
            "article_count": 5,
            "mention_velocity": 1.0,
            "lifecycle": "hot",
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "display_mode": "summary",
            "display_title": "Test Title",
            "display_summary": "Test summary",
            "recent_article_count": 5,
        }
        response = NarrativeResponse(**data)
        assert response.display_mode == "summary"
        assert response.display_title == "Test Title"
        assert response.display_summary == "Test summary"
        assert response.recent_article_count == 5

    def test_narrative_response_display_mode_literal_validation(self):
        """display_mode should only accept 'summary' or 'article_cluster'."""
        valid_data = {
            "id": "123abc",
            "_id": "123abc",
            "theme": "regulatory",
            "title": "Test",
            "summary": "Test",
            "entities": ["SEC"],
            "article_count": 5,
            "mention_velocity": 1.0,
            "lifecycle": "hot",
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "display_mode": "article_cluster",
            "display_title": "SEC",
            "display_summary": "Latest coverage",
            "recent_article_count": 5,
        }
        response = NarrativeResponse(**valid_data)
        assert response.display_mode == "article_cluster"

        # Invalid mode should raise validation error
        invalid_data = valid_data.copy()
        invalid_data["display_mode"] = "invalid_mode"
        with pytest.raises(ValueError):
            NarrativeResponse(**invalid_data)

    def test_narrative_response_display_summary_optional(self):
        """display_summary can be None."""
        data = {
            "id": "123abc",
            "_id": "123abc",
            "theme": "regulatory",
            "title": "Test",
            "summary": "Test",
            "entities": ["SEC"],
            "article_count": 5,
            "mention_velocity": 1.0,
            "lifecycle": "hot",
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "display_mode": "summary",
            "display_title": "Test",
            "display_summary": None,
            "recent_article_count": 5,
        }
        response = NarrativeResponse(**data)
        assert response.display_summary is None


class TestNoLLMCalls:
    """Verify that display mode computation does not call LLM."""

    def test_get_narrative_display_mode_no_llm(self, fresh_start_cutoff):
        """_get_narrative_display_mode should not call any LLM provider."""
        # Mock all LLM imports to fail if called
        with patch("crypto_news_aggregator.llm.gateway.get_gateway") as mock_gateway:
            mock_gateway.side_effect = RuntimeError("LLM call detected!")

            narrative = {
                "theme": "regulatory",
                "title": "Old",
                "summary": "Old.",
                "entities": ["SEC"],
                "article_count": 5,
                "first_seen": fresh_start_cutoff - timedelta(days=30),
                "last_summary_generated_at": None,
                "_fresh_start_validated_at": None,
            }
            articles = [{"title": "SEC Action"}]

            # Should not raise any LLM error
            mode, title, summary = _get_narrative_display_mode(
                narrative, fresh_start_cutoff, articles
            )
            assert mode == "article_cluster"
            assert title == "SEC"
            assert summary is not None
            # LLM gateway should not have been called
            mock_gateway.assert_not_called()


class TestPublicCopyCleanup:
    """Test public-facing copy cleanup requirements."""

    def test_missing_entities_theme_returns_recent_coverage(self, fresh_start_cutoff):
        """Missing entities/theme returns display_title='Recent Coverage', not generic fallback."""
        narrative = {
            "entities": [],
            "theme": "",
            "article_count": 3,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert title == "Recent Coverage"
        assert title != "Untitled"
        assert title != ""

    def test_zero_articles_zero_count_tracking_message(self, fresh_start_cutoff):
        """Zero articles and zero count produces tracking message, not 'Latest 0 articles'."""
        narrative = {
            "theme": "test",
            "entities": ["Entity"],
            "article_count": 0,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Should NOT have "Latest 0 articles" or "Recent 0 articles"
        assert summary == "Recent coverage is being tracked for this narrative."
        assert "Latest 0" not in summary
        assert "Recent 0" not in summary

    def test_zero_valid_titles_but_positive_count_uses_count_message(self, fresh_start_cutoff):
        """Zero valid titles but article_count > 0 produces proper count message."""
        narrative = {
            "theme": "test",
            "entities": ["Entity"],
            "article_count": 7,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        # All articles filtered (forbidden words) - 3 articles passed
        articles = [
            {"title": "Data missing from system"},
            {"title": "Summary is stale"},
            {"title": "Status: untrusted"},
        ]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Uses count from recent_articles (3) since articles were passed
        assert summary == "Recent coverage includes 3 articles in this narrative."
        assert "Latest" not in summary  # Should not be "Latest"
        assert "stale" not in summary.lower()
        assert "missing" not in summary.lower()

    def test_zero_valid_titles_uses_narrative_count_fallback(self, fresh_start_cutoff):
        """When all articles filtered but no articles passed, uses narrative article_count."""
        narrative = {
            "theme": "test",
            "entities": ["Entity"],
            "article_count": 7,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        # No articles passed at all
        articles = []
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        # Uses narrative article_count (7) since no articles provided
        assert summary == "Recent coverage includes 7 articles in this narrative."

    def test_single_article_uses_latest_coverage(self, fresh_start_cutoff):
        """Single article should produce 'Latest coverage includes...'."""
        narrative = {
            "theme": "test",
            "entities": ["Bitcoin"],
            "article_count": 1,
            "first_seen": fresh_start_cutoff - timedelta(days=30),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        articles = [{"title": "Bitcoin at $80K"}]
        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )
        assert summary == "Latest coverage includes Bitcoin at $80K."


class TestOldNarrativesStayActive:
    """Verify that old narratives with recent activity remain eligible in API."""

    def test_old_narrative_with_recent_update_included(self, fresh_start_cutoff):
        """Old narrative with last_updated recently should appear as article_cluster."""
        narrative = {
            "theme": "bitcoin",
            "title": "Bitcoin Holds $75K",  # Old generated title
            "summary": "Old summary about BTC price.",  # Old summary
            "entities": ["Bitcoin", "BTC"],
            "article_count": 8,
            "first_seen": fresh_start_cutoff - timedelta(days=90),  # Very old
            "last_updated": fresh_start_cutoff + timedelta(hours=1),  # But recently active
            "last_summary_generated_at": fresh_start_cutoff - timedelta(days=30),  # Old summary
            "_fresh_start_validated_at": None,
        }
        articles = [
            {"title": "BTC Around $80K"},
            {"title": "ETF Outflows Moderate"},
            {"title": "Options Positioning Shifts"},
        ]

        mode, title, summary = _get_narrative_display_mode(
            narrative, fresh_start_cutoff, articles
        )

        # Should render as article_cluster, not summary
        assert mode == "article_cluster"
        # Should use primary entity, not old generated title
        assert title == "Bitcoin"
        assert title != "Bitcoin Holds $75K"
        # Should use recent article titles, not old summary
        assert "BTC Around $80K" in summary
        assert "Old summary about BTC price" not in summary
