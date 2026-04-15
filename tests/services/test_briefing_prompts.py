"""
Test enhanced briefing prompt quality checks.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.services.briefing_agent import BriefingAgent, GeneratedBriefing, BriefingInput
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


@pytest.fixture
def mock_briefing_input_with_entities():
    """Create mock briefing input with specific entities."""
    return BriefingInput(
        briefing_type="morning",
        signals=[],
        narratives=[
            {
                "title": "Binance Central Asian Expansion",
                "summary": "Binance listed Kyrgyzstan som-pegged stablecoin",
                "entities": ["Binance", "Kyrgyzstan"],
            },
            {
                "title": "BlackRock Bitcoin ETF Positioning",
                "summary": "BlackRock designated Bitcoin ETF as key 2025 theme",
                "entities": ["BlackRock", "Bitcoin"],
            }
        ],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


def test_system_prompt_includes_entity_rules(mock_briefing_input_with_entities):
    """Test that system prompt includes specific entity reference rules."""
    agent = BriefingAgent()

    system_prompt = agent._get_system_prompt("morning")

    # Check for entity reference rules
    assert "SPECIFIC ENTITY REFERENCES" in system_prompt
    assert "NEVER use vague references" in system_prompt
    assert '"the platform", "the exchange"' in system_prompt

    # Check for why it matters requirement
    assert '"WHY IT MATTERS"' in system_prompt
    assert "The significance lies in" in system_prompt

    # Check for good/bad examples
    assert "GOOD EXAMPLE:" in system_prompt
    assert "BAD EXAMPLE:" in system_prompt


def test_critique_prompt_includes_entity_check(mock_briefing_input_with_entities):
    """Test that critique prompt checks for vague entity references."""
    agent = BriefingAgent()

    generated = GeneratedBriefing(
        narrative="The exchange is expanding into new markets.",  # Vague!
        key_insights=["Exchange expansion"],
        entities_mentioned=["Exchange"],  # Also vague
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = agent._build_critique_prompt(generated, mock_briefing_input_with_entities)

    # Check that critique prompt includes entity vagueness check
    assert "VAGUE ENTITY REFERENCES" in critique_prompt
    assert "the platform" in critique_prompt.lower()
    assert "AVAILABLE ENTITIES" in critique_prompt
    assert "Binance" in critique_prompt
    assert "BlackRock" in critique_prompt


def test_critique_detects_missing_why_it_matters(mock_briefing_input_with_entities):
    """Test that critique detects missing significance explanations."""
    agent = BriefingAgent()

    generated = GeneratedBriefing(
        narrative="Binance listed a new stablecoin. BlackRock designated Bitcoin ETF as key theme.",
        key_insights=["Stablecoin listing", "ETF positioning"],
        entities_mentioned=["Binance", "BlackRock"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = agent._build_critique_prompt(generated, mock_briefing_input_with_entities)

    # Check for "why it matters" requirement
    assert 'MISSING "WHY IT MATTERS"' in critique_prompt
    assert "significance or implications" in critique_prompt.lower()


def test_generation_prompt_converts_utc_to_display_timezone():
    """Test that prompt time context converts UTC to display timezone (CST/CDT)."""
    agent = BriefingAgent()

    # Test case 1: Midnight UTC = 7 PM CDT April 14
    # Create a briefing input with generated_at = 2026-04-15 00:00 UTC
    briefing_input = BriefingInput(
        briefing_type="evening",
        signals=[],
        narratives=[],
        patterns=MagicMock(to_prompt_context=lambda: ""),
        memory=MagicMock(to_prompt_context=lambda: ""),
        generated_at=datetime(2026, 4, 15, 0, 0, tzinfo=timezone.utc),
    )

    prompt = agent._build_generation_prompt(briefing_input)

    # Verify the prompt contains April 14, not April 15
    assert "Tuesday, April 14, 2026" in prompt
    assert "April 15" not in prompt


def test_generation_prompt_handles_daytime_utc():
    """Test that prompt correctly converts daytime UTC timestamps."""
    agent = BriefingAgent()

    # Test case 2: 2 PM UTC April 15 = 9 AM CDT April 15
    briefing_input = BriefingInput(
        briefing_type="morning",
        signals=[],
        narratives=[],
        patterns=MagicMock(to_prompt_context=lambda: ""),
        memory=MagicMock(to_prompt_context=lambda: ""),
        generated_at=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
    )

    prompt = agent._build_generation_prompt(briefing_input)

    # Verify the prompt contains April 15 (and not April 14)
    assert "April 15, 2026" in prompt
    assert "April 14" not in prompt
