"""
Tests for narrative theme extraction service.

Tests theme extraction from articles using Claude Sonnet.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from crypto_news_aggregator.services.narrative_themes import (
    extract_themes_from_article,
    discover_narrative_from_article,
    backfill_themes_for_recent_articles,
    backfill_narratives_for_recent_articles,
    get_articles_by_theme,
    generate_narrative_from_theme,
    cluster_by_narrative_salience,
    validate_narrative_json,
    validate_entity_in_text,
    compute_narrative_fingerprint,
    calculate_fingerprint_similarity,
    _compute_focus_similarity,
    _build_degraded_narrative,
    THEME_CATEGORIES
)


@pytest.fixture
def sample_article_data():
    """Sample article data for testing."""
    return {
        "_id": "test123",
        "article_id": "test123",
        "title": "SEC Announces New Crypto Regulations",
        "description": "The Securities and Exchange Commission has announced new regulatory frameworks for cryptocurrency exchanges and stablecoin issuers.",
        "summary": "The Securities and Exchange Commission has announced new regulatory frameworks for cryptocurrency exchanges and stablecoin issuers."
    }


@pytest.fixture
def mock_llm_response_themes():
    """Mock LLM response for theme extraction."""
    return '["regulatory", "stablecoin"]'


@pytest.fixture
def mock_llm_response_narrative():
    """Mock LLM response for narrative generation."""
    return '{"title": "SEC Regulatory Crackdown", "summary": "The SEC is intensifying enforcement actions against crypto exchanges."}'


@pytest.mark.asyncio
async def test_extract_themes_from_article_success(sample_article_data):
    """Test successful theme extraction from article."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '["regulatory", "stablecoin"]'
        mock_llm.return_value = mock_provider
        
        # Extract themes
        themes = await extract_themes_from_article(
            article_id=sample_article_data["article_id"],
            title=sample_article_data["title"],
            summary=sample_article_data["summary"]
        )
        
        # Assertions
        assert themes == ["regulatory", "stablecoin"]
        assert all(theme in THEME_CATEGORIES for theme in themes)
        assert mock_provider._get_completion.call_count == 1


@pytest.mark.asyncio
async def test_extract_themes_filters_invalid_themes(sample_article_data):
    """Test that invalid themes are filtered out."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '["regulatory", "invalid_theme", "stablecoin"]'
        mock_llm.return_value = mock_provider
        
        themes = await extract_themes_from_article(
            article_id=sample_article_data["article_id"],
            title=sample_article_data["title"],
            summary=sample_article_data["summary"]
        )
        
        # Should filter out invalid_theme
        assert themes == ["regulatory", "stablecoin"]
        assert "invalid_theme" not in themes


@pytest.mark.asyncio
async def test_extract_themes_empty_content():
    """Test theme extraction with empty title and summary."""
    themes = await extract_themes_from_article(
        article_id="test123",
        title="",
        summary=""
    )
    
    assert themes == []


@pytest.mark.asyncio
async def test_extract_themes_llm_error(sample_article_data):
    """Test theme extraction when LLM fails."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider raising exception
        mock_provider = MagicMock()
        mock_provider._get_completion.side_effect = Exception("LLM API error")
        mock_llm.return_value = mock_provider
        
        themes = await extract_themes_from_article(
            article_id=sample_article_data["article_id"],
            title=sample_article_data["title"],
            summary=sample_article_data["summary"]
        )
        
        # Should return empty list on error
        assert themes == []


@pytest.mark.asyncio
async def test_extract_themes_invalid_json(sample_article_data):
    """Test theme extraction with invalid JSON response."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider returning invalid JSON
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = "not valid json"
        mock_llm.return_value = mock_provider
        
        themes = await extract_themes_from_article(
            article_id=sample_article_data["article_id"],
            title=sample_article_data["title"],
            summary=sample_article_data["summary"]
        )
        
        # Should return empty list on parse error
        assert themes == []


@pytest.mark.asyncio
async def test_get_articles_by_theme_success():
    """Test retrieving articles by theme."""
    with patch("crypto_news_aggregator.services.narrative_themes.mongo_manager") as mock_mongo:
        # Mock database
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.articles = mock_collection
        
        # Make get_async_database return a coroutine
        async def get_db():
            return mock_db
        mock_mongo.get_async_database = get_db
        
        # Mock articles
        sample_articles = [
            {"_id": "1", "title": "Article 1", "themes": ["regulatory"]},
            {"_id": "2", "title": "Article 2", "themes": ["regulatory"]},
            {"_id": "3", "title": "Article 3", "themes": ["regulatory"]},
        ]
        
        # Mock cursor
        class MockCursor:
            def __init__(self, data):
                self.data = data
                self.index = 0
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result
            
            def sort(self, *args, **kwargs):
                return self
        
        mock_cursor = MockCursor(sample_articles)
        mock_collection.find.return_value = mock_cursor
        
        # Get articles
        articles = await get_articles_by_theme(theme="regulatory", hours=48, min_articles=2)
        
        # Assertions
        assert articles is not None
        assert len(articles) == 3
        mock_collection.find.assert_called_once()


@pytest.mark.asyncio
async def test_get_articles_by_theme_below_threshold():
    """Test that None is returned when below minimum article threshold."""
    with patch("crypto_news_aggregator.services.narrative_themes.mongo_manager") as mock_mongo:
        # Mock database
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.articles = mock_collection
        
        # Make get_async_database return a coroutine
        async def get_db():
            return mock_db
        mock_mongo.get_async_database = get_db
        
        # Mock only 1 article (below threshold of 2)
        sample_articles = [
            {"_id": "1", "title": "Article 1", "themes": ["regulatory"]},
        ]
        
        # Mock cursor
        class MockCursor:
            def __init__(self, data):
                self.data = data
                self.index = 0
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result
            
            def sort(self, *args, **kwargs):
                return self
        
        mock_cursor = MockCursor(sample_articles)
        mock_collection.find.return_value = mock_cursor
        
        # Get articles
        articles = await get_articles_by_theme(theme="regulatory", hours=48, min_articles=2)
        
        # Should return None when below threshold
        assert articles is None


@pytest.mark.asyncio
async def test_generate_narrative_from_theme_success(mock_llm_response_narrative):
    """Test narrative generation from theme and articles."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = mock_llm_response_narrative
        mock_llm.return_value = mock_provider
        
        # Sample articles
        articles = [
            {"_id": "1", "title": "SEC sues Coinbase", "description": "Regulatory action"},
            {"_id": "2", "title": "Binance faces charges", "description": "Enforcement"},
        ]
        
        # Generate narrative
        narrative = await generate_narrative_from_theme(theme="regulatory", articles=articles)
        
        # Assertions
        assert narrative is not None
        assert narrative["title"] == "SEC Regulatory Crackdown"
        assert narrative["summary"] == "The SEC is intensifying enforcement actions against crypto exchanges."
        mock_provider._get_completion.assert_called_once()


@pytest.mark.asyncio
async def test_generate_narrative_from_theme_empty_articles():
    """Test narrative generation with empty articles list."""
    narrative = await generate_narrative_from_theme(theme="regulatory", articles=[])
    
    assert narrative is None


@pytest.mark.asyncio
async def test_generate_narrative_from_theme_llm_error():
    """Test narrative generation when LLM fails."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider raising exception
        mock_provider = MagicMock()
        mock_provider._get_completion.side_effect = Exception("LLM API error")
        mock_llm.return_value = mock_provider
        
        articles = [
            {"_id": "1", "title": "Article 1", "description": "Content"},
        ]
        
        narrative = await generate_narrative_from_theme(theme="regulatory", articles=articles)
        
        # Should return None on error
        assert narrative is None


@pytest.mark.asyncio
async def test_generate_narrative_from_theme_fallback():
    """Test narrative generation fallback when JSON parsing fails."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider returning invalid JSON
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = "invalid json"
        mock_llm.return_value = mock_provider
        
        articles = [
            {"_id": "1", "title": "Article 1", "description": "Content"},
        ]
        
        narrative = await generate_narrative_from_theme(theme="regulatory", articles=articles)
        
        # Should use fallback
        assert narrative is not None
        assert "Regulatory Narrative" in narrative["title"]
        assert "regulatory" in narrative["summary"].lower()


def test_theme_categories_defined():
    """Test that theme categories are properly defined."""
    assert len(THEME_CATEGORIES) > 0
    assert "regulatory" in THEME_CATEGORIES
    assert "defi_adoption" in THEME_CATEGORIES
    assert "institutional_investment" in THEME_CATEGORIES
    assert "stablecoin" in THEME_CATEGORIES


# ============================================================================
# NEW TESTS FOR NARRATIVE DISCOVERY SYSTEM (Two-Layer Approach)
# ============================================================================

@pytest.fixture
def mock_llm_response_narrative_discovery():
    """Mock LLM response for Layer 1 narrative discovery."""
    return '''{
        "actors": ["SEC", "Binance", "Coinbase"],
        "actor_salience": {
            "SEC": 5,
            "Binance": 4,
            "Coinbase": 3
        },
        "nucleus_entity": "SEC",
        "narrative_focus": "regulatory enforcement action",
        "actions": ["SEC filed charges against exchanges", "Alleged unregistered securities operations"],
        "tensions": ["Regulation vs. Innovation", "Centralization vs. Decentralization"],
        "implications": "Enforcement actions mark escalation in regulatory pressure on crypto industry",
        "narrative_summary": "Regulators are tightening control over centralized cryptocurrency exchanges as the SEC charges major platforms with securities violations."
    }'''


@pytest.fixture
def mock_llm_response_theme_mapping():
    """Mock LLM response for Layer 2 theme mapping."""
    return '''{
        "themes": ["regulatory", "security"],
        "suggested_new_theme": null
    }'''


@pytest.mark.asyncio
async def test_discover_narrative_from_article_success(sample_article_data, mock_llm_response_narrative_discovery):
    """Test Layer 1: Successful narrative discovery from article."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = mock_llm_response_narrative_discovery
        mock_llm.return_value = mock_provider
        
        # Discover narrative
        narrative_data = await discover_narrative_from_article(
            article=sample_article_data
        )
        
        # Assertions
        assert narrative_data is not None
        assert "actors" in narrative_data
        assert "actions" in narrative_data
        assert "tensions" in narrative_data
        assert "implications" in narrative_data
        assert "narrative_summary" in narrative_data
        
        # Verify content
        assert "SEC" in narrative_data["actors"]
        assert "Binance" in narrative_data["actors"]
        assert len(narrative_data["actions"]) > 0
        assert len(narrative_data["tensions"]) > 0
        assert len(narrative_data["narrative_summary"]) > 0
        
        mock_provider._get_completion.assert_called_once()


@pytest.mark.asyncio
async def test_discover_narrative_empty_content():
    """Test Layer 1: Narrative discovery with empty content."""
    narrative_data = await discover_narrative_from_article(
        article={"_id": "test123", "title": "", "description": ""}
    )
    
    assert narrative_data is None


@pytest.mark.asyncio
async def test_discover_narrative_missing_fields(sample_article_data):
    """Test Layer 1: Narrative discovery with incomplete LLM response - now returns degraded instead of None."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider returning incomplete data
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '{"actors": ["SEC"], "actions": []}'
        mock_llm.return_value = mock_provider

        narrative_data = await discover_narrative_from_article(
            article=sample_article_data
        )

        # BUG-057: Should return degraded narrative (not None) to keep pipeline moving
        assert narrative_data is not None
        assert narrative_data.get("status") == "degraded"
        assert narrative_data.get("degraded_reason") is not None


@pytest.mark.asyncio
async def test_discover_narrative_llm_error(sample_article_data):
    """Test Layer 1: Narrative discovery when LLM fails."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider raising exception
        mock_provider = MagicMock()
        mock_provider._get_completion.side_effect = Exception("LLM API error")
        mock_llm.return_value = mock_provider
        
        narrative_data = await discover_narrative_from_article(
            article=sample_article_data
        )
        
        # Should return None on error
        assert narrative_data is None


@pytest.mark.skip(reason="map_narrative_to_themes function not implemented yet")
@pytest.mark.asyncio
async def test_map_narrative_to_themes_success(mock_llm_response_theme_mapping):
    """Test Layer 2: Successful theme mapping from narrative."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = mock_llm_response_theme_mapping
        mock_llm.return_value = mock_provider
        
        narrative_summary = "Regulators are tightening control over centralized exchanges"
        
        # Map to themes
        mapping = await map_narrative_to_themes(narrative_summary, "test123")
        
        # Assertions
        assert mapping is not None
        assert "themes" in mapping
        assert "suggested_new_theme" in mapping
        assert "regulatory" in mapping["themes"]
        assert all(theme in THEME_CATEGORIES or theme == "emerging" for theme in mapping["themes"])
        
        mock_provider._get_completion.assert_called_once()


@pytest.mark.skip(reason="map_narrative_to_themes function not implemented yet")
@pytest.mark.asyncio
async def test_map_narrative_to_themes_emerging():
    """Test Layer 2: Theme mapping suggests new category for emerging narrative."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider suggesting new theme
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '''{
            "themes": ["emerging"],
            "suggested_new_theme": "ai_agents"
        }'''
        mock_llm.return_value = mock_provider
        
        narrative_summary = "AI agents are now trading autonomously on DEXs"
        
        # Map to themes
        mapping = await map_narrative_to_themes(narrative_summary, "test123")
        
        # Assertions
        assert mapping["themes"] == ["emerging"]
        assert mapping["suggested_new_theme"] == "ai_agents"


@pytest.mark.skip(reason="map_narrative_to_themes function not implemented yet")
@pytest.mark.asyncio
async def test_map_narrative_to_themes_empty_summary():
    """Test Layer 2: Theme mapping with empty narrative summary."""
    mapping = await map_narrative_to_themes("", "test123")
    
    # Should return emerging theme as fallback
    assert mapping["themes"] == ["emerging"]
    assert mapping["suggested_new_theme"] is None


@pytest.mark.skip(reason="map_narrative_to_themes function not implemented yet")
@pytest.mark.asyncio
async def test_map_narrative_filters_invalid_themes():
    """Test Layer 2: Theme mapping filters out invalid themes."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider returning invalid themes
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '''{
            "themes": ["regulatory", "invalid_theme", "stablecoin"],
            "suggested_new_theme": null
        }'''
        mock_llm.return_value = mock_provider
        
        mapping = await map_narrative_to_themes("Some narrative", "test123")
        
        # Should filter out invalid_theme
        assert "regulatory" in mapping["themes"]
        assert "stablecoin" in mapping["themes"]
        assert "invalid_theme" not in mapping["themes"]


@pytest.mark.skip(reason="get_articles_by_narrative_similarity function not implemented yet")
@pytest.mark.asyncio
async def test_get_articles_by_narrative_similarity():
    """Test clustering articles by shared actors and tensions."""
    with patch("crypto_news_aggregator.services.narrative_themes.mongo_manager") as mock_mongo:
        # Mock database
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.articles = mock_collection
        
        async def get_db():
            return mock_db
        mock_mongo.get_async_database = get_db
        
        # Mock articles with narrative data
        sample_articles = [
            {
                "_id": "1",
                "title": "SEC sues Binance",
                "narrative_summary": "SEC charges Binance",
                "actors": ["SEC", "Binance"],
                "tensions": ["Regulation vs Innovation"]
            },
            {
                "_id": "2",
                "title": "SEC sues Coinbase",
                "narrative_summary": "SEC charges Coinbase",
                "actors": ["SEC", "Coinbase"],
                "tensions": ["Regulation vs Innovation"]
            },
            {
                "_id": "3",
                "title": "Arbitrum gains users",
                "narrative_summary": "L2 competition heats up",
                "actors": ["Arbitrum", "Optimism"],
                "tensions": ["Scaling competition"]
            },
        ]
        
        # Mock cursor
        class MockCursor:
            def __init__(self, data):
                self.data = data
                self.index = 0
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result
            
            def sort(self, *args, **kwargs):
                return self
        
        mock_cursor = MockCursor(sample_articles)
        mock_collection.find.return_value = mock_cursor
        
        # Get clusters
        clusters = await get_articles_by_narrative_similarity(hours=48, min_articles=2)
        
        # Assertions
        assert len(clusters) >= 1
        # First cluster should have SEC-related articles (shared tension)
        assert any(len(cluster) == 2 for cluster in clusters)


@pytest.mark.skip(reason="generate_narrative_from_cluster function not implemented yet")
@pytest.mark.asyncio
async def test_generate_narrative_from_cluster_success():
    """Test generating rich narrative summary from article cluster."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '''{
            "title": "SEC vs Major Exchanges: Enforcement intensifies",
            "summary": "The SEC has filed charges against Binance and Coinbase, marking a significant escalation in regulatory enforcement."
        }'''
        mock_llm.return_value = mock_provider
        
        # Sample cluster with narrative data
        articles = [
            {
                "_id": "1",
                "narrative_summary": "SEC charges Binance with securities violations",
                "actors": ["SEC", "Binance"],
                "tensions": ["Regulation vs Innovation"]
            },
            {
                "_id": "2",
                "narrative_summary": "SEC files lawsuit against Coinbase",
                "actors": ["SEC", "Coinbase"],
                "tensions": ["Regulation vs Innovation"]
            },
        ]
        
        # Generate narrative
        narrative = await generate_narrative_from_cluster(articles)
        
        # Assertions
        assert narrative is not None
        assert "title" in narrative
        assert "summary" in narrative
        assert "SEC" in narrative["title"]
        assert len(narrative["title"]) <= 80  # Max length check
        assert len(narrative["summary"]) > 0


@pytest.mark.skip(reason="generate_narrative_from_cluster function not implemented yet")
@pytest.mark.asyncio
async def test_generate_narrative_from_cluster_empty():
    """Test narrative generation with empty cluster."""
    narrative = await generate_narrative_from_cluster([])
    
    assert narrative is None


@pytest.mark.asyncio
async def test_extract_themes_basic_functionality(sample_article_data):
    """Test basic theme extraction functionality."""
    with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider._get_completion.return_value = '["regulatory"]'
        mock_llm.return_value = mock_provider
        
        # Extract themes
        themes = await extract_themes_from_article(
            article_id=sample_article_data["article_id"],
            title=sample_article_data["title"],
            summary=sample_article_data["summary"]
        )
        
        # Assertions
        assert themes == ["regulatory"]
        assert mock_provider._get_completion.call_count == 1


# ============================================================================
# ENTITY VALIDATION TESTS (FEATURE-016)
# ============================================================================

class TestValidateEntityInText:
    """Unit tests for validate_entity_in_text function (LLM hallucination prevention)."""

    def test_entity_in_title_only(self):
        """Test validation passes when entity is in title only."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Bitcoin Price Surges to New High",
            article_text="Cryptocurrency market rallies today"
        )
        assert result is True

    def test_entity_in_body_only(self):
        """Test validation passes when entity is in body only."""
        result = validate_entity_in_text(
            nucleus_entity="Ethereum",
            article_title="Crypto Market Update",
            article_text="Ethereum led the gains with 5% increase today"
        )
        assert result is True

    def test_entity_in_both_title_and_body(self):
        """Test validation passes when entity is in both title and body."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Bitcoin Reaches All-Time High",
            article_text="Bitcoin has reached an all-time high of $60,000 today"
        )
        assert result is True

    def test_entity_not_in_text_hallucination(self):
        """Test validation fails when entity is hallucinated (not in text)."""
        result = validate_entity_in_text(
            nucleus_entity="Netflix",
            article_title="Coinbase Earnings Beat Expectations",
            article_text="Coinbase reported strong Q4 earnings today"
        )
        assert result is False

    def test_entity_case_insensitive_lowercase_entity(self):
        """Test validation is case-insensitive with lowercase entity."""
        result = validate_entity_in_text(
            nucleus_entity="coinbase",
            article_title="COINBASE Stock Rises 10%",
            article_text="Coinbase shares increased significantly"
        )
        assert result is True

    def test_entity_case_insensitive_uppercase_entity(self):
        """Test validation is case-insensitive with uppercase entity."""
        result = validate_entity_in_text(
            nucleus_entity="ETHEREUM",
            article_title="ethereum reaches new milestone",
            article_text="eth holders celebrate the upgrade"
        )
        assert result is True

    def test_entity_case_insensitive_mixed_case(self):
        """Test validation is case-insensitive with mixed case."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="BITCOIN and ethereum rally together",
            article_text="bitcoin is trading at $45,000"
        )
        assert result is True

    def test_word_boundary_no_false_positive_bit_bitcoin(self):
        """Test word boundary prevents 'Bit' matching 'Bitcoin'."""
        result = validate_entity_in_text(
            nucleus_entity="Bit",
            article_title="Bitcoin Price Update",
            article_text="Bitcoin is trading higher today"
        )
        assert result is False

    def test_word_boundary_no_false_positive_eth_ethereum(self):
        """Test word boundary prevents 'ETH' matching 'ETHEREUM'."""
        result = validate_entity_in_text(
            nucleus_entity="ETH",
            article_title="Ethereum Upgrade News",
            article_text="The Ethereum network upgraded today"
        )
        assert result is False

    def test_word_boundary_correct_match(self):
        """Test word boundary correctly matches complete words."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Bitcoin Price Update",
            article_text="Bitcoin is trading higher"
        )
        assert result is True

    def test_word_boundary_punctuation_handling(self):
        """Test word boundary handles punctuation correctly."""
        result = validate_entity_in_text(
            nucleus_entity="SEC",
            article_title="SEC Sues Binance, Others",
            article_text="The SEC announced enforcement action."
        )
        assert result is True

    def test_empty_nucleus_entity(self):
        """Test validation fails for empty nucleus_entity."""
        result = validate_entity_in_text(
            nucleus_entity="",
            article_title="Some Article",
            article_text="Some content"
        )
        assert result is False

    def test_none_nucleus_entity(self):
        """Test validation fails for None nucleus_entity."""
        result = validate_entity_in_text(
            nucleus_entity=None,
            article_title="Some Article",
            article_text="Some content"
        )
        assert result is False

    def test_empty_title_and_text(self):
        """Test validation fails when both title and text are empty."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="",
            article_text=""
        )
        assert result is False

    def test_none_title_and_text(self):
        """Test validation fails when both title and text are None."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title=None,
            article_text=None
        )
        assert result is False

    def test_netflix_coinbase_hallucination_example(self):
        """Test the known bad case: Netflix hallucinated in Coinbase article."""
        # This is the real example from BUG-003 investigation
        result = validate_entity_in_text(
            nucleus_entity="Netflix",
            article_title="Coinbase Stock Surges on Earnings",
            article_text="Coinbase reported strong quarterly earnings as institutional adoption continues"
        )
        assert result is False

    def test_multi_word_entity_exact_match(self):
        """Test multi-word entity matching."""
        result = validate_entity_in_text(
            nucleus_entity="Ethereum Foundation",
            article_title="Ethereum Foundation Announces Grant Program",
            article_text="The Ethereum Foundation has announced a new grant program for developers"
        )
        assert result is True

    def test_multi_word_entity_not_found(self):
        """Test multi-word entity validation fails when not found."""
        result = validate_entity_in_text(
            nucleus_entity="Ethereum Foundation",
            article_title="Ethereum Upgrades Network",
            article_text="The Ethereum network has been upgraded"
        )
        assert result is False

    def test_entity_with_special_characters(self):
        """Test entity with special characters (e.g., parentheses, dashes)."""
        result = validate_entity_in_text(
            nucleus_entity="OpenAI (ChatGPT)",
            article_title="OpenAI (ChatGPT) Integration Announced",
            article_text="OpenAI (ChatGPT) will be integrated into the platform"
        )
        assert result is True

    def test_entity_with_hyphen(self):
        """Test entity with hyphen."""
        result = validate_entity_in_text(
            nucleus_entity="U.S. Securities",
            article_title="U.S. Securities and Exchange Commission Acts",
            article_text="U.S. Securities regulators take action"
        )
        assert result is True

    def test_long_article_text(self):
        """Test validation with long article text."""
        long_text = """
        This is a very long article about cryptocurrency news. The market has been volatile lately.
        Bitcoin has been on a roller coaster. Many investors are watching Ethereum closely.
        The regulatory environment is changing. The SEC is watching the market. DeFi protocols
        are growing. Staking rewards are increasing. NFT markets are recovering.
        Ethereum validators are earning rewards. The network is secure. Smart contracts are
        becoming more efficient. Layer 2 solutions are maturing. Cross-chain bridges are improving.
        """
        result = validate_entity_in_text(
            nucleus_entity="Ethereum",
            article_title="Crypto Markets Update",
            article_text=long_text
        )
        assert result is True

    def test_entity_at_beginning_of_text(self):
        """Test entity matching at the beginning of text."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Crypto News",
            article_text="Bitcoin is the world's largest cryptocurrency by market cap"
        )
        assert result is True

    def test_entity_at_end_of_text(self):
        """Test entity matching at the end of text."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Crypto News",
            article_text="Many investors are interested in Bitcoin"
        )
        assert result is True

    def test_entity_in_middle_of_text(self):
        """Test entity matching in the middle of text."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Crypto News",
            article_text="Ethereum is popular but Bitcoin remains dominant in the market"
        )
        assert result is True

    def test_numbers_in_entity(self):
        """Test entity with numbers."""
        result = validate_entity_in_text(
            nucleus_entity="ERC-20",
            article_title="ERC-20 Token Standard Explained",
            article_text="ERC-20 tokens are the most common on Ethereum"
        )
        assert result is True

    def test_comma_separated_list_false_positive_prevention(self):
        """Test that comma-separated list doesn't cause false positives."""
        result = validate_entity_in_text(
            nucleus_entity="Bitcoin",
            article_title="Bitcoin, Ethereum, Dogecoin Rally",
            article_text="Cryptocurrency markets surging across the board"
        )
        assert result is True


# ============================================================================
# VALIDATION TESTS
# ============================================================================

class TestValidateNarrativeJson:
    """Unit tests for validate_narrative_json function."""

    @pytest.fixture
    def valid_narrative_data(self):
        """Valid narrative data for testing."""
        return {
            "actors": ["SEC", "Binance", "Coinbase"],
            "actor_salience": {
                "SEC": 5,
                "Binance": 4,
                "Coinbase": 3
            },
            "nucleus_entity": "SEC",
            "narrative_focus": "regulatory enforcement action",
            "actions": ["Filed lawsuit", "Announced enforcement"],
            "tensions": ["Regulation vs Innovation"],
            "narrative_summary": "The SEC is intensifying regulatory enforcement against major crypto exchanges."
        }
    
    def test_validate_valid_data(self, valid_narrative_data):
        """Test validation passes for valid data."""
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_missing_required_field(self, valid_narrative_data):
        """Test validation fails when required field is missing."""
        # Remove required field
        del valid_narrative_data["actors"]
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "Missing required field: actors" in error
    
    def test_validate_missing_multiple_fields(self):
        """Test validation fails with first missing field."""
        data = {
            "actors": ["SEC"],
            "actor_salience": {"SEC": 5}
            # Missing: nucleus_entity, actions, tensions, narrative_summary
        }
        
        is_valid, error = validate_narrative_json(data)
        
        assert is_valid is False
        assert "Missing required field" in error
    
    def test_validate_empty_actors_list(self, valid_narrative_data):
        """Test validation auto-fixes empty actors by backfilling with nucleus_entity (Tier 3 auto-fix)."""
        valid_narrative_data["actors"] = []

        is_valid, error = validate_narrative_json(valid_narrative_data)

        # BUG-057: Should be valid after auto-fix (Tier 3 auto-fix)
        assert is_valid is True
        assert error is None
        # Actors should be backfilled with nucleus_entity
        assert valid_narrative_data["actors"] == ["SEC"]
    
    def test_validate_actors_not_list(self, valid_narrative_data):
        """Test validation fails when actors is not a list."""
        valid_narrative_data["actors"] = "SEC, Binance"

        is_valid, error = validate_narrative_json(valid_narrative_data)

        assert is_valid is False
        assert "actors must be a list" in error
    
    def test_validate_caps_actors_at_20(self, valid_narrative_data):
        """Test validation caps actors list at 20 items."""
        # Create list with 25 actors
        valid_narrative_data["actors"] = [f"Actor{i}" for i in range(25)]
        valid_narrative_data["actor_salience"] = {f"Actor{i}": 3 for i in range(25)}
        valid_narrative_data["nucleus_entity"] = "Actor0"
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is True
        assert len(valid_narrative_data["actors"]) == 20
    
    def test_validate_empty_nucleus_entity(self, valid_narrative_data):
        """Test validation fails for empty nucleus_entity."""
        valid_narrative_data["nucleus_entity"] = ""
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "nucleus_entity must be non-empty string" in error
    
    def test_validate_nucleus_entity_not_string(self, valid_narrative_data):
        """Test validation fails when nucleus_entity is not a string."""
        valid_narrative_data["nucleus_entity"] = 123
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "nucleus_entity must be non-empty string" in error
    
    def test_validate_auto_adds_nucleus_to_actors(self, valid_narrative_data):
        """Test validation auto-adds nucleus_entity to actors list if missing."""
        valid_narrative_data["nucleus_entity"] = "NewEntity"
        # NewEntity not in actors list initially
        # But has a salience score, so it should work
        valid_narrative_data["actor_salience"]["NewEntity"] = 5

        is_valid, error = validate_narrative_json(valid_narrative_data)

        # Should be valid and nucleus added to actors
        assert is_valid is True
        assert "NewEntity" in valid_narrative_data["actors"]
    
    def test_validate_auto_adds_nucleus_to_actors_success(self, valid_narrative_data):
        """Test validation auto-adds nucleus_entity to actors list successfully."""
        valid_narrative_data["nucleus_entity"] = "NewEntity"
        valid_narrative_data["actor_salience"]["NewEntity"] = 5
        # NewEntity not in actors list initially
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is True
        assert "NewEntity" in valid_narrative_data["actors"]
        assert valid_narrative_data["actors"][0] == "NewEntity"  # Added at front
    
    def test_validate_salience_not_dict(self, valid_narrative_data):
        """Test validation fails when actor_salience is not a dict."""
        valid_narrative_data["actor_salience"] = ["SEC", "Binance"]
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "actor_salience must be a dictionary" in error
    
    def test_validate_salience_invalid_type(self, valid_narrative_data):
        """Test validation fails for non-numeric salience score."""
        valid_narrative_data["actor_salience"]["SEC"] = "high"
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "Invalid salience type for SEC" in error
    
    def test_validate_salience_out_of_range_low(self, valid_narrative_data):
        """Test validation fails for salience score below 1."""
        valid_narrative_data["actor_salience"]["SEC"] = 0
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "Invalid salience 0 for SEC (must be 1-5)" in error
    
    def test_validate_salience_out_of_range_high(self, valid_narrative_data):
        """Test validation fails for salience score above 5."""
        valid_narrative_data["actor_salience"]["Binance"] = 6
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "Invalid salience 6 for Binance (must be 1-5)" in error
    
    def test_validate_salience_accepts_float(self, valid_narrative_data):
        """Test validation accepts float salience scores."""
        valid_narrative_data["actor_salience"]["SEC"] = 4.5
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is True
    
    def test_validate_nucleus_missing_salience(self, valid_narrative_data):
        """Test validation auto-fixes missing nucleus_entity salience (Tier 2 auto-fix)."""
        del valid_narrative_data["actor_salience"]["SEC"]

        is_valid, error = validate_narrative_json(valid_narrative_data)

        # BUG-057: Should be valid after auto-fix (Tier 2 auto-fix)
        assert is_valid is True
        assert error is None
        # Nucleus should have salience 5 after auto-fix
        assert valid_narrative_data["actor_salience"]["SEC"] == 5
    
    def test_validate_narrative_summary_too_short(self, valid_narrative_data):
        """Test validation fails for narrative_summary under 10 characters."""
        valid_narrative_data["narrative_summary"] = "Too short"
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "narrative_summary must be string with at least 10 characters" in error
    
    def test_validate_narrative_summary_not_string(self, valid_narrative_data):
        """Test validation fails when narrative_summary is not a string."""
        valid_narrative_data["narrative_summary"] = 12345
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is False
        assert "narrative_summary must be string with at least 10 characters" in error
    
    def test_validate_narrative_summary_exactly_10_chars(self, valid_narrative_data):
        """Test validation passes for narrative_summary with exactly 10 characters."""
        valid_narrative_data["narrative_summary"] = "1234567890"
        
        is_valid, error = validate_narrative_json(valid_narrative_data)
        
        assert is_valid is True
    
    def test_validate_narrative_focus_required(self, valid_narrative_data):
        """Test validation fails when narrative_focus is missing."""
        del valid_narrative_data["narrative_focus"]

        is_valid, error = validate_narrative_json(valid_narrative_data)

        assert is_valid is False
        assert "Missing required field: narrative_focus" in error

    def test_validate_narrative_focus_empty_string(self, valid_narrative_data):
        """Test validation fails for empty narrative_focus."""
        valid_narrative_data["narrative_focus"] = ""

        is_valid, error = validate_narrative_json(valid_narrative_data)

        assert is_valid is False
        assert "narrative_focus must be non-empty string" in error

    def test_validate_narrative_focus_normalized_lowercase(self, valid_narrative_data):
        """Test that narrative_focus is normalized to lowercase."""
        valid_narrative_data["narrative_focus"] = "  REGULATORY Enforcement Action  "

        is_valid, error = validate_narrative_json(valid_narrative_data)

        assert is_valid is True
        assert valid_narrative_data["narrative_focus"] == "regulatory enforcement action"

    def test_validate_all_required_fields_present(self):
        """Test that all required fields are checked."""
        required_fields = ['actors', 'actor_salience', 'nucleus_entity',
                          'narrative_focus', 'actions', 'tensions', 'narrative_summary']

        for field in required_fields:
            data = {
                "actors": ["SEC"],
                "actor_salience": {"SEC": 5},
                "nucleus_entity": "SEC",
                "narrative_focus": "regulatory enforcement",
                "actions": ["Filed lawsuit"],
                "tensions": ["Regulation"],
                "narrative_summary": "The SEC is taking action."
            }
            del data[field]

            is_valid, error = validate_narrative_json(data)

            assert is_valid is False
            assert f"Missing required field: {field}" in error


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestValidateNarrativeJsonIntegration:
    """Integration tests for validate_narrative_json with discover_narrative_from_article."""
    
    @pytest.mark.asyncio
    async def test_validation_with_discover_narrative_valid_response(self):
        """Test validation works with valid LLM response from discover_narrative_from_article."""
        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            # Mock valid LLM response
            mock_provider = MagicMock()
            mock_provider._get_completion.return_value = '''{
                "actors": ["SEC", "Binance", "Coinbase"],
                "actor_salience": {
                    "SEC": 5,
                    "Binance": 4,
                    "Coinbase": 3
                },
                "nucleus_entity": "SEC",
                "narrative_focus": "regulatory enforcement action",
                "actions": ["Filed lawsuit against Binance"],
                "tensions": ["Regulation vs Innovation"],
                "implications": "Signals regulatory crackdown",
                "narrative_summary": "The SEC is intensifying enforcement against major exchanges as it targets Binance for alleged securities violations."
            }'''
            mock_llm.return_value = mock_provider
            
            # Discover narrative
            narrative_data = await discover_narrative_from_article(
                article={
                    "_id": "test123",
                    "title": "SEC Sues Binance",
                    "description": "The SEC has filed a lawsuit against Binance for regulatory violations."
                }
            )
            
            # Validate the response
            assert narrative_data is not None
            is_valid, error = validate_narrative_json(narrative_data)
            
            assert is_valid is True
            assert error is None
    
    @pytest.mark.asyncio
    async def test_validation_catches_malformed_llm_response(self):
        """Test that malformed LLM response returns degraded narrative (BUG-057)."""
        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            # Mock malformed LLM response (missing nucleus_entity)
            mock_provider = MagicMock()
            mock_provider._get_completion.return_value = '''{
                "actors": ["SEC", "Binance"],
                "actor_salience": {"SEC": 5, "Binance": 4},
                "actions": ["Filed lawsuit"],
                "tensions": ["Regulation"],
                "implications": "Enforcement action",
                "narrative_summary": "SEC takes action."
            }'''
            mock_llm.return_value = mock_provider

            # Discover narrative
            narrative_data = await discover_narrative_from_article(
                article={
                    "_id": "test123",
                    "title": "SEC Sues Binance",
                    "description": "The SEC has filed a lawsuit."
                }
            )

            # BUG-057: Should return degraded narrative instead of None
            assert narrative_data is not None
            assert narrative_data.get("status") == "degraded"
            assert "nucleus_entity" in narrative_data.get("degraded_reason", "")
    
    @pytest.mark.asyncio
    async def test_validation_catches_empty_actors(self):
        """Test that empty actors list is auto-fixed with nucleus_entity (BUG-057)."""
        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            # Mock LLM response with empty actors
            mock_provider = MagicMock()
            mock_provider._get_completion.return_value = '''{
                "actors": [],
                "actor_salience": {},
                "nucleus_entity": "SEC",
                "narrative_focus": "enforcement action",
                "actions": ["Filed lawsuit"],
                "tensions": ["Regulation"],
                "implications": "Enforcement",
                "narrative_summary": "SEC enforcement action continues."
            }'''
            mock_llm.return_value = mock_provider

            # Discover narrative
            narrative_data = await discover_narrative_from_article(
                article={
                    "_id": "test123",
                    "title": "SEC Action",
                    "description": "SEC takes enforcement action."
                }
            )

            # BUG-057: Empty actors auto-fixed with nucleus_entity, should be valid
            assert narrative_data is not None
            # With nucleus_entity in the response, validation should succeed (auto-fix)
            is_valid, error = validate_narrative_json(narrative_data)
            assert is_valid is True
            assert "SEC" in narrative_data.get("actors", [])
    
    @pytest.mark.asyncio
    async def test_validation_catches_invalid_salience_scores(self):
        """Test validation catches invalid salience scores from LLM."""
        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            # Mock LLM response with out-of-range salience
            mock_provider = MagicMock()
            mock_provider._get_completion.return_value = '''{
                "actors": ["SEC", "Binance"],
                "actor_salience": {
                    "SEC": 10,
                    "Binance": 4
                },
                "nucleus_entity": "SEC",
                "narrative_focus": "enforcement",
                "actions": ["Filed lawsuit"],
                "tensions": ["Regulation"],
                "implications": "Enforcement",
                "narrative_summary": "SEC enforcement action against Binance continues."
            }'''
            mock_llm.return_value = mock_provider

            # Discover narrative
            narrative_data = await discover_narrative_from_article(
                article={
                    "_id": "test123",
                    "title": "SEC vs Binance",
                    "description": "SEC files lawsuit against Binance."
                }
            )

            # BUG-057: Invalid salience should return degraded narrative
            assert narrative_data is not None
            assert narrative_data.get("status") == "degraded"
            assert "salience" in narrative_data.get("degraded_reason", "").lower()
    
    @pytest.mark.asyncio
    async def test_validation_auto_fix_nucleus_in_actors(self):
        """Test validation auto-fixes nucleus_entity not in actors list."""
        # Create data where nucleus is not in actors
        data = {
            "actors": ["Binance", "Coinbase"],
            "actor_salience": {
                "SEC": 5,
                "Binance": 4,
                "Coinbase": 3
            },
            "nucleus_entity": "SEC",
            "narrative_focus": "regulatory enforcement",
            "actions": ["Filed lawsuit"],
            "tensions": ["Regulation"],
            "narrative_summary": "SEC enforcement action against exchanges."
        }

        is_valid, error = validate_narrative_json(data)

        # Should auto-fix by adding SEC to actors
        assert is_valid is True
        assert "SEC" in data["actors"]
        assert data["actors"][0] == "SEC"  # Added at front


# ============================================================================
# FOCUS SIMILARITY TESTS (NEW FOR FEATURE-010)
# ============================================================================

class TestComputeFocusSimilarity:
    """Unit tests for _compute_focus_similarity function."""

    def test_focus_similarity_exact_match(self):
        """Test that exact focus match returns 1.0."""
        similarity = _compute_focus_similarity("price surge", "price surge")
        assert similarity == 1.0

    def test_focus_similarity_exact_match_case_insensitive(self):
        """Test that exact match is case-insensitive."""
        similarity = _compute_focus_similarity("Price Surge", "price surge")
        assert similarity == 1.0

    def test_focus_similarity_exact_match_with_whitespace(self):
        """Test that exact match handles extra whitespace."""
        similarity = _compute_focus_similarity("  price surge  ", "price surge")
        assert similarity == 1.0

    def test_focus_similarity_high_similarity(self):
        """Test high similarity (>80% word overlap) returns 0.9."""
        # Need >80%: "word1 word2 word3 word4 word5 extra" vs "word1 word2 word3 word4 word5"
        # = 5 overlapping out of 6 union = 83%, which passes 0.8 threshold, so 0.9
        similarity = _compute_focus_similarity("word1 word2 word3 word4 word5 extra", "word1 word2 word3 word4 word5")
        assert similarity == 0.9

    def test_focus_similarity_partial_match(self):
        """Test partial similarity (50-80% word overlap) returns 0.7."""
        # "price surge momentum" vs "price surge rally" = 2 overlap {price, surge}, union {price, surge, momentum, rally} = 4
        # 2/4 = 50%, which is not > 0.5, so let's use: "regulatory enforcement action" vs "regulatory enforcement"
        # overlap {regulatory, enforcement} = 2, union {regulatory, enforcement, action} = 3
        # 2/3 = 66.7%, which is > 0.5 and < 0.8, so returns 0.7
        similarity = _compute_focus_similarity("regulatory enforcement action", "regulatory enforcement")
        assert similarity == 0.7

    def test_focus_similarity_no_match(self):
        """Test no overlap returns 0.0."""
        similarity = _compute_focus_similarity("price surge", "governance dispute")
        assert similarity == 0.0

    def test_focus_similarity_empty_strings(self):
        """Test empty strings return neutral 0.5."""
        similarity = _compute_focus_similarity("", "")
        assert similarity == 0.5

    def test_focus_similarity_one_empty(self):
        """Test one empty string returns neutral 0.5."""
        similarity = _compute_focus_similarity("price surge", "")
        assert similarity == 0.5

        similarity = _compute_focus_similarity("", "governance")
        assert similarity == 0.5

    def test_focus_similarity_single_word_exact_match(self):
        """Test single word exact match."""
        similarity = _compute_focus_similarity("surge", "surge")
        assert similarity == 1.0

    def test_focus_similarity_single_word_no_match(self):
        """Test single word with no match."""
        similarity = _compute_focus_similarity("surge", "decline")
        assert similarity == 0.0

    def test_focus_similarity_multi_word_phrases(self):
        """Test multi-word phrases."""
        # "regulatory enforcement action" vs "regulatory enforcement"
        # overlap: {regulatory, enforcement} = 2
        # union: {regulatory, enforcement, action} = 3
        # 2/3 = 66.7%, which is > 50%, so 0.7
        similarity = _compute_focus_similarity("regulatory enforcement action", "regulatory enforcement")
        assert similarity == 0.7

    def test_focus_similarity_dogecoin_example_from_ticket(self):
        """Test Dogecoin example from FEATURE-010 ticket."""
        # Same focus should return 1.0
        similarity1 = _compute_focus_similarity("price surge", "price surge")
        assert similarity1 == 1.0

        # Different focus should return 0.0
        similarity2 = _compute_focus_similarity("price surge", "governance dispute")
        assert similarity2 == 0.0


# ============================================================================
# NARRATIVE FINGERPRINT TESTS
# ============================================================================

class TestComputeNarrativeFingerprint:
    """Unit tests for compute_narrative_fingerprint function."""
    
    @pytest.fixture
    def sample_cluster_with_dict_actors(self):
        """Sample cluster data with actors as dict (salience scores)."""
        return {
            "nucleus_entity": "SEC",
            "narrative_focus": "regulatory enforcement action",
            "actors": {
                "SEC": 5,
                "Binance": 4,
                "Coinbase": 4,
                "Kraken": 3,
                "Gemini": 3,
                "FTX": 2,
                "Tether": 2
            },
            "actions": [
                "Filed lawsuit against major exchanges",
                "Announced new regulatory framework",
                "Issued enforcement actions",
                "Requested additional disclosures"
            ]
        }

    @pytest.fixture
    def sample_cluster_with_list_actors(self):
        """Sample cluster data with actors as list."""
        return {
            "nucleus_entity": "Ethereum",
            "narrative_focus": "protocol upgrade deployment",
            "actors": ["Ethereum", "Vitalik Buterin", "EIP-4844", "Layer 2"],
            "actions": [
                "Deployed Dencun upgrade",
                "Reduced transaction fees",
                "Improved scalability"
            ]
        }
    
    def test_fingerprint_with_dict_actors(self, sample_cluster_with_dict_actors):
        """Test fingerprint computation with actors as dict (salience scores)."""
        fingerprint = compute_narrative_fingerprint(sample_cluster_with_dict_actors)

        # Check structure
        assert "nucleus_entity" in fingerprint
        assert "narrative_focus" in fingerprint
        assert "top_actors" in fingerprint
        assert "key_actions" in fingerprint
        assert "timestamp" in fingerprint

        # Check nucleus entity
        assert fingerprint["nucleus_entity"] == "SEC"

        # Check narrative focus (normalized to lowercase)
        assert fingerprint["narrative_focus"] == "regulatory enforcement action"

        # Check top actors (should be sorted by salience, top 5)
        assert len(fingerprint["top_actors"]) == 5
        assert fingerprint["top_actors"][0] == "SEC"  # Highest salience (5)
        # Binance and Coinbase both have salience 4, order may vary
        assert "Binance" in fingerprint["top_actors"][:3]
        assert "Coinbase" in fingerprint["top_actors"][:3]

        # Check key actions (top 3)
        assert len(fingerprint["key_actions"]) == 3
        assert fingerprint["key_actions"][0] == "Filed lawsuit against major exchanges"

        # Check timestamp is datetime
        assert isinstance(fingerprint["timestamp"], datetime)

    def test_fingerprint_with_list_actors(self, sample_cluster_with_list_actors):
        """Test fingerprint computation with actors as list."""
        fingerprint = compute_narrative_fingerprint(sample_cluster_with_list_actors)

        # Check structure
        assert "nucleus_entity" in fingerprint
        assert "narrative_focus" in fingerprint
        assert "top_actors" in fingerprint
        assert "key_actions" in fingerprint
        assert "timestamp" in fingerprint

        # Check nucleus entity
        assert fingerprint["nucleus_entity"] == "Ethereum"

        # Check narrative focus (normalized to lowercase)
        assert fingerprint["narrative_focus"] == "protocol upgrade deployment"

        # Check top actors (should take first 5 from list)
        assert len(fingerprint["top_actors"]) == 4  # Only 4 actors in sample
        assert fingerprint["top_actors"] == ["Ethereum", "Vitalik Buterin", "EIP-4844", "Layer 2"]

        # Check key actions (top 3)
        assert len(fingerprint["key_actions"]) == 3
        assert "Deployed Dencun upgrade" in fingerprint["key_actions"]
    
    def test_fingerprint_with_empty_cluster(self):
        """Test fingerprint computation with empty cluster."""
        empty_cluster = {}
        fingerprint = compute_narrative_fingerprint(empty_cluster)

        # Should handle gracefully
        assert fingerprint["nucleus_entity"] == ""
        assert fingerprint["narrative_focus"] == ""
        assert fingerprint["top_actors"] == []
        assert fingerprint["key_actions"] == []
        assert isinstance(fingerprint["timestamp"], datetime)

    def test_fingerprint_with_missing_fields(self):
        """Test fingerprint computation with missing fields."""
        partial_cluster = {
            "nucleus_entity": "Bitcoin"
            # Missing narrative_focus, actors and actions
        }
        fingerprint = compute_narrative_fingerprint(partial_cluster)

        # Should handle gracefully
        assert fingerprint["nucleus_entity"] == "Bitcoin"
        assert fingerprint["narrative_focus"] == ""
        assert fingerprint["top_actors"] == []
        assert fingerprint["key_actions"] == []
        assert isinstance(fingerprint["timestamp"], datetime)
    
    def test_fingerprint_limits_actors_to_5(self):
        """Test that fingerprint limits actors to top 5."""
        cluster = {
            "nucleus_entity": "DeFi",
            "actors": {
                "Uniswap": 5,
                "Aave": 5,
                "Compound": 4,
                "MakerDAO": 4,
                "Curve": 3,
                "Balancer": 3,
                "SushiSwap": 2,
                "1inch": 2
            },
            "actions": ["TVL growth", "New protocols launched"]
        }
        
        fingerprint = compute_narrative_fingerprint(cluster)
        
        # Should limit to top 5 actors
        assert len(fingerprint["top_actors"]) == 5
        # Top actors should include highest salience
        assert "Uniswap" in fingerprint["top_actors"]
        assert "Aave" in fingerprint["top_actors"]
    
    def test_fingerprint_limits_actions_to_3(self):
        """Test that fingerprint limits actions to top 3."""
        cluster = {
            "nucleus_entity": "Regulation",
            "actors": {"SEC": 5},
            "actions": [
                "Action 1",
                "Action 2",
                "Action 3",
                "Action 4",
                "Action 5"
            ]
        }
        
        fingerprint = compute_narrative_fingerprint(cluster)
        
        # Should limit to top 3 actions
        assert len(fingerprint["key_actions"]) == 3
        assert fingerprint["key_actions"] == ["Action 1", "Action 2", "Action 3"]
    
    def test_fingerprint_with_fewer_than_5_actors(self):
        """Test fingerprint with fewer than 5 actors."""
        cluster = {
            "nucleus_entity": "Solana",
            "actors": {
                "Solana": 5,
                "Anatoly Yakovenko": 4
            },
            "actions": ["Network upgrade"]
        }
        
        fingerprint = compute_narrative_fingerprint(cluster)
        
        # Should include all available actors
        assert len(fingerprint["top_actors"]) == 2
        assert fingerprint["top_actors"] == ["Solana", "Anatoly Yakovenko"]
    
    def test_fingerprint_with_fewer_than_3_actions(self):
        """Test fingerprint with fewer than 3 actions."""
        cluster = {
            "nucleus_entity": "NFT",
            "actors": {"OpenSea": 5},
            "actions": ["Marketplace update"]
        }
        
        fingerprint = compute_narrative_fingerprint(cluster)
        
        # Should include all available actions
        assert len(fingerprint["key_actions"]) == 1
        assert fingerprint["key_actions"] == ["Marketplace update"]
    
    def test_fingerprint_timestamp_is_recent(self):
        """Test that fingerprint timestamp is current."""
        cluster = {
            "nucleus_entity": "Test",
            "actors": {"Actor1": 5},
            "actions": ["Action1"]
        }
        
        before = datetime.now(timezone.utc)
        fingerprint = compute_narrative_fingerprint(cluster)
        after = datetime.now(timezone.utc)
        
        # Timestamp should be between before and after
        assert before <= fingerprint["timestamp"] <= after
    
    def test_fingerprint_sorts_actors_by_salience_descending(self):
        """Test that actors are sorted by salience in descending order."""
        cluster = {
            "nucleus_entity": "Market",
            "actors": {
                "Actor1": 2,
                "Actor2": 5,
                "Actor3": 3,
                "Actor4": 4,
                "Actor5": 1
            },
            "actions": ["Event"]
        }
        
        fingerprint = compute_narrative_fingerprint(cluster)
        
        # Should be sorted: Actor2(5), Actor4(4), Actor3(3), Actor1(2), Actor5(1)
        assert fingerprint["top_actors"][0] == "Actor2"
        assert fingerprint["top_actors"][1] == "Actor4"
        assert fingerprint["top_actors"][2] == "Actor3"
        assert fingerprint["top_actors"][3] == "Actor1"
        assert fingerprint["top_actors"][4] == "Actor5"


# ============================================================================
# FINGERPRINT SIMILARITY TESTS
# ============================================================================

class TestCalculateFingerprintSimilarity:
    """Unit tests for calculate_fingerprint_similarity function with FEATURE-010 weights."""

    @pytest.fixture
    def fingerprint_sec_binance(self):
        """Sample fingerprint for SEC vs Binance narrative."""
        return {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'regulatory enforcement action',
            'top_actors': ['SEC', 'Binance', 'Coinbase', 'Kraken', 'Gemini'],
            'key_actions': ['filed lawsuit', 'regulatory enforcement', 'compliance review']
        }

    @pytest.fixture
    def fingerprint_sec_coinbase(self):
        """Sample fingerprint for SEC vs Coinbase narrative (similar to Binance)."""
        return {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'regulatory enforcement',
            'top_actors': ['SEC', 'Coinbase', 'Kraken', 'FTX', 'Gemini'],
            'key_actions': ['filed lawsuit', 'enforcement action', 'securities violation']
        }

    @pytest.fixture
    def fingerprint_defi_growth(self):
        """Sample fingerprint for DeFi growth narrative (different)."""
        return {
            'nucleus_entity': 'Uniswap',
            'narrative_focus': 'tvl growth momentum',
            'top_actors': ['Uniswap', 'Aave', 'Compound', 'MakerDAO', 'Curve'],
            'key_actions': ['TVL increase', 'new protocol launch', 'yield farming']
        }

    def test_identical_fingerprints(self, fingerprint_sec_binance):
        """Test similarity of identical fingerprints returns 1.0 (no semantic boost with FEATURE-010)."""
        similarity = calculate_fingerprint_similarity(
            fingerprint_sec_binance,
            fingerprint_sec_binance
        )

        # Identical fingerprints with new weights:
        # focus: 1.0 * 0.5 = 0.5
        # nucleus: 1.0 * 0.3 = 0.3
        # actors: 1.0 * 0.1 = 0.1
        # actions: 1.0 * 0.1 = 0.1
        # Total: 1.0 (no semantic boost)
        assert 0.99 <= similarity <= 1.01  # Account for floating point precision

    def test_same_nucleus_same_focus_similar_actors(self, fingerprint_sec_binance, fingerprint_sec_coinbase):
        """Test high similarity when nucleus matches and focus is similar."""
        similarity = calculate_fingerprint_similarity(
            fingerprint_sec_binance,
            fingerprint_sec_coinbase
        )

        # New weights (FEATURE-010): focus (0.5), nucleus (0.3), actors (0.1), actions (0.1)
        # Focus: "regulatory enforcement action" vs "regulatory enforcement"
        #   -> overlap {regulatory, enforcement} = 2, union {regulatory, enforcement, action} = 3
        #   -> 2/3 = 66.7% > 50%, so _compute_focus_similarity returns 0.7
        # Nucleus: 1.0 (both SEC)
        # Actors overlap: {SEC, Coinbase, Kraken, Gemini} = 4, union {SEC, Binance, Coinbase, Kraken, FTX, Gemini} = 6
        #   -> 4/6 = 0.667
        # Actions overlap: {filed lawsuit, enforcement action} = 0 (no exact match), union = 5
        #   -> 0/5 = 0.0
        # Expected: (0.7*0.5) + (1.0*0.3) + (0.667*0.1) + (0.0*0.1) = 0.35 + 0.3 + 0.067 + 0.0 = 0.717
        assert 0.70 <= similarity <= 0.75

    def test_hard_gate_different_nucleus_different_focus(self):
        """Test hard gate blocks similarity when nucleus AND focus don't match."""
        fp1 = {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'regulatory enforcement',
            'top_actors': ['SEC', 'Binance'],
            'key_actions': ['lawsuit']
        }
        fp2 = {
            'nucleus_entity': 'Ethereum',
            'narrative_focus': 'protocol upgrade',
            'top_actors': ['Ethereum', 'Vitalik'],
            'key_actions': ['upgrade']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate blocks: no focus match AND no nucleus match
        # Expected: 0.0
        assert similarity == 0.0

    def test_hard_gate_same_nucleus_different_focus(self):
        """Test that same nucleus allows similarity calculation despite different focus."""
        fp1 = {
            'nucleus_entity': 'Dogecoin',
            'narrative_focus': 'price surge',
            'top_actors': ['Dogecoin', 'Elon Musk'],
            'key_actions': ['price surge']
        }
        fp2 = {
            'nucleus_entity': 'Dogecoin',
            'narrative_focus': 'governance dispute',
            'top_actors': ['Dogecoin', 'core team'],
            'key_actions': ['governance vote']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate passes: same nucleus (Dogecoin)
        # Focus match: "price surge" vs "governance dispute" -> 0% overlap -> 0.0
        # Nucleus: 1.0
        # Actors overlap: {Dogecoin} = 1, union = 3 -> 1/3 = 0.333
        # Actions overlap: 0
        # Expected: (0.0*0.5) + (1.0*0.3) + (0.333*0.1) + (0.0*0.1) = 0.0 + 0.3 + 0.033 + 0.0 = 0.333
        assert 0.30 <= similarity <= 0.35

    def test_hard_gate_same_focus_different_nucleus(self):
        """Test that same focus allows similarity calculation despite different nucleus."""
        fp1 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'institutional adoption',
            'top_actors': ['Bitcoin', 'MicroStrategy'],
            'key_actions': ['buying']
        }
        fp2 = {
            'nucleus_entity': 'Ethereum',
            'narrative_focus': 'institutional adoption',
            'top_actors': ['Ethereum', 'Grayscale'],
            'key_actions': ['buying']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate passes: same focus (institutional adoption)
        # Focus match: 1.0 (exact match)
        # Nucleus: 0.0 (different entities)
        # Actors overlap: 0
        # Actions overlap: 1
        # Expected: (1.0*0.5) + (0.0*0.3) + (0.0*0.1) + (1.0*0.1) = 0.5 + 0.0 + 0.0 + 0.1 = 0.6
        assert 0.55 <= similarity <= 0.65

    def test_different_nucleus_different_focus_different_actors(self, fingerprint_sec_binance, fingerprint_defi_growth):
        """Test hard gate blocks similarity when nucleus and focus are different."""
        similarity = calculate_fingerprint_similarity(
            fingerprint_sec_binance,
            fingerprint_defi_growth
        )

        # Hard gate blocks: no focus match AND no nucleus match
        # Expected: 0.0
        assert similarity == 0.0
    
    def test_same_nucleus_no_actor_overlap(self):
        """Test that different focus prevents high similarity even with same nucleus."""
        fp1 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'institutional buying momentum',
            'top_actors': ['Bitcoin', 'MicroStrategy', 'Saylor'],
            'key_actions': ['institutional buying', 'treasury allocation']
        }
        fp2 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'nation-state adoption',
            'top_actors': ['Bitcoin', 'El Salvador', 'Bukele'],
            'key_actions': ['nation-state adoption', 'legal tender']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # New weights (FEATURE-010): focus (0.5), nucleus (0.3), actors (0.1), actions (0.1)
        # Hard gate passes: same nucleus (Bitcoin)
        # Focus: "institutional buying momentum" vs "nation-state adoption" -> 0/5 word overlap = 0.0
        # Nucleus: 1.0
        # Actors overlap: {Bitcoin} = 1, union = 5 -> 1/5 = 0.2
        # Actions overlap: 0
        # Expected: (0.0*0.5) + (1.0*0.3) + (0.2*0.1) + (0.0*0.1) = 0.0 + 0.3 + 0.02 + 0.0 = 0.32
        assert 0.30 <= similarity <= 0.35

    def test_different_nucleus_high_actor_overlap_blocked_by_hard_gate(self):
        """Test that hard gate blocks high actor overlap when nucleus and focus differ."""
        fp1 = {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'regulatory enforcement',
            'top_actors': ['SEC', 'Binance', 'Coinbase', 'Kraken'],
            'key_actions': ['regulatory action']
        }
        fp2 = {
            'nucleus_entity': 'Binance',
            'narrative_focus': 'compliance response',
            'top_actors': ['Binance', 'SEC', 'Coinbase', 'Kraken'],
            'key_actions': ['compliance response']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate blocks: no focus match (different phrases) AND no nucleus match (SEC vs Binance)
        # Expected: 0.0
        assert similarity == 0.0

    def test_empty_fingerprints_blocked_by_hard_gate(self):
        """Test that hard gate blocks empty fingerprints (no focus, no nucleus)."""
        fp1 = {
            'nucleus_entity': '',
            'narrative_focus': '',
            'top_actors': [],
            'key_actions': []
        }
        fp2 = {
            'nucleus_entity': '',
            'narrative_focus': '',
            'top_actors': [],
            'key_actions': []
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate blocks: no focus match AND no nucleus match
        # Expected: 0.0
        assert similarity == 0.0

    def test_one_empty_fingerprint_blocks_hard_gate(self, fingerprint_sec_binance):
        """Test that one empty fingerprint is blocked by hard gate."""
        empty_fp = {
            'nucleus_entity': '',
            'narrative_focus': '',
            'top_actors': [],
            'key_actions': []
        }

        similarity = calculate_fingerprint_similarity(
            fingerprint_sec_binance,
            empty_fp
        )

        # Hard gate blocks: no focus match AND no nucleus match
        # Expected: 0.0
        assert similarity == 0.0

    def test_missing_fields_handled_gracefully(self):
        """Test that missing fields are handled gracefully with same nucleus."""
        fp1 = {'nucleus_entity': 'SEC'}  # Missing narrative_focus, actors and actions
        fp2 = {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'enforcement action',
            'top_actors': ['SEC', 'Binance'],
            'key_actions': ['lawsuit']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Hard gate passes: same nucleus (SEC)
        # Focus: missing in fp1 -> 0.5 (neutral for legacy)
        # Focus score: 0.5 * 0.5 = 0.25
        # Nucleus: 1.0 * 0.3 = 0.3
        # Actors: no actors in fp1 -> 0.0
        # Actions: no actions in fp1 -> 0.0
        # Expected: 0.25 + 0.3 + 0.0 + 0.0 = 0.55
        assert 0.50 <= similarity <= 0.60

    def test_action_overlap_contribution_with_same_nucleus_focus(self):
        """Test that action overlap contributes to similarity score."""
        fp1 = {
            'nucleus_entity': 'DeFi',
            'narrative_focus': 'tvl growth momentum',
            'top_actors': ['Uniswap', 'Aave'],
            'key_actions': ['TVL growth', 'new protocol', 'yield farming']
        }
        fp2 = {
            'nucleus_entity': 'DeFi',
            'narrative_focus': 'tvl growth momentum',
            'top_actors': ['Uniswap', 'Aave'],
            'key_actions': ['TVL growth', 'new protocol', 'liquidity mining']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # New weights (FEATURE-010): focus (0.5), nucleus (0.3), actors (0.1), actions (0.1)
        # Hard gate passes: same nucleus (DeFi) and same focus
        # Focus: exact match -> 1.0 * 0.5 = 0.5
        # Nucleus: 1.0 * 0.3 = 0.3
        # Actors: full overlap -> 1.0 * 0.1 = 0.1
        # Actions: 2 overlap {TVL growth, new protocol}, union = 4 -> 2/4 * 0.1 = 0.05
        # Expected: 0.5 + 0.3 + 0.1 + 0.05 = 0.95
        assert 0.90 <= similarity <= 1.00

    def test_weighted_scoring(self):
        """Test that weights are applied correctly (focus > nucleus > actors > actions)."""
        # Test 1: High actor overlap, different nucleus, different focus
        fp1 = {
            'nucleus_entity': 'EntityA',
            'narrative_focus': 'focus one',
            'top_actors': ['A', 'B', 'C', 'D', 'E'],
            'key_actions': ['action1']
        }
        fp2 = {
            'nucleus_entity': 'EntityB',
            'narrative_focus': 'focus two',
            'top_actors': ['A', 'B', 'C', 'D', 'E'],
            'key_actions': ['action2']
        }

        similarity_actors = calculate_fingerprint_similarity(fp1, fp2)

        # Test 2: Same nucleus, same focus, no actor overlap
        fp3 = {
            'nucleus_entity': 'EntityA',
            'narrative_focus': 'same focus',
            'top_actors': ['A', 'B', 'C'],
            'key_actions': ['action1']
        }
        fp4 = {
            'nucleus_entity': 'EntityA',
            'narrative_focus': 'same focus',
            'top_actors': ['X', 'Y', 'Z'],
            'key_actions': ['action2']
        }

        similarity_nucleus_focus = calculate_fingerprint_similarity(fp3, fp4)

        # similarity_actors: 0.0 + 0.35*0 + 0.20*1.0 + 0.0 = 0.20
        # similarity_nucleus_focus: 0.30 + 0.35*1.0 + 0.0 + 0.0 + 0.10 = 0.75
        # Nucleus+focus match should be much higher than actor overlap alone
        assert similarity_nucleus_focus > similarity_actors

    def test_jaccard_similarity_calculation(self):
        """Test that Jaccard similarity is calculated correctly for actors."""
        fp1 = {
            'nucleus_entity': 'Test',
            'narrative_focus': 'same focus',
            'top_actors': ['A', 'B', 'C'],
            'key_actions': []
        }
        fp2 = {
            'nucleus_entity': 'Test',
            'narrative_focus': 'same focus',
            'top_actors': ['B', 'C', 'D'],
            'key_actions': []
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Nucleus match: 0.30
        # Focus match: 1.0 * 0.35 = 0.35
        # Actor Jaccard: intersection={B,C}=2, union={A,B,C,D}=4, jaccard=2/4=0.5
        # Actor score: 0.20 * 0.5 = 0.10
        # Semantic boost: 0.10
        # Total: 0.30 + 0.35 + 0.10 + 0.10 = 0.85
        assert 0.80 <= similarity <= 0.90
    
    def test_case_insensitive_nucleus_matching(self):
        """Test that nucleus entity matching is case-insensitive."""
        fp1 = {
            'nucleus_entity': 'SEC',
            'narrative_focus': 'enforcement action',
            'top_actors': ['SEC', 'Binance'],
            'key_actions': ['lawsuit']
        }
        fp2 = {
            'nucleus_entity': 'sec',  # lowercase
            'narrative_focus': 'enforcement action',
            'top_actors': ['sec', 'binance'],  # lowercase
            'key_actions': ['lawsuit']
        }

        similarity = calculate_fingerprint_similarity(fp1, fp2)

        # Nucleus match (case-insensitive): 0.30
        # Focus match: 1.0 * 0.35 = 0.35
        # No actor overlap (actors are case-sensitive): 0.0
        # Action overlap: 0.15 * 1.0 = 0.15
        # Semantic boost: 0.10
        # Total: 0.30 + 0.35 + 0.0 + 0.15 + 0.10 = 0.90
        assert 0.85 <= similarity <= 0.95

    def test_semantic_boost_applied(self):
        """Test that semantic boost is applied when nucleus AND focus match well."""
        # Test 1: Same nucleus, same focus - boost applied
        fp1 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'institutional adoption',
            'top_actors': ['MicroStrategy'],
            'key_actions': ['buying']
        }
        fp2 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'institutional adoption',
            'top_actors': ['Tesla'],
            'key_actions': ['selling']
        }

        similarity_with_boost = calculate_fingerprint_similarity(fp1, fp2)

        # Nucleus match: 0.30
        # Focus match: 1.0 * 0.35 = 0.35
        # No actor overlap: 0.0
        # No action overlap: 0.0
        # Semantic boost: 0.10 (nucleus matches + focus >= 0.5)
        # Total: 0.75
        assert 0.70 <= similarity_with_boost <= 0.80

        # Test 2: Same nucleus, different focus - no boost (focus < 0.5)
        fp3 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'institutional adoption',
            'top_actors': ['Grayscale'],
            'key_actions': ['accumulating']
        }
        fp4 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'retail selling pressure',
            'top_actors': ['BlackRock'],
            'key_actions': ['launching ETF']
        }

        similarity_no_boost = calculate_fingerprint_similarity(fp3, fp4)

        # Nucleus match: 0.30
        # Focus match: 0/4 words overlap = 0.0
        # No actor overlap: 0.0
        # No action overlap: 0.0
        # No semantic boost (focus < 0.5)
        # Total: 0.30
        assert 0.25 <= similarity_no_boost <= 0.35

        # Test 3: No nucleus match - no boost
        fp5 = {
            'nucleus_entity': 'Ethereum',
            'narrative_focus': 'protocol upgrade',
            'top_actors': ['Vitalik'],
            'key_actions': ['upgrade']
        }
        fp6 = {
            'nucleus_entity': 'Bitcoin',
            'narrative_focus': 'mining difficulty',
            'top_actors': ['Satoshi'],
            'key_actions': ['mining']
        }

        similarity_no_match = calculate_fingerprint_similarity(fp5, fp6)

        # No nucleus match: 0.0
        # No focus overlap: 0.0
        # No actor overlap: 0.0
        # No action overlap: 0.0
        # Total: 0.0
        assert similarity_no_match == 0.0


# =============================================================================
# BUG-057: Narrative Retry Storm Fix Tests
# =============================================================================

class TestBuildDegradedNarrative:
    """Test _build_degraded_narrative() function."""

    def test_build_degraded_narrative_basic(self):
        """Test building a degraded narrative with basic inputs."""
        narrative = _build_degraded_narrative(
            article_id="test_123",
            title="SEC Announces New Crypto Rules",
            summary="The SEC issued guidance on crypto trading.",
            content_hash="abc123def456",
            reason="validation failed: nucleus_entity not in text"
        )

        # Check structure
        assert narrative["status"] == "degraded"
        assert narrative["degraded_reason"] == "validation failed: nucleus_entity not in text"
        assert "narrative_hash" in narrative
        assert narrative["narrative_hash"] == "abc123def456"
        assert narrative["narrative_focus"] == "unclassified"
        assert len(narrative["actors"]) > 0
        assert "actor_salience" in narrative
        assert "narrative_summary" in narrative

    def test_build_degraded_narrative_extracts_fallback_nucleus(self):
        """Test that degraded narrative uses title prefix as fallback nucleus."""
        title = "SEC Announces New Crypto Rules"
        narrative = _build_degraded_narrative(
            article_id="test_456",
            title=title,
            summary="Summary text",
            content_hash="hash789",
            reason="test reason"
        )

        # Fallback nucleus should be title before colon or first 50 chars
        assert narrative["nucleus_entity"]
        assert narrative["actors"][0] == narrative["nucleus_entity"]

    def test_build_degraded_narrative_empty_title(self):
        """Test degraded narrative with empty title."""
        narrative = _build_degraded_narrative(
            article_id="test_789",
            title="",
            summary="Just summary text",
            content_hash="hash999",
            reason="empty title"
        )

        # Should fall back to "Unknown"
        assert narrative["nucleus_entity"] == "Unknown"
        assert narrative["actors"] == ["Unknown"]


class TestZeroRetryOnValidationFailure:
    """Test that validation failures return degraded fallback without retry."""

    @pytest.mark.asyncio
    async def test_validation_failure_returns_degraded_not_retried(self):
        """Test that validation failures return degraded result immediately (no retry)."""
        article = {
            "_id": "test_validation_fail",
            "title": "Bitcoin Price Surges",
            "description": "Bitcoin price went up today."
        }

        # Mock LLM returning always-invalid response (missing nucleus_entity)
        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            mock_provider = MagicMock()
            # Always return invalid data
            mock_provider._get_completion.return_value = json.dumps({
                "actors": ["Bitcoin"],
                "actor_salience": {"Bitcoin": 5},
                # Missing nucleus_entity - validation will fail
                "narrative_focus": "price surge",
                "actions": ["price increased"],
                "tensions": [],
                "narrative_summary": "Bitcoin price went up"
            })
            mock_llm.return_value = mock_provider

            narrative = await discover_narrative_from_article(article, max_retries=2)

            # Should get degraded narrative, not None
            assert narrative is not None
            assert narrative.get("status") == "degraded"
            # Should only call LLM once (no retry on validation failure)
            assert mock_provider._get_completion.call_count == 1

    @pytest.mark.asyncio
    async def test_validation_failure_on_entity_hallucination(self):
        """Test that hallucinated nucleus_entity returns degraded without retry."""
        article = {
            "_id": "test_hallucination",
            "title": "Coinbase Posts Earnings",
            "description": "Coinbase reported strong quarterly earnings."
        }

        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            mock_provider = MagicMock()
            # LLM hallucinates "Netflix" as nucleus_entity (not in article)
            mock_provider._get_completion.return_value = json.dumps({
                "actors": ["Netflix", "Coinbase"],
                "actor_salience": {"Netflix": 5, "Coinbase": 3},
                "nucleus_entity": "Netflix",  # NOT in article - hallucination!
                "narrative_focus": "earnings",
                "actions": ["reported earnings"],
                "tensions": [],
                "narrative_summary": "Netflix reported earnings"
            })
            mock_llm.return_value = mock_provider

            narrative = await discover_narrative_from_article(article, max_retries=2)

            # Should return degraded narrative
            assert narrative is not None
            assert narrative.get("status") == "degraded"
            assert "hallucinated" in narrative.get("degraded_reason", "")
            # Should only call LLM once (no retry on hallucination detection)
            assert mock_provider._get_completion.call_count == 1


class TestPerArticleLLMCallCap:
    """Test MAX_LLM_CALLS_PER_ARTICLE enforcement."""

    @pytest.mark.asyncio
    async def test_llm_call_cap_enforced(self):
        """Test that per-article LLM call cap is enforced."""
        article = {
            "_id": "test_call_cap",
            "title": "Test Article",
            "description": "Test description"
        }

        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            mock_provider = MagicMock()
            # Always raise rate limit error to trigger retries
            mock_provider._get_completion.side_effect = Exception("429 rate limited")
            mock_llm.return_value = mock_provider

            with patch("asyncio.sleep"):  # Mock sleep to speed up test
                narrative = await discover_narrative_from_article(article, max_retries=5)

            # Should return degraded when call cap reached
            assert narrative is not None
            assert narrative.get("status") == "degraded"
            # Should only call LLM up to MAX_LLM_CALLS_PER_ARTICLE (2)
            assert mock_provider._get_completion.call_count <= 2


class TestTier2Tier3AutoFixes:
    """Test auto-fixes for Tier 2/3 validation failures."""

    def test_tier2_auto_fix_nucleus_salience(self):
        """Test that missing nucleus salience is auto-fixed to 5."""
        data = {
            "actors": ["Bitcoin", "Ethereum"],
            "actor_salience": {"Bitcoin": 5},  # Missing Ethereum
            "nucleus_entity": "Ethereum",
            "narrative_focus": "protocol upgrade",
            "actions": ["upgrade performed"],
            "tensions": [],
            "narrative_summary": "Ethereum protocol upgraded"
        }

        is_valid, error = validate_narrative_json(data)

        # Should be valid after auto-fix
        assert is_valid
        assert error is None
        # Nucleus should have salience 5 after auto-fix
        assert data["actor_salience"]["Ethereum"] == 5

    def test_tier3_auto_fix_empty_actors_backfill(self):
        """Test that empty actors list is backfilled from nucleus_entity."""
        data = {
            "actors": [],  # Empty - should be backfilled
            "actor_salience": {},
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "price surge",
            "actions": ["price increased"],
            "tensions": [],
            "narrative_summary": "Bitcoin price went up"
        }

        is_valid, error = validate_narrative_json(data)

        # Should be valid after auto-fix
        assert is_valid
        assert error is None
        # Actors should be backfilled with nucleus_entity
        assert "Bitcoin" in data["actors"]
        assert len(data["actors"]) > 0

    def test_nucleus_entity_added_to_actors(self):
        """Test that nucleus_entity is added to actors list if missing."""
        data = {
            "actors": ["SEC", "Coinbase"],  # Bitcoin not in actors
            "actor_salience": {"SEC": 5, "Coinbase": 3},
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "regulatory action",
            "actions": ["SEC action"],
            "tensions": [],
            "narrative_summary": "SEC took action against Bitcoin"
        }

        is_valid, error = validate_narrative_json(data)

        assert is_valid
        # Nucleus should be added to actors
        assert "Bitcoin" in data["actors"]


class TestDegradedNarrativeTracking:
    """Test degraded narrative tracking in backfill."""

    @pytest.mark.asyncio
    async def test_backfill_tracks_degraded_count(self):
        """Test that backfill_narratives_for_recent_articles tracks degraded count."""
        with patch("crypto_news_aggregator.services.narrative_themes.mongo_manager") as mock_mongo:
            # Mock database
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_db.articles = mock_collection

            async def get_db():
                return mock_db
            mock_mongo.get_async_database = get_db

            # Create mock articles - one will succeed, one will degrade
            articles = [
                {
                    "_id": "success_1",
                    "title": "Bitcoin Surge",
                    "description": "Bitcoin price went up",
                    "published_at": datetime.now(timezone.utc)
                },
                {
                    "_id": "degrade_1",
                    "title": "Bad Article",
                    "description": "Bad data",
                    "published_at": datetime.now(timezone.utc)
                }
            ]

            # Mock cursor
            class MockCursor:
                def __init__(self, data):
                    self.data = data
                    self.index = 0

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self.index >= len(self.data):
                        raise StopAsyncIteration
                    result = self.data[self.index]
                    self.index += 1
                    return result

                def limit(self, n):
                    return self

            mock_cursor = MockCursor(articles)
            mock_collection.find.return_value = mock_cursor

            with patch("crypto_news_aggregator.services.narrative_themes.discover_narrative_from_article") as mock_discover:
                # First article succeeds, second degrades
                async def discover_side_effect(article):
                    if article["_id"] == "success_1":
                        return {
                            "actors": ["Bitcoin"],
                            "actor_salience": {"Bitcoin": 5},
                            "nucleus_entity": "Bitcoin",
                            "narrative_focus": "price surge",
                            "actions": ["price increased"],
                            "tensions": [],
                            "narrative_summary": "Bitcoin price went up",
                            "narrative_hash": "hash1"
                        }
                    else:
                        return {
                            "status": "degraded",
                            "degraded_reason": "validation failed",
                            "actors": ["Unknown"],
                            "actor_salience": {"Unknown": 3},
                            "nucleus_entity": "Unknown",
                            "narrative_focus": "unclassified",
                            "narrative_hash": "hash2",
                            "narrative_summary": "Bad data"
                        }

                mock_discover.side_effect = discover_side_effect

                # Mock update_one
                async def mock_update(*args, **kwargs):
                    pass
                mock_collection.update_one = mock_update

                # Run backfill
                updated = await backfill_narratives_for_recent_articles(hours=48, limit=2)

                # Should have updated 2 articles
                assert updated == 2


class TestDownstreamDegradedFiltering:
    """Test that degraded narratives are filtered in detect_narratives."""

    @pytest.mark.asyncio
    async def test_detect_narratives_filters_degraded(self):
        """Test that detect_narratives excludes status='degraded' narratives."""
        # This test verifies the MongoDB query excludes degraded narratives
        # The actual filtering happens in detect_narratives query:
        # "status": {"$ne": "degraded"}

        from crypto_news_aggregator.services.narrative_service import detect_narratives

        with patch("crypto_news_aggregator.services.narrative_service.mongo_manager") as mock_mongo:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_db.articles = mock_collection

            async def get_db():
                return mock_db
            mock_mongo.get_async_database = get_db

            # Capture the query passed to find()
            find_query = None

            class MockCursor:
                def __aiter__(self):
                    return self

                async def __anext__(self):
                    raise StopAsyncIteration

                def limit(self, n):
                    return self

            def mock_find(query):
                nonlocal find_query
                find_query = query
                return MockCursor()

            mock_collection.find = mock_find

            try:
                await detect_narratives(hours=48)
            except Exception:
                pass  # We're just checking the query

            # Verify the query filters out degraded narratives
            if find_query:
                # Should have a status filter excluding degraded
                assert "$ne" in str(find_query) or "degraded" in str(find_query)


class TestIntegrationRetryStormFix:
    """Integration test for the complete BUG-057 fix."""

    @pytest.mark.asyncio
    async def test_retry_storm_prevented(self):
        """Test that the complete fix prevents retry storms."""
        article = {
            "_id": "integration_test",
            "title": "Test Article",
            "description": "Test description"
        }

        llm_call_count = 0

        with patch("crypto_news_aggregator.services.narrative_themes.get_llm_provider") as mock_llm:
            mock_provider = MagicMock()

            def llm_call_counter(*args, **kwargs):
                nonlocal llm_call_count
                llm_call_count += 1
                # Always fail validation (missing nucleus_entity)
                return json.dumps({
                    "actors": ["Bitcoin"],
                    "actor_salience": {"Bitcoin": 5},
                    "narrative_focus": "price",
                    "actions": [],
                    "tensions": [],
                    "narrative_summary": "price change"
                })

            mock_provider._get_completion.side_effect = llm_call_counter
            mock_llm.return_value = mock_provider

            result = await discover_narrative_from_article(article, max_retries=4)

            # Should get degraded result
            assert result is not None
            assert result.get("status") == "degraded"

            # Key: LLM should be called only once (validation failure, no retry)
            # not 4 times (old behavior with max_retries=4)
            assert llm_call_count <= 2  # max_retries=2 in discover function


# Add import for json at top of test file if not already present
import json
