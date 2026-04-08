"""
Test multi-pass refinement logic in briefing agent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.services.briefing_agent import BriefingAgent, GeneratedBriefing, BriefingInput
from crypto_news_aggregator.llm.gateway import GatewayResponse
from datetime import datetime, timezone


@pytest.fixture
def mock_briefing_input():
    """Create mock briefing input."""
    return BriefingInput(
        briefing_type="morning",
        signals=[],
        narratives=[{"title": "Test Narrative", "summary": "Test summary"}],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_refinement_passes_on_first_iteration(mock_briefing_input):
    """Test that refinement stops when quality check passes on first iteration."""
    agent = BriefingAgent()

    initial = GeneratedBriefing(
        narrative="Good briefing content",
        key_insights=["Insight 1"],
        entities_mentioned=["Bitcoin"],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.85,
    )

    # Mock critique to indicate no refinement needed
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = GatewayResponse(
            text='{"needs_refinement": false, "issues": []}',
            input_tokens=30,
            output_tokens=20,
            cost=0.005,
            model="claude-sonnet-4-5-20250929",
            operation="briefing_critique",
            trace_id="test-trace-1",
        )

        result = await agent._self_refine(initial, mock_briefing_input, max_iterations=2)

        # Should only call LLM once (critique only, no refinement)
        assert mock_llm.call_count == 1
        assert "Quality passed on iteration 1" in result.detected_patterns
        assert result.confidence_score == 0.85


@pytest.mark.asyncio
async def test_refinement_iterates_until_max(mock_briefing_input):
    """Test that refinement stops at max iterations."""
    agent = BriefingAgent()

    initial = GeneratedBriefing(
        narrative="Poor briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    # Mock critique to always indicate refinement needed
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_llm:
        # Critique responses always say "needs refinement"
        # Refinement responses return parseable JSON
        mock_llm.side_effect = [
            GatewayResponse(
                text='{"needs_refinement": true, "issues": ["vague claims"]}',
                input_tokens=30,
                output_tokens=20,
                cost=0.005,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_critique",
                trace_id="test-trace-2a",
            ),  # Critique 1
            GatewayResponse(
                text='{"narrative": "Refined v1", "confidence_score": 0.7}',
                input_tokens=50,
                output_tokens=50,
                cost=0.01,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_refine",
                trace_id="test-trace-2b",
            ),  # Refine 1
            GatewayResponse(
                text='{"needs_refinement": true, "issues": ["still vague"]}',
                input_tokens=30,
                output_tokens=20,
                cost=0.005,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_critique",
                trace_id="test-trace-2c",
            ),  # Critique 2
            GatewayResponse(
                text='{"narrative": "Refined v2", "confidence_score": 0.7}',
                input_tokens=50,
                output_tokens=50,
                cost=0.01,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_refine",
                trace_id="test-trace-2d",
            ),  # Refine 2
        ]

        result = await agent._self_refine(initial, mock_briefing_input, max_iterations=2)

        # Should call LLM 4 times (2 iterations × [critique + refine])
        assert mock_llm.call_count == 4
        assert "Max refinement iterations (2) reached" in result.detected_patterns
        # Confidence should be capped at 0.6
        assert result.confidence_score == 0.6


@pytest.mark.asyncio
async def test_refinement_passes_on_second_iteration(mock_briefing_input):
    """Test that refinement can pass on subsequent iterations."""
    agent = BriefingAgent()

    initial = GeneratedBriefing(
        narrative="Initial briefing",
        key_insights=[],
        entities_mentioned=[],
        detected_patterns=[],
        recommendations=[],
        confidence_score=0.7,
    )

    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [
            GatewayResponse(
                text='{"needs_refinement": true, "issues": ["missing context"]}',
                input_tokens=30,
                output_tokens=20,
                cost=0.005,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_critique",
                trace_id="test-trace-3a",
            ),  # Critique 1
            GatewayResponse(
                text='{"narrative": "Better briefing", "confidence_score": 0.85}',
                input_tokens=50,
                output_tokens=50,
                cost=0.01,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_refine",
                trace_id="test-trace-3b",
            ),  # Refine 1
            GatewayResponse(
                text='{"needs_refinement": false, "issues": []}',
                input_tokens=30,
                output_tokens=20,
                cost=0.005,
                model="claude-sonnet-4-5-20250929",
                operation="briefing_critique",
                trace_id="test-trace-3c",
            ),  # Critique 2 - passes
        ]

        result = await agent._self_refine(initial, mock_briefing_input, max_iterations=3)

        # Should call LLM 3 times (stopped after passing on iteration 2)
        assert mock_llm.call_count == 3
        assert "Quality passed on iteration 2" in result.detected_patterns
        assert result.confidence_score == 0.85
