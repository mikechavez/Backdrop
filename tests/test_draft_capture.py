"""
Test briefing draft capture for eval dataset building.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from bson import ObjectId

from crypto_news_aggregator.services.briefing_agent import (
    BriefingAgent,
    GeneratedBriefing,
    BriefingInput,
)
from crypto_news_aggregator.llm.gateway import GatewayResponse
from crypto_news_aggregator.llm.draft_capture import save_draft


@pytest.fixture
def mock_briefing_input():
    """Create mock briefing input."""
    return BriefingInput(
        briefing_type="morning",
        signals=[{"entity": "Bitcoin", "score": 0.85}],
        narratives=[{"title": "Test Narrative", "summary": "Test summary"}],
        patterns=MagicMock(all_patterns=lambda: []),
        memory=MagicMock(manual_inputs=[], to_prompt_context=lambda: ""),
        generated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_generated_briefing():
    """Create mock generated briefing."""
    return GeneratedBriefing(
        narrative="Test briefing content",
        key_insights=["Insight 1", "Insight 2"],
        entities_mentioned=["Bitcoin", "Ethereum"],
        detected_patterns=["Pattern 1"],
        recommendations=[{"action": "Watch Bitcoin", "reason": "High signal"}],
        confidence_score=0.85,
    )


@pytest.fixture
def mock_gateway_response():
    """Create mock gateway response with trace_id."""
    return GatewayResponse(
        text='{"narrative": "Test", "confidence_score": 0.85}',
        input_tokens=50,
        output_tokens=50,
        cost=0.01,
        model="claude-sonnet-4-5-20250929",
        operation="briefing_generate",
        trace_id="test-trace-id-123",
    )


@pytest.mark.asyncio
async def test_pre_refine_draft_saved(mock_briefing_input, mock_generated_briefing, mock_gateway_response):
    """Test that pre-refine draft is saved after initial generation."""
    agent = BriefingAgent()
    briefing_id = str(ObjectId())

    # Mock the database
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    with patch.object(agent, "_generate_with_llm") as mock_generate:
        mock_generate.return_value = (mock_generated_briefing, mock_gateway_response)

        # Call save_draft directly
        await save_draft(
            db=mock_db,
            briefing_id=briefing_id,
            trace_id=mock_gateway_response.trace_id,
            stage="pre_refine",
            model="claude-sonnet-4-5-20250929",
            generated=mock_generated_briefing,
        )

        # Verify insert_one was called with correct data
        mock_collection.insert_one.assert_called_once()
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args["briefing_id"] == briefing_id
        assert call_args["trace_id"] == mock_gateway_response.trace_id
        assert call_args["stage"] == "pre_refine"
        assert call_args["narrative"] == "Test briefing content"
        assert call_args["model"] == "claude-sonnet-4-5-20250929"


@pytest.mark.asyncio
async def test_post_refine_draft_saved(mock_briefing_input, mock_generated_briefing, mock_gateway_response):
    """Test that post-refine draft is saved with iteration number and critique."""
    agent = BriefingAgent()
    briefing_id = str(ObjectId())
    critique_text = "Needs more detail on regulation"

    # Mock the database
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    # Call save_draft with post_refine stage
    await save_draft(
        db=mock_db,
        briefing_id=briefing_id,
        trace_id=mock_gateway_response.trace_id,
        stage="post_refine_1",
        model="claude-sonnet-4-5-20250929",
        generated=mock_generated_briefing,
        critique=critique_text,
    )

    # Verify insert_one was called with correct data
    mock_collection.insert_one.assert_called_once()
    call_args = mock_collection.insert_one.call_args[0][0]
    assert call_args["stage"] == "post_refine_1"
    assert call_args["critique"] == critique_text
    assert call_args["briefing_id"] == briefing_id


@pytest.mark.asyncio
async def test_self_refine_with_draft_capture(
    mock_briefing_input, mock_generated_briefing, mock_gateway_response
):
    """Test that _self_refine saves drafts at each iteration when briefing_id and db provided."""
    agent = BriefingAgent()
    briefing_id = str(ObjectId())

    # Mock database
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    # Mock the gateway to return responses for critique and refine
    refine_response = GatewayResponse(
        text='{"narrative": "Refined text", "key_insights": ["Refined insight"], "confidence_score": 0.88}',
        input_tokens=60,
        output_tokens=60,
        cost=0.015,
        model="claude-sonnet-4-5-20250929",
        operation="briefing_refine",
        trace_id="refine-trace-id-456",
    )

    with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
        # First call: critique saying no refinement needed
        mock_llm.return_value = GatewayResponse(
            text='{"needs_refinement": false}',
            input_tokens=30,
            output_tokens=20,
            cost=0.005,
            model="claude-sonnet-4-5-20250929",
            operation="briefing_critique",
            trace_id="critique-trace-id-789",
        )

        result = await agent._self_refine(
            mock_generated_briefing,
            mock_briefing_input,
            max_iterations=2,
            briefing_id=briefing_id,
            db=mock_db,
        )

        # Should pass on first iteration (only critique call)
        assert mock_llm.call_count == 1
        assert "Quality passed on iteration 1" in result.detected_patterns


@pytest.mark.asyncio
async def test_draft_captures_all_fields(mock_generated_briefing, mock_gateway_response):
    """Test that draft capture preserves all GeneratedBriefing fields."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    briefing_id = str(ObjectId())

    await save_draft(
        db=mock_db,
        briefing_id=briefing_id,
        trace_id=mock_gateway_response.trace_id,
        stage="pre_refine",
        model="claude-sonnet-4-5-20250929",
        generated=mock_generated_briefing,
    )

    call_args = mock_collection.insert_one.call_args[0][0]

    # Verify all fields are captured
    assert call_args["narrative"] == mock_generated_briefing.narrative
    assert call_args["key_insights"] == mock_generated_briefing.key_insights
    assert call_args["entities_mentioned"] == mock_generated_briefing.entities_mentioned
    assert call_args["detected_patterns"] == mock_generated_briefing.detected_patterns
    assert call_args["recommendations"] == mock_generated_briefing.recommendations
    assert call_args["confidence_score"] == mock_generated_briefing.confidence_score
    assert "timestamp" in call_args
    assert call_args["trace_id"] == mock_gateway_response.trace_id


@pytest.mark.asyncio
async def test_save_draft_handles_db_errors(mock_generated_briefing, mock_gateway_response):
    """Test that draft capture doesn't raise on database errors (observability layer)."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    # Simulate database error
    mock_collection.insert_one.side_effect = Exception("Database error")

    briefing_id = str(ObjectId())

    # Should not raise — draft capture is observability, not critical
    await save_draft(
        db=mock_db,
        briefing_id=briefing_id,
        trace_id=mock_gateway_response.trace_id,
        stage="pre_refine",
        model="claude-sonnet-4-5-20250929",
        generated=mock_generated_briefing,
    )

    # No assertion needed — just verify it doesn't raise
