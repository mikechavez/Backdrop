"""
Test BUG-099: Prevent Invalid Briefings From Publishing.

Tests that malformed, low-confidence, parse-failed, empty-insight, or model-meta-output
briefings are not published to public users.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from bson import ObjectId
from crypto_news_aggregator.services.briefing_agent import (
    BriefingAgent,
    GeneratedBriefing,
    BriefingInput,
)


@pytest.fixture
def briefing_agent():
    """Create a briefing agent instance."""
    return BriefingAgent()


@pytest.fixture
def mock_briefing_input():
    """Create mock briefing input for testing."""
    return BriefingInput(
        briefing_type="morning",
        signals=[{"name": "bitcoin_surge"}],
        narratives=[
            {
                "title": "Bitcoin Surge",
                "summary": "Bitcoin surged 10%",
                "entities": ["Bitcoin"],
            }
        ],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


class TestValidateBriefingPublishable:
    """Tests for _validate_briefing_publishable validation function."""

    def test_valid_briefing_publishable(self, briefing_agent):
        """Test that a valid briefing passes validation."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged 10% on strong economic data.",
            key_insights=["Bitcoin up 10%", "Market optimistic"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.85,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is True
        assert reason is None

    def test_parse_failed_briefing_rejected(self, briefing_agent):
        """Test that briefings marked parse_failed are rejected."""
        generated = GeneratedBriefing(
            narrative="Some raw text",
            key_insights=[],
            entities_mentioned=[],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.3,
            parse_failed=True,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "parse_failed" in reason

    def test_low_confidence_briefing_rejected(self, briefing_agent):
        """Test that low confidence (<0.5) briefings are rejected."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged.",
            key_insights=["Bitcoin up"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.3,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "low_confidence" in reason

    def test_empty_narrative_rejected(self, briefing_agent):
        """Test that empty narrative is rejected."""
        generated = GeneratedBriefing(
            narrative="",
            key_insights=["Bitcoin up"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "empty_narrative" in reason

    def test_whitespace_narrative_rejected(self, briefing_agent):
        """Test that whitespace-only narrative is rejected."""
        generated = GeneratedBriefing(
            narrative="   \n\t  ",
            key_insights=["Bitcoin up"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "empty_narrative" in reason

    def test_empty_key_insights_rejected(self, briefing_agent):
        """Test that empty key_insights are rejected."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged.",
            key_insights=[],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "empty_key_insights" in reason

    @pytest.mark.parametrize(
        "phrase,narrative",
        [
            ("please provide", "Please provide the active narrative data"),
            ("i don't have access", "I don't have access to real-time data"),
            ("i need the actual narrative data", "I need the actual narrative data to proceed"),
            ("i need to pause", "I need to pause and wait for more data"),
            ("i cannot generate", "I cannot generate a briefing without data"),
            ("as an ai", "As an AI, I can only work with provided data"),
            ("missing data", "The narrative contains missing data"),
            ("before i can generate", "Before I can generate, you must provide"),
            ("could you provide", "Could you provide the missing narratives"),
            ("available data", "The available data is insufficient"),
        ],
    )
    def test_model_meta_phrases_rejected(self, briefing_agent, phrase, narrative):
        """Test that narratives with model-meta phrases are rejected."""
        generated = GeneratedBriefing(
            narrative=narrative,
            key_insights=["Some insight"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "model_meta_output" in reason

    def test_case_insensitive_model_meta_detection(self, briefing_agent):
        """Test that model-meta detection is case-insensitive."""
        generated = GeneratedBriefing(
            narrative="PLEASE PROVIDE the active narrative data",
            key_insights=["Insight"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        is_publishable, reason = briefing_agent._validate_briefing_publishable(generated)
        assert is_publishable is False
        assert "model_meta_output" in reason


class TestParseBriefingResponseMarksParseFailure:
    """Tests for parse failure handling in _parse_briefing_response."""

    def test_valid_json_not_marked_parse_failed(self, briefing_agent):
        """Test that valid JSON responses are not marked parse_failed."""
        response = """
        {
            "narrative": "Bitcoin rose 10%",
            "key_insights": ["Up 10%"],
            "entities_mentioned": ["Bitcoin"],
            "detected_patterns": [],
            "recommendations": [],
            "confidence_score": 0.9
        }
        """

        generated = briefing_agent._parse_briefing_response(response)
        assert generated.parse_failed is False
        assert generated.confidence_score == 0.9

    def test_invalid_json_marked_parse_failed(self, briefing_agent):
        """Test that invalid JSON responses are marked parse_failed."""
        response = "This is plain text, not JSON at all"

        generated = briefing_agent._parse_briefing_response(response)
        assert generated.parse_failed is True
        assert generated.confidence_score == 0.3
        assert "This is plain text" in generated.narrative


class TestSaveBriefingPublishability:
    """Tests for _save_briefing respecting publishability validation."""

    @pytest.mark.asyncio
    async def test_valid_briefing_is_published(self, briefing_agent, mock_briefing_input):
        """Test that valid briefings are published."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged 10%.",
            key_insights=["Bitcoin up 10%"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        test_id = str(ObjectId())
        with patch(
            "crypto_news_aggregator.services.briefing_agent.insert_briefing",
            new_callable=AsyncMock,
            return_value=test_id,
        ):
            result = await briefing_agent._save_briefing(
                briefing_type="morning",
                briefing_input=mock_briefing_input,
                generated=generated,
                is_smoke=False,
                task_id="task1",
            )

        assert result["published"] is True
        assert "invalid_output" not in result["metadata"]

    @pytest.mark.asyncio
    async def test_invalid_briefing_not_published(self, briefing_agent, mock_briefing_input):
        """Test that invalid briefings are not published."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged.",
            key_insights=[],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        test_id = str(ObjectId())
        with patch(
            "crypto_news_aggregator.services.briefing_agent.insert_briefing",
            new_callable=AsyncMock,
            return_value=test_id,
        ):
            result = await briefing_agent._save_briefing(
                briefing_type="morning",
                briefing_input=mock_briefing_input,
                generated=generated,
                is_smoke=False,
                task_id="task1",
            )

        assert result["published"] is False
        assert result["metadata"]["invalid_output"] is True
        assert "invalid_reason" in result["metadata"]
        assert "empty_key_insights" in result["metadata"]["invalid_reason"]

    @pytest.mark.asyncio
    async def test_parse_failed_briefing_not_published(self, briefing_agent, mock_briefing_input):
        """Test that parse-failed briefings are not published."""
        generated = GeneratedBriefing(
            narrative="Please provide the narrative data",
            key_insights=[],
            entities_mentioned=[],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.3,
            parse_failed=True,
        )

        test_id = str(ObjectId())
        with patch(
            "crypto_news_aggregator.services.briefing_agent.insert_briefing",
            new_callable=AsyncMock,
            return_value=test_id,
        ):
            result = await briefing_agent._save_briefing(
                briefing_type="morning",
                briefing_input=mock_briefing_input,
                generated=generated,
                is_smoke=False,
                task_id="task1",
            )

        assert result["published"] is False
        assert result["metadata"]["invalid_output"] is True
        assert "parse_failed" in result["metadata"]["invalid_reason"]

    @pytest.mark.asyncio
    async def test_model_meta_briefing_not_published(self, briefing_agent, mock_briefing_input):
        """Test that model-meta briefings are not published."""
        generated = GeneratedBriefing(
            narrative="I need the actual narrative data to generate a proper briefing.",
            key_insights=["Need more data"],
            entities_mentioned=[],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        test_id = str(ObjectId())
        with patch(
            "crypto_news_aggregator.services.briefing_agent.insert_briefing",
            new_callable=AsyncMock,
            return_value=test_id,
        ):
            result = await briefing_agent._save_briefing(
                briefing_type="morning",
                briefing_input=mock_briefing_input,
                generated=generated,
                is_smoke=False,
                task_id="task1",
            )

        assert result["published"] is False
        assert result["metadata"]["invalid_output"] is True
        assert "model_meta_output" in result["metadata"]["invalid_reason"]

    @pytest.mark.asyncio
    async def test_smoke_test_always_unpublished(self, briefing_agent, mock_briefing_input):
        """Test that smoke tests are never published."""
        generated = GeneratedBriefing(
            narrative="Bitcoin surged 10%.",
            key_insights=["Bitcoin up 10%"],
            entities_mentioned=["Bitcoin"],
            detected_patterns=[],
            recommendations=[],
            confidence_score=0.8,
            parse_failed=False,
        )

        test_id = str(ObjectId())
        with patch(
            "crypto_news_aggregator.services.briefing_agent.insert_briefing",
            new_callable=AsyncMock,
            return_value=test_id,
        ):
            result = await briefing_agent._save_briefing(
                briefing_type="morning",
                briefing_input=mock_briefing_input,
                generated=generated,
                is_smoke=True,
                task_id="task1",
            )

        assert result["published"] is False
        assert result["is_smoke"] is True


class TestDatabaseFilterExcludesInvalid:
    """Tests for database-level filtering of invalid briefings."""

    def test_production_filter_excludes_invalid(self):
        """Test that _get_production_briefings_filter excludes invalid briefings."""
        from crypto_news_aggregator.db.operations.briefing import _get_production_briefings_filter

        filter_query = _get_production_briefings_filter()

        # Filter should have multiple conditions
        assert "$or" in filter_query
        assert "is_smoke" in filter_query
        assert "metadata.invalid_output" in filter_query

        # Should exclude invalid briefings
        assert filter_query["metadata.invalid_output"] == {"$ne": True}
