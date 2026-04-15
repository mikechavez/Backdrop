"""
Test BUG-081: Briefing quality guardrails for duplicate events, unnamed entities, and implausible figures.
"""

import pytest
from unittest.mock import MagicMock
from crypto_news_aggregator.services.briefing_agent import BriefingAgent, GeneratedBriefing, BriefingInput
from datetime import datetime, timezone


@pytest.fixture
def briefing_agent():
    """Create a briefing agent instance."""
    return BriefingAgent()


@pytest.fixture
def mock_briefing_input():
    """Create mock briefing input with entities for testing."""
    return BriefingInput(
        briefing_type="evening",
        signals=[],
        narratives=[
            {
                "title": "Polkadot Bridge Exploit - Event A",
                "summary": "Polkadot bridge breach minting $1.1B in unauthorized DOT",
                "entities": ["Polkadot", "Hyperbridge"],
            },
            {
                "title": "Hyperbridge Exploit - Event B",
                "summary": "Hyperbridge exploit minting over 1 billion fake DOT tokens",
                "entities": ["Hyperbridge", "Polkadot"],
            },
            {
                "title": "Kraken Security Incident",
                "summary": "Major security incident affected Kraken and another platform",
                "entities": ["Kraken"],
            },
            {
                "title": "Liquidation Cascade",
                "summary": "$204.7B in liquidations within 24 hours",
                "entities": ["Market"],
            },
        ],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


def test_system_prompt_includes_rule_9_consolidate_duplicates(briefing_agent):
    """Test that system prompt includes rule 9 for consolidating duplicate events."""
    system_prompt = briefing_agent._get_system_prompt("evening")

    assert "9. CONSOLIDATE DUPLICATE EVENTS" in system_prompt
    assert "same underlying event from different angles" in system_prompt
    assert "synthesize them into a single coherent account" in system_prompt
    assert "Do NOT present the same event twice with different framing" in system_prompt
    assert "Polkadot" in system_prompt and "bridge exploit" in system_prompt.lower()


def test_system_prompt_includes_rule_10_no_unnamed_entities(briefing_agent):
    """Test that system prompt includes rule 10 for preventing unnamed entities."""
    system_prompt = briefing_agent._get_system_prompt("evening")

    assert "10. NO UNNAMED ENTITIES" in system_prompt
    assert "two platforms" in system_prompt
    assert "multiple exchanges" in system_prompt
    assert "several protocols" in system_prompt
    assert "NEVER imply a count of affected parties" in system_prompt


def test_system_prompt_includes_rule_11_figure_plausibility(briefing_agent):
    """Test that system prompt includes rule 11 for verifying figure plausibility."""
    system_prompt = briefing_agent._get_system_prompt("evening")

    assert "11. VERIFY FIGURE PLAUSIBILITY" in system_prompt
    assert "total crypto market cap (~$2-3T)" in system_prompt
    assert "$50B" in system_prompt
    assert "$10B" in system_prompt
    assert "historically unprecedented" in system_prompt


def test_critique_prompt_includes_check_8_duplicate_events(briefing_agent, mock_briefing_input):
    """Test that critique prompt includes check 8 for duplicate events."""
    generated = GeneratedBriefing(
        narrative="The Polkadot bridge breach minted $1.1B in unauthorized DOT. The Hyperbridge exploit also minted over 1 billion fake DOT tokens.",
        key_insights=["Bridge exploit"],
        entities_mentioned=["Polkadot", "Hyperbridge"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = briefing_agent._build_critique_prompt(generated, mock_briefing_input)

    assert "8. DUPLICATE EVENTS" in critique_prompt
    assert "same underlying event" in critique_prompt
    assert "consolidated into one account" in critique_prompt


def test_critique_prompt_includes_check_9_unnamed_entities(briefing_agent, mock_briefing_input):
    """Test that critique prompt includes check 9 for unnamed entities."""
    generated = GeneratedBriefing(
        narrative="A major security incident affected two platforms. One is Kraken, but the other remains unidentified.",
        key_insights=["Security incident"],
        entities_mentioned=["Kraken"],  # Missing the second platform
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = briefing_agent._build_critique_prompt(generated, mock_briefing_input)

    assert "9. UNNAMED ENTITIES" in critique_prompt
    assert "two platforms" in critique_prompt
    assert "multiple exchanges" in critique_prompt
    assert "explicitly named" in critique_prompt


def test_critique_prompt_includes_check_10_implausible_figures(briefing_agent, mock_briefing_input):
    """Test that critique prompt includes check 10 for implausible figures."""
    generated = GeneratedBriefing(
        narrative="The market experienced $204.7B in liquidations within 24 hours.",
        key_insights=["Market liquidation"],
        entities_mentioned=["Market"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = briefing_agent._build_critique_prompt(generated, mock_briefing_input)

    assert "10. IMPLAUSIBLE FIGURES" in critique_prompt
    assert "$2-3T" in critique_prompt or "2-3T" in critique_prompt
    assert "$50B" in critique_prompt
    assert "$10B" in critique_prompt
    assert "historically unprecedented" in critique_prompt


def test_critique_prompt_mentions_available_entities(briefing_agent, mock_briefing_input):
    """Test that critique prompt includes available entities for reference."""
    generated = GeneratedBriefing(
        narrative="Something happened.",
        key_insights=["Test"],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    critique_prompt = briefing_agent._build_critique_prompt(generated, mock_briefing_input)

    # Should list available entities for the critiquer to check against
    assert "Polkadot" in critique_prompt
    assert "Hyperbridge" in critique_prompt
    assert "Kraken" in critique_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
