"""
Test BUG-100: Refinement prompt source context grounding.

Ensures the refinement prompt includes full narrative details,
entities, signals, and patterns to prevent the LLM from asking
for additional data during the refinement pass.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from crypto_news_aggregator.services.briefing_agent import (
    BriefingAgent,
    GeneratedBriefing,
    BriefingInput,
)


@pytest.fixture
def sample_narratives():
    """Create sample narratives with entities and summaries."""
    return [
        {
            "_id": "narr-1",
            "title": "Bitcoin Spot ETF Approval",
            "summary": "SEC approved multiple Bitcoin spot ETFs in early 2024, marking institutional adoption.",
            "entities": ["Bitcoin", "SEC", "ETF"],
            "article_count": 42,
            "article_ids": ["art-1", "art-2", "art-3"],
        },
        {
            "_id": "narr-2",
            "title": "Ethereum Shanghai Upgrade Staking",
            "summary": "Ethereum Shanghai upgrade enabled solo staking with 32 ETH minimum deposit.",
            "entities": ["Ethereum", "Shanghai", "Staking"],
            "article_count": 28,
            "article_ids": ["art-4", "art-5"],
        },
        {
            "_id": "narr-3",
            "title": "Coinbase Institutional Growth",
            "summary": "Coinbase reported record institutional trading volumes and new custody offerings.",
            "entities": ["Coinbase", "Institutional", "Trading"],
            "article_count": 15,
            "article_ids": ["art-6"],
        },
    ]


@pytest.fixture
def sample_signals():
    """Create sample trending signals."""
    return [
        {
            "entity": "Bitcoin",
            "metrics": {
                "score_24h": 85.5,
                "velocity_24h": 120.0,
            },
        },
        {
            "entity": "Ethereum",
            "metrics": {
                "score_24h": 72.3,
                "velocity_24h": 95.0,
            },
        },
    ]


@pytest.fixture
def mock_patterns():
    """Create mock pattern detector."""
    mock = MagicMock()
    mock.all_patterns.return_value = [
        {"name": "Institutional Accumulation", "description": "Large wallet movements into exchanges"},
        {"name": "Regulatory Pressure", "description": "Increased regulatory scrutiny affecting prices"},
    ]
    return mock


@pytest.fixture
def briefing_input_with_context(sample_narratives, sample_signals, mock_patterns):
    """Create briefing input with full context."""
    return BriefingInput(
        briefing_type="morning",
        signals=sample_signals,
        narratives=sample_narratives,
        patterns=mock_patterns,
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


def test_refinement_prompt_includes_narrative_titles(briefing_input_with_context):
    """Test that refinement prompt includes narrative titles."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Bitcoin and Ethereum prices rose.",
        key_insights=["Price movement"],
        entities_mentioned=["Bitcoin", "Ethereum"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Needs more detail on why prices rose.",
        briefing_input_with_context,
    )

    assert "Bitcoin Spot ETF Approval" in prompt
    assert "Ethereum Shanghai Upgrade Staking" in prompt
    assert "Coinbase Institutional Growth" in prompt


def test_refinement_prompt_includes_narrative_summaries(briefing_input_with_context):
    """Test that refinement prompt includes narrative summaries."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Bitcoin adoption is growing.",
        key_insights=["Adoption"],
        entities_mentioned=["Bitcoin"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Vague on adoption details.",
        briefing_input_with_context,
    )

    assert "SEC approved multiple Bitcoin spot ETFs" in prompt
    assert "Ethereum Shanghai upgrade enabled solo staking" in prompt
    assert "Coinbase reported record institutional trading" in prompt


def test_refinement_prompt_includes_narrative_entities(briefing_input_with_context):
    """Test that refinement prompt includes narrative entities."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Institutions are adopting crypto.",
        key_insights=["Institutional adoption"],
        entities_mentioned=["Institutions"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Which institutions?",
        briefing_input_with_context,
    )

    assert "Bitcoin, SEC, ETF" in prompt
    assert "Ethereum, Shanghai, Staking" in prompt
    assert "Coinbase, Institutional, Trading" in prompt


def test_refinement_prompt_includes_signal_details(briefing_input_with_context):
    """Test that refinement prompt includes signal metrics."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Market is active.",
        key_insights=["Activity"],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Which assets are active?",
        briefing_input_with_context,
    )

    assert "Bitcoin: score=85.5, velocity=120%" in prompt
    assert "Ethereum: score=72.3, velocity=95%" in prompt


def test_refinement_prompt_includes_pattern_details(briefing_input_with_context):
    """Test that refinement prompt includes detected patterns."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Patterns suggest accumulation.",
        key_insights=["Patterns"],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Vague on patterns.",
        briefing_input_with_context,
    )

    assert "Institutional Accumulation" in prompt
    assert "Large wallet movements into exchanges" in prompt
    assert "Regulatory Pressure" in prompt
    assert "Increased regulatory scrutiny affecting prices" in prompt


def test_refinement_prompt_says_valid_json_only(briefing_input_with_context):
    """Test that refinement prompt explicitly says valid JSON only."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input_with_context,
    )

    assert "Return ONLY valid JSON" in prompt
    assert "Do NOT include any text outside the JSON object" in prompt


def test_refinement_prompt_says_no_additional_data_requests(briefing_input_with_context):
    """Test that refinement prompt forbids asking for additional data."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input_with_context,
    )

    assert "Do NOT ask for additional data or context" in prompt


def test_refinement_prompt_says_remove_unsupported_claims(briefing_input_with_context):
    """Test that refinement prompt says to remove unsupported claims."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input_with_context,
    )

    assert "If a claim is not supported by the source context, REMOVE it" in prompt


def test_refinement_prompt_no_longer_counts_only(briefing_input_with_context):
    """Test that refinement prompt does NOT include counts-only AVAILABLE DATA."""
    agent = BriefingAgent()
    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input_with_context,
    )

    # Should NOT have the old counts-only section
    assert "Signals: 2 trending entities" not in prompt
    assert "Narratives: 3 active narratives" not in prompt
    assert "Patterns: 2 detected patterns" not in prompt

    # Should have the new source context section
    assert "AVAILABLE SOURCE CONTEXT:" in prompt


def test_refinement_prompt_bounded_for_many_narratives():
    """Test that refinement prompt remains bounded for 15+ narratives."""
    agent = BriefingAgent()

    # Create 15 narratives
    narratives = [
        {
            "_id": f"narr-{i}",
            "title": f"Narrative {i}",
            "summary": f"Summary for narrative {i}" * 10,  # Make it verbose
            "entities": [f"Entity{i}A", f"Entity{i}B", f"Entity{i}C"],
            "article_count": 50 + i,
        }
        for i in range(15)
    ]

    briefing_input = BriefingInput(
        briefing_type="morning",
        signals=[{"entity": f"Sig{i}", "metrics": {"score_24h": 80.0, "velocity_24h": 100.0}} for i in range(10)],
        narratives=narratives,
        patterns=MagicMock(all_patterns=lambda: [{"name": f"Pat{i}", "description": f"Pattern {i}"} for i in range(10)]),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )

    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input,
    )

    # Should only include top 8 narratives (matching generation prompt limit)
    assert "Narrative 0" in prompt
    assert "Narrative 7" in prompt
    # Should NOT include narratives beyond 8
    assert "Narrative 8" not in prompt
    assert "Narrative 14" not in prompt

    # Should only include top 10 signals
    assert "Sig0" in prompt
    assert "Sig9" in prompt
    assert "Sig10" not in prompt

    # Should only include top 5 patterns
    assert "Pat0" in prompt
    assert "Pat4" in prompt
    assert "Pat5" not in prompt

    # Verify prompt is not excessively long (rough check)
    assert len(prompt) < 8000, "Refinement prompt too long (token explosion risk)"


def test_refinement_prompt_handles_missing_optional_fields():
    """Test that refinement prompt gracefully handles missing fields."""
    agent = BriefingAgent()

    # Narratives with minimal fields
    narratives = [
        {
            "_id": "narr-1",
            "title": "Minimal Narrative",
            # No summary
            # No entities
            # No article_count
        },
    ]

    briefing_input = BriefingInput(
        briefing_type="morning",
        signals=[],
        narratives=narratives,
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )

    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input,
    )

    # Should include the title and gracefully skip missing fields
    assert "Minimal Narrative" in prompt
    assert "Articles: 0" in prompt  # Default when missing


def test_refinement_prompt_empty_briefing_input():
    """Test that refinement prompt handles empty briefing input gracefully."""
    agent = BriefingAgent()

    briefing_input = BriefingInput(
        briefing_type="morning",
        signals=[],
        narratives=[],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )

    generated = GeneratedBriefing(
        narrative="Test briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.8,
    )

    prompt = agent._build_refinement_prompt(
        generated,
        "Critique feedback",
        briefing_input,
    )

    # Should still have the refinement instructions
    assert "REFINEMENT INSTRUCTIONS:" in prompt
    assert "Return ONLY valid JSON" in prompt
    assert "Do NOT ask for additional data or context" in prompt

    # Should not crash and should still be valid
    assert len(prompt) > 100
