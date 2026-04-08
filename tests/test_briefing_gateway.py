"""
Test briefing_agent.py integration with LLM gateway.

Verifies:
- Correct operation tags used for generate/critique/refine
- Spend cap breach aborts briefing
- 403 auth errors trigger fallback model
- Gateway is called instead of direct API
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from crypto_news_aggregator.services.briefing_agent import BriefingAgent, GeneratedBriefing, BriefingInput
from crypto_news_aggregator.llm.gateway import GatewayResponse
from crypto_news_aggregator.llm.exceptions import LLMError
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


@pytest.fixture
def agent():
    """Create BriefingAgent with mocked gateway."""
    with patch('crypto_news_aggregator.services.briefing_agent.get_gateway'):
        return BriefingAgent()


@pytest.mark.asyncio
async def test_generate_uses_correct_operation(agent):
    """Verify _call_llm with generate operation passes correct params to gateway."""
    with patch.object(agent.gateway, 'call', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = GatewayResponse(
            text="Generated text",
            input_tokens=50,
            output_tokens=50,
            cost=0.01,
            model="claude-sonnet-4-5-20250929",
            operation="briefing_generate",
            trace_id="test-trace-1",
        )

        # Call _call_llm with generate operation
        result = await agent._call_llm(
            prompt="Test prompt",
            system_prompt="Test system",
            operation="briefing_generate",
            max_tokens=4096,
        )

        # Verify gateway was called with correct operation
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['operation'] == 'briefing_generate'
        assert call_kwargs['max_tokens'] == 4096
        # Verify result is GatewayResponse
        assert isinstance(result, GatewayResponse)
        assert result.text == "Generated text"
        assert result.trace_id == "test-trace-1"


@pytest.mark.asyncio
async def test_critique_uses_correct_operation(agent):
    """Verify _call_llm with critique operation passes correct params to gateway."""
    with patch.object(agent.gateway, 'call', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = GatewayResponse(
            text='{"needs_refinement": false}',
            input_tokens=30,
            output_tokens=20,
            cost=0.005,
            model="claude-sonnet-4-5-20250929",
            operation="briefing_critique",
            trace_id="test-trace-2",
        )

        # Call _call_llm with critique operation
        result = await agent._call_llm(
            prompt="Critique prompt",
            system_prompt="Critic system",
            operation="briefing_critique",
            max_tokens=1024,
        )

        # Verify critique operation was used
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['operation'] == 'briefing_critique'
        assert call_kwargs['max_tokens'] == 1024
        # Verify result is GatewayResponse
        assert isinstance(result, GatewayResponse)
        assert result.trace_id == "test-trace-2"


@pytest.mark.asyncio
async def test_refine_uses_correct_operation(agent):
    """Verify _call_llm with refine operation passes correct params to gateway."""
    with patch.object(agent.gateway, 'call', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = GatewayResponse(
            text="Refined content",
            input_tokens=60,
            output_tokens=60,
            cost=0.015,
            model="claude-sonnet-4-5-20250929",
            operation="briefing_refine",
            trace_id="test-trace-3",
        )

        # Call _call_llm with refine operation
        result = await agent._call_llm(
            prompt="Refine prompt",
            system_prompt="Refine system",
            operation="briefing_refine",
            max_tokens=4096,
        )

        # Verify refine operation was used
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['operation'] == 'briefing_refine'
        assert call_kwargs['max_tokens'] == 4096
        # Verify result is GatewayResponse
        assert isinstance(result, GatewayResponse)
        assert result.text == "Refined content"
        assert result.trace_id == "test-trace-3"


@pytest.mark.asyncio
async def test_spend_limit_kills_briefing(agent):
    """Verify spend cap breach (LLMError spend_limit) propagates without retry."""
    with patch.object(agent.gateway, 'call', new_callable=AsyncMock) as mock_call:
        # Simulate spend cap breach
        mock_call.side_effect = LLMError(
            "Daily spend limit reached (hard limit: $0.33)",
            error_type="spend_limit",
            model="claude-sonnet-4-5-20250929"
        )

        # Should raise spend_limit, not retry
        with pytest.raises(LLMError) as exc_info:
            await agent._call_llm(
                prompt="Test",
                system_prompt="Test",
                operation="briefing_generate",
            )

        assert exc_info.value.error_type == "spend_limit"
        # Should only try primary model (no fallback for spend_limit)
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_fallback_on_403(agent):
    """Verify 403 auth error triggers fallback to secondary model."""
    # First call (primary model) raises 403
    auth_error = LLMError(
        "403 Forbidden",
        error_type="auth_error",
        model="claude-sonnet-4-5-20250929"
    )

    # Second call (fallback model) succeeds
    success_response = GatewayResponse(
        text="Fallback success",
        input_tokens=40,
        output_tokens=40,
        cost=0.008,
        model="claude-haiku-4-5-20251001",
        operation="briefing_generate",
        trace_id="test-trace-fallback",
    )

    with patch.object(agent.gateway, 'call', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [auth_error, success_response]

        result = await agent._call_llm(
            prompt="Test",
            system_prompt="Test",
            operation="briefing_generate",
        )

        # Should have retried (2 calls)
        assert mock_call.call_count == 2

        # Second call should use fallback model
        second_call_kwargs = mock_call.call_args_list[1].kwargs
        assert second_call_kwargs['model'] == "claude-haiku-4-5-20251001"
        assert isinstance(result, GatewayResponse)
        assert result.text == "Fallback success"
        assert result.model == "claude-haiku-4-5-20251001"
