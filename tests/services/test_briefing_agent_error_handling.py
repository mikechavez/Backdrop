"""Tests for briefing_agent error handling."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from crypto_news_aggregator.services.briefing_agent import BriefingAgent
from crypto_news_aggregator.llm.exceptions import LLMError


class TestBriefingAgentErrorHandling:
    """Test BriefingAgent error handling."""

    @pytest.fixture
    def agent(self):
        """Create a BriefingAgent instance for testing."""
        return BriefingAgent(api_key="test-key")

    @pytest.mark.asyncio
    async def test_generate_briefing_llm_error_propagates(self, agent):
        """generate_briefing should propagate LLMError."""
        with patch.object(agent, "_gather_inputs") as mock_gather:
            with patch.object(agent, "_generate_with_llm") as mock_generate:
                # Mock successful input gathering
                mock_gather.return_value = MagicMock()
                # Mock LLM failure
                mock_generate.side_effect = LLMError(
                    "API error", error_type="auth_error"
                )

                with pytest.raises(LLMError) as exc_info:
                    await agent.generate_briefing()

                assert exc_info.value.error_type == "auth_error"

    @pytest.mark.asyncio
    async def test_generate_briefing_clean_skip_returns_none(self, agent):
        """generate_briefing should return None when briefing already exists (clean skip)."""
        with patch(
            "crypto_news_aggregator.services.briefing_agent.check_briefing_exists_for_slot"
        ) as mock_check:
            # Mock that briefing already exists
            mock_check.return_value = True

            result = await agent.generate_briefing()

            assert result is None
            # Verify check was called
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_briefing_non_llm_error_returns_none(self, agent):
        """generate_briefing should return None on non-LLM errors."""
        with patch.object(agent, "_gather_inputs") as mock_gather:
            # Mock a database error (not LLMError)
            mock_gather.side_effect = ValueError("Database error")

            result = await agent.generate_briefing()

            assert result is None

    @pytest.mark.asyncio
    async def test_call_llm_timeout_raises_llm_error(self, agent):
        """_call_llm should raise LLMError on timeout."""
        # Note: This would be tested with actual httpx mocking in integration tests
        # This is a placeholder showing the expected behavior
        pass

    @pytest.mark.asyncio
    async def test_generate_briefing_with_force(self, agent):
        """generate_briefing should skip existence check when force=True."""
        with patch(
            "crypto_news_aggregator.services.briefing_agent.check_briefing_exists_for_slot"
        ) as mock_check:
            with patch.object(agent, "_gather_inputs") as mock_gather:
                with patch.object(agent, "_generate_with_llm") as mock_generate:
                    # Set up mocks
                    mock_gather.return_value = MagicMock()
                    mock_generate.return_value = MagicMock()

                    # Mock the self-refine step
                    with patch.object(agent, "_self_refine") as mock_refine:
                        mock_refine.return_value = MagicMock()

                        # Mock save steps
                        with patch.object(agent, "_save_briefing") as mock_save:
                            with patch.object(agent, "_save_patterns"):
                                mock_save.return_value = {"_id": "test-id"}

                                # Call with force=True
                                await agent.generate_briefing(force=True)

                                # Verify check was NOT called when force=True
                                mock_check.assert_not_called()
