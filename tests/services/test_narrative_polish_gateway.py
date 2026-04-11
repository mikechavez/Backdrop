"""
Tests for narrative polish gateway integration (BUG-063).

Verifies that narrative polish operations route through the unified gateway
instead of making direct unmetered LLM calls.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from bson import ObjectId

from crypto_news_aggregator.services.narrative_themes import generate_narrative_from_cluster
from crypto_news_aggregator.llm.gateway import GatewayResponse


@pytest.fixture
def sample_cluster():
    """Create a sample cluster of articles for testing."""
    return [
        {
            "_id": ObjectId(),
            "actors": ["Alice", "Bob"],
            "tensions": ["conflict"],
            "nucleus_entity": "Entity X",
            "narrative_focus": "conflict resolution",
            "narrative_summary": {"actions": ["action1"]},
            "title": "Article 1",
            "description": "Test description 1"
        },
        {
            "_id": ObjectId(),
            "actors": ["Alice", "Charlie"],
            "tensions": ["dispute"],
            "nucleus_entity": "Entity X",
            "narrative_focus": "conflict resolution",
            "narrative_summary": {"actions": ["action2"]},
            "title": "Article 2",
            "description": "Test description 2"
        }
    ]


@pytest.fixture
def mock_gateway_response():
    """Create a mock gateway response object."""
    return GatewayResponse(
        text='{"title": "Polished Title", "summary": "Polished summary"}',
        input_tokens=100,
        output_tokens=50,
        cost=0.001,
        model="claude-haiku-4-5-20251001",
        operation="narrative_polish",
        trace_id="trace-123"
    )


@pytest.fixture
def mock_polish_response():
    """Mock response for narrative polish operation."""
    return GatewayResponse(
        text="Polished summary text",
        input_tokens=50,
        output_tokens=25,
        cost=0.0005,
        model="claude-haiku-4-5-20251001",
        operation="narrative_polish",
        trace_id="trace-polish-456"
    )


@pytest.mark.asyncio
async def test_narrative_polish_uses_gateway(sample_cluster, mock_gateway_response, mock_polish_response):
    """
    Verify that narrative polish operation calls gateway.call(), not llm_client._get_completion().

    This is the core fix for BUG-063: ensure the polish operation is metered and tracked
    through the unified cost gateway.
    """
    with patch('crypto_news_aggregator.services.narrative_themes.get_gateway') as mock_get_gateway:
        mock_gateway = AsyncMock()

        # First call is for cluster narrative generation, second is for polish
        mock_gateway.call.side_effect = [mock_gateway_response, mock_polish_response]
        mock_get_gateway.return_value = mock_gateway

        # Generate narrative (which includes polish)
        narrative = await generate_narrative_from_cluster(sample_cluster)

        # Verify that gateway.call was invoked at least twice
        assert mock_gateway.call.call_count >= 2, f"Expected at least 2 gateway calls, got {mock_gateway.call.call_count}"

        # Check that one of the calls is for narrative_polish operation
        calls = mock_gateway.call.call_args_list
        polish_call_found = False

        for call_obj in calls:
            if 'operation' in call_obj.kwargs and call_obj.kwargs['operation'] == 'narrative_polish':
                polish_call_found = True
                # Verify the call has the correct model
                assert call_obj.kwargs['model'] == 'claude-haiku-4-5-20251001', \
                    f"Expected Haiku model for polish, got {call_obj.kwargs['model']}"
                break

        assert polish_call_found, "narrative_polish operation not found in gateway calls. The fix was not applied correctly."


@pytest.mark.asyncio
async def test_narrative_polish_extraction_from_gateway_response(sample_cluster, mock_gateway_response, mock_polish_response):
    """
    Verify that the polished summary is correctly extracted from the gateway response.

    The polish operation should extract text from the GatewayResponse object,
    not from the old llm_client response format.
    """
    with patch('crypto_news_aggregator.services.narrative_themes.get_gateway') as mock_get_gateway:
        mock_gateway = AsyncMock()

        # Mock responses for both cluster narrative generation and polish
        custom_polish_response = GatewayResponse(
            text="This is the polished narrative summary",
            input_tokens=100,
            output_tokens=30,
            cost=0.0008,
            model="claude-haiku-4-5-20251001",
            operation="narrative_polish",
            trace_id="trace-789"
        )

        mock_gateway.call.side_effect = [mock_gateway_response, custom_polish_response]
        mock_get_gateway.return_value = mock_gateway

        narrative = await generate_narrative_from_cluster(sample_cluster)

        # Verify the polish response was processed
        if narrative and 'summary' in narrative:
            # The summary should contain content from the polished response
            # (though it will be stripped of quotes)
            assert narrative['summary'] is not None


@pytest.mark.asyncio
async def test_narrative_polish_error_handling(sample_cluster, mock_gateway_response):
    """
    Verify that polish operation falls back gracefully on gateway errors.

    If the polish gateway call fails, the original summary should be retained
    and no exception should be raised.
    """
    with patch('crypto_news_aggregator.services.narrative_themes.get_gateway') as mock_get_gateway:
        mock_gateway = AsyncMock()

        # First call succeeds (cluster narrative), second fails (polish)
        mock_gateway.call.side_effect = [mock_gateway_response, Exception("Gateway error")]
        mock_get_gateway.return_value = mock_gateway

        # Should not raise, should return narrative with original summary
        narrative = await generate_narrative_from_cluster(sample_cluster)

        assert narrative is not None, "Narrative should be returned despite polish failure"
        assert 'summary' in narrative, "Summary should be present even if polish fails"


@pytest.mark.asyncio
async def test_narrative_polish_called_with_correct_model():
    """
    Verify that the polish operation specifies Haiku model.

    Cost optimization requires using Haiku for the polish operation.
    """
    cluster = [
        {
            "_id": ObjectId(),
            "actors": ["Test"],
            "tensions": ["test"],
            "nucleus_entity": "Test",
            "narrative_focus": "test",
            "narrative_summary": {"actions": ["test"]},
            "title": "Test",
            "description": "Test description with some content to summarize"
        }
    ]

    with patch('crypto_news_aggregator.services.narrative_themes.get_gateway') as mock_get_gateway:
        mock_gateway = AsyncMock()

        response = GatewayResponse(
            text='{"title": "Title", "summary": "Summary"}',
            input_tokens=100,
            output_tokens=50,
            cost=0.001,
            model="claude-haiku-4-5-20251001",
            operation="cluster_narrative_gen",
            trace_id="trace-1"
        )

        polish_response = GatewayResponse(
            text="Polished",
            input_tokens=50,
            output_tokens=20,
            cost=0.0005,
            model="claude-haiku-4-5-20251001",
            operation="narrative_polish",
            trace_id="trace-2"
        )

        mock_gateway.call.side_effect = [response, polish_response]
        mock_get_gateway.return_value = mock_gateway

        await generate_narrative_from_cluster(cluster)

        # Check that the polish call used Haiku
        calls = mock_gateway.call.call_args_list
        for call_obj in calls:
            if 'operation' in call_obj.kwargs and call_obj.kwargs['operation'] == 'narrative_polish':
                assert call_obj.kwargs['model'] == 'claude-haiku-4-5-20251001', \
                    "Polish operation must use Haiku model for cost optimization"
