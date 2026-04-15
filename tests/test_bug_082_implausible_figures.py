"""
Tests for BUG-082: Narrative summary pipeline implausible financial figures validation.

Tests that:
1. The summary prompt instructs LLM to verify financial figures across articles
2. Post-generation figure plausibility checks log warnings for suspicious figures
3. The regex correctly identifies financial figures in various formats
4. Figures below threshold do not trigger warnings
"""

import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.llm.optimized_anthropic import OptimizedAnthropicLLM


@pytest.fixture
def mock_db():
    """Mock MongoDB database."""
    return MagicMock()


@pytest.fixture
def mock_api_key():
    """Mock API key."""
    return "test-api-key"


@pytest.fixture
def llm_client(mock_db, mock_api_key):
    """Create OptimizedAnthropicLLM instance with mocks."""
    with patch.object(OptimizedAnthropicLLM, 'initialize', new_callable=AsyncMock):
        client = OptimizedAnthropicLLM(mock_db, mock_api_key)
        client.cache = MagicMock()
        return client


class TestNarrativeSummaryPrompt:
    """Tests for summary prompt with figure verification instruction."""

    def test_summary_prompt_includes_figure_verification(self, llm_client):
        """Test that _build_summary_prompt includes figure verification instruction."""
        articles = [
            {
                "title": "Bitcoin Surge",
                "text": "Bitcoin rose 10% due to institutional buying."
            },
            {
                "title": "Ethereum Update",
                "text": "Ethereum foundation announced new initiatives."
            }
        ]

        prompt = llm_client._build_summary_prompt(articles)

        # Check that the prompt includes the figure verification instruction
        assert "Verifies financial figures are consistent across articles" in prompt
        assert "note the discrepancy rather than picking one" in prompt
        assert "conflicting perspectives" in prompt

    def test_summary_prompt_contains_articles(self, llm_client):
        """Test that prompt includes article content."""
        articles = [
            {
                "title": "Breaking News",
                "text": "Important announcement about crypto market."
            }
        ]

        prompt = llm_client._build_summary_prompt(articles)

        assert "Breaking News" in prompt
        assert "Important announcement" in prompt

    def test_summary_prompt_limits_articles(self, llm_client):
        """Test that prompt only includes first 10 articles."""
        articles = [
            {
                "title": f"Article {i}",
                "text": f"Content for article {i}"
            }
            for i in range(15)
        ]

        prompt = llm_client._build_summary_prompt(articles)

        # Should include articles 0-9, not 10-14
        assert "Article 0" in prompt
        assert "Article 9" in prompt
        assert "Article 14" not in prompt


class TestImplausibleFigureDetection:
    """Tests for post-generation figure plausibility checks."""

    @pytest.mark.asyncio
    async def test_suspicious_figure_above_threshold_logs_warning(self, llm_client, caplog):
        """Test that figures exceeding $50B threshold trigger warning log."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "A $204.7B liquidation event occurred in the crypto market."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        result = await llm_client.generate_narrative_summary(articles)

        # Verify warning was logged
        assert any("SUSPICIOUS FIGURE" in record.message for record in caplog.records)
        assert any("$204.7B" in record.message for record in caplog.records)
        assert any("$50B single-event threshold" in record.message for record in caplog.records)
        assert result == "A $204.7B liquidation event occurred in the crypto market."

    @pytest.mark.asyncio
    async def test_figure_below_threshold_no_warning(self, llm_client, caplog):
        """Test that figures below $50B threshold do not trigger warning."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "A $2.5B investment round was announced by the company."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        result = await llm_client.generate_narrative_summary(articles)

        # Verify no warning was logged for $2.5B
        assert not any("SUSPICIOUS FIGURE" in record.message for record in caplog.records)
        assert result == "A $2.5B investment round was announced by the company."

    @pytest.mark.asyncio
    async def test_trillion_figure_converted_to_billions(self, llm_client, caplog):
        """Test that trillion figures are converted to billions for threshold check."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                # $1.2T = $1,200B, which exceeds $50B threshold
                mock_call.return_value = {
                    "content": "The total market cap is $1.2T in value."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        result = await llm_client.generate_narrative_summary(articles)

        # Verify warning for trillion figure
        assert any("SUSPICIOUS FIGURE" in record.message for record in caplog.records)
        assert any("$1.2T" in record.message for record in caplog.records)


class TestFigureRegexFormats:
    """Tests for regex pattern matching various financial figure formats."""

    @pytest.mark.asyncio
    async def test_regex_matches_dollar_b_format(self, llm_client, caplog):
        """Test regex matches $XXX.XB format."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "Liquidations reached $204.7B in volume."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        assert any("$204.7B" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_matches_billion_word_format(self, llm_client, caplog):
        """Test regex matches $XXX billion format."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "The withdrawal exceeded $100 billion in total."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        assert any("$100 billion" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_matches_trillion_t_format(self, llm_client, caplog):
        """Test regex matches $XXX.XT format."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "Market cap reached $2.5T in value."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        assert any("$2.5T" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_matches_trillion_word_format(self, llm_client, caplog):
        """Test regex matches $XXX trillion format."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "Total derivatives notional is $1.2 trillion globally."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        assert any("$1.2 trillion" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_handles_comma_separated_numbers(self, llm_client, caplog):
        """Test regex handles numbers with comma separators."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "Volume exceeded $1,500.5B yesterday."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        # Should match and detect $1,500.5B > $50B
        assert any("SUSPICIOUS FIGURE" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_regex_case_insensitive(self, llm_client, caplog):
        """Test regex is case-insensitive for unit letters."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                # Test lowercase 'b' and uppercase 't'
                mock_call.return_value = {
                    "content": "The amount was $100b and $1.5T in total."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        warnings = [r for r in caplog.records if "SUSPICIOUS FIGURE" in r.message]
        assert len(warnings) >= 2  # Should match both figures


class TestSummaryWithMultipleFigures:
    """Tests for summaries containing multiple financial figures."""

    @pytest.mark.asyncio
    async def test_multiple_figures_suspicious_and_safe(self, llm_client, caplog):
        """Test that both suspicious and safe figures are handled correctly."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "A $5B investment led to $150B in liquidations, affecting $2B in positions."
                }

                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        await llm_client.generate_narrative_summary(articles)

        warnings = [r for r in caplog.records if "SUSPICIOUS FIGURE" in r.message]
        # Should warn about $150B but not $5B or $2B
        assert len(warnings) == 1
        assert "$150B" in warnings[0].message


class TestCachingWithFigureValidation:
    """Tests that caching works correctly with figure validation."""

    @pytest.mark.asyncio
    async def test_cache_bypass_with_figure_validation(self, llm_client, caplog):
        """Test that figure validation still occurs even with caching enabled."""
        with caplog.at_level(logging.WARNING):
            with patch.object(llm_client, '_make_api_call') as mock_call:
                mock_call.return_value = {
                    "content": "The event involved $75B in movement."
                }

                # First call: cache miss
                with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=None):
                    with patch.object(llm_client.cache, 'set', new_callable=AsyncMock):
                        articles = [{"title": "Test", "text": "Test content"}]
                        result = await llm_client.generate_narrative_summary(articles, use_cache=True)

        # Should log warning even with caching enabled
        assert any("SUSPICIOUS FIGURE" in record.message for record in caplog.records)
        assert result == "The event involved $75B in movement."

    @pytest.mark.asyncio
    async def test_cache_hit_returns_summary(self, llm_client):
        """Test that cache hits return summary without re-validation."""
        cached_result = {"summary": "Cached summary with $200B figure"}

        with patch.object(llm_client.cache, 'get', new_callable=AsyncMock, return_value=cached_result):
            articles = [{"title": "Test", "text": "Test content"}]
            result = await llm_client.generate_narrative_summary(articles, use_cache=True)

        # Should return cached result directly without calling API
        assert result == "Cached summary with $200B figure"
