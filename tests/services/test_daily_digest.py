"""Tests for the daily digest service."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from crypto_news_aggregator.services.daily_digest import (
    build_digest,
    format_slack_message,
    send_to_slack,
)


@pytest.mark.asyncio
async def test_build_digest():
    """Test digest building from MongoDB stats."""
    # Mock database
    mock_db = AsyncMock()

    # Mock articles count
    mock_db.articles.count_documents = AsyncMock(return_value=42)

    # Mock briefings count
    mock_db.daily_briefings.count_documents = AsyncMock(return_value=3)

    # Mock dbStats
    mock_db.command = AsyncMock(
        return_value={
            "storageSize": 250 * 1024 * 1024,  # 250 MB
        }
    )

    # Mock heartbeats
    now = datetime.now(timezone.utc)
    hb_data = {
        "fetch_news": {
            "_id": "fetch_news",
            "last_success": now - timedelta(hours=2),
            "last_result_summary": "Fetched 127 articles",
        },
        "generate_briefing": {
            "_id": "generate_briefing",
            "last_success": now - timedelta(hours=1),
            "last_result_summary": "Morning briefing generated",
        },
    }

    async def find_one_side_effect(query):
        stage = query.get("_id")
        return hb_data.get(stage)

    mock_db.pipeline_heartbeats.find_one = AsyncMock(
        side_effect=find_one_side_effect
    )

    # Build digest
    digest = await build_digest(mock_db)

    # Assertions
    assert digest["article_count_24h"] == 42
    assert digest["briefing_count_24h"] == 3
    assert digest["storage_mb"] == 250.0
    assert digest["storage_pct"] == 48.8  # 250/512 * 100

    assert "heartbeats" in digest
    assert "fetch_news" in digest["heartbeats"]
    assert "generate_briefing" in digest["heartbeats"]

    assert digest["heartbeats"]["fetch_news"]["age_hours"] == 2.0
    assert digest["heartbeats"]["generate_briefing"]["age_hours"] == 1.0


@pytest.mark.asyncio
async def test_build_digest_missing_dbstats():
    """Test digest building when dbStats is not available."""
    mock_db = AsyncMock()
    mock_db.articles.count_documents = AsyncMock(return_value=10)
    mock_db.daily_briefings.count_documents = AsyncMock(return_value=1)
    mock_db.command = AsyncMock(side_effect=Exception("Admin access required"))
    mock_db.pipeline_heartbeats.find_one = AsyncMock(return_value=None)

    digest = await build_digest(mock_db)

    assert digest["article_count_24h"] == 10
    assert digest["briefing_count_24h"] == 1
    assert digest["storage_mb"] is None
    assert digest["storage_pct"] is None


def test_format_slack_message_all_green():
    """Test Slack message formatting when all systems are nominal."""
    digest = {
        "article_count_24h": 347,
        "briefing_count_24h": 3,
        "storage_mb": 250.0,
        "storage_pct": 48.8,
        "heartbeats": {
            "fetch_news": {
                "age_hours": 1.2,
                "summary": "Fetched 127 articles",
            },
            "generate_briefing": {
                "age_hours": 2.1,
                "summary": "Morning briefing generated, 20 signals, 15 narratives",
            },
        },
        "generated_at": "2026-04-03T09:00:12Z",
    }

    message = format_slack_message(digest)

    # Check structure
    assert "blocks" in message
    assert len(message["blocks"]) == 5

    # Check header
    assert message["blocks"][0]["type"] == "header"
    assert "green_circle" in message["blocks"][0]["text"]["text"]

    # Check main section has correct content
    section_text = message["blocks"][1]["text"]["text"]
    assert "All systems nominal" in section_text
    assert "347" in section_text
    assert "3" in section_text
    assert "250.0 MB / 512 MB (48.8%)" in section_text


def test_format_slack_message_zero_articles():
    """Test Slack message formatting when no articles were ingested."""
    digest = {
        "article_count_24h": 0,
        "briefing_count_24h": 0,
        "storage_mb": 253.0,
        "storage_pct": 49.4,
        "heartbeats": {},
        "generated_at": "2026-04-03T09:00:12Z",
    }

    message = format_slack_message(digest)

    # Should be red alert
    assert "red_circle" in message["blocks"][0]["text"]["text"]
    assert "Issues detected" in message["blocks"][1]["text"]["text"]


def test_format_slack_message_storage_warning():
    """Test Slack message formatting when storage is >90%."""
    digest = {
        "article_count_24h": 50,
        "briefing_count_24h": 2,
        "storage_mb": 470.0,
        "storage_pct": 91.8,
        "heartbeats": {},
        "generated_at": "2026-04-03T09:00:12Z",
    }

    message = format_slack_message(digest)

    # Should be orange warning
    assert "orange_circle" in message["blocks"][0]["text"]["text"]
    assert "Storage warning" in message["blocks"][1]["text"]["text"]


@pytest.mark.asyncio
async def test_send_to_slack_success():
    """Test successful Slack webhook POST."""
    webhook_url = "https://hooks.slack.com/services/T123/B456/xyz"
    message = {"text": "Test message"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await send_to_slack(webhook_url, message)

        assert result is True
        mock_client.post.assert_called_once_with(webhook_url, json=message)


@pytest.mark.asyncio
async def test_send_to_slack_failure():
    """Test failed Slack webhook POST."""
    webhook_url = "https://hooks.slack.com/services/T123/B456/xyz"
    message = {"text": "Test message"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await send_to_slack(webhook_url, message)

        assert result is False
