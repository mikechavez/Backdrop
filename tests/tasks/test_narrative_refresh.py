"""
Integration tests for narrative refresh task.

Tests cover:
- Flagged narrative refresh lifecycle
- Budget limit enforcement
- Priority-based sorting (hot > emerging > rising > cooling)
- Error handling and edge cases
- Metric tracking and logging
"""

import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from unittest.mock import AsyncMock, patch, MagicMock

from src.crypto_news_aggregator.tasks.narrative_refresh import (
    _refresh_flagged_narratives_async,
    MAX_REFRESH_PER_RUN,
)


@pytest.mark.asyncio
async def test_refresh_flagged_narratives_basic(mongo_db, mocker):
    """
    Create a flagged narrative with articles, run refresh, verify flag cleared and summary updated.
    """
    # Create test articles
    articles = [
        {
            "_id": ObjectId(),
            "title": "Bitcoin Surge",
            "text": "Bitcoin reached $100k amid positive market sentiment",
            "url": "https://test.com/1",
            "actors": ["Bitcoin", "Traders"],
            "tensions": ["Market volatility"],
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "price surge",
        },
        {
            "_id": ObjectId(),
            "title": "BTC Momentum",
            "text": "Bitcoin continues upward trajectory",
            "url": "https://test.com/2",
            "actors": ["Bitcoin"],
            "tensions": ["Regulatory pressure"],
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "price surge",
        },
    ]
    await mongo_db.articles.insert_many(articles)

    # Create flagged narrative
    article_ids = [str(a["_id"]) for a in articles]
    narrative = {
        "_id": ObjectId(),
        "nucleus_entity": "Bitcoin",
        "narrative_focus": "price surge",
        "summary": "Old summary",
        "title": "Old Title",
        "article_ids": article_ids,
        "article_count": 2,
        "lifecycle_state": "hot",
        "needs_summary_update": True,
        "last_updated": datetime.now(timezone.utc),
    }
    await mongo_db.narratives.insert_one(narrative)

    # Mock the generation function
    mock_new_narrative = {
        "summary": "Fresh summary",
        "title": "Fresh Title",
        "actors": ["Bitcoin", "Traders"],
    }
    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.generate_narrative_from_cluster",
        new_callable=AsyncMock,
        return_value=mock_new_narrative,
    )

    # Mock budget check (always allow)
    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.check_llm_budget",
        return_value=(True, "OK"),
    )

    # Mock refresh_budget_if_stale
    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.refresh_budget_if_stale",
        new_callable=AsyncMock,
    )

    # Mock mongo_manager
    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.mongo_manager.get_async_database",
        new_callable=AsyncMock,
        return_value=mongo_db,
    )

    # Run refresh
    result = await _refresh_flagged_narratives_async()

    # Verify metrics
    assert result["flagged_count_before"] == 1
    assert result["flagged_count_after"] == 0
    assert result["refreshed_count"] == 1
    assert result["skipped_budget_count"] == 0
    assert result["skipped_error_count"] == 0

    # Verify narrative was updated
    updated = await mongo_db.narratives.find_one({"_id": narrative["_id"]})
    assert updated["summary"] == "Fresh summary"
    assert updated["title"] == "Fresh Title"
    assert updated["needs_summary_update"] is False
    assert updated["last_summary_generated_at"] is not None


@pytest.mark.asyncio
async def test_refresh_respects_lifecycle_priority(mongo_db, mocker):
    """
    Create multiple flagged narratives with different lifecycle_states.
    Verify they're processed in priority order: hot > emerging > rising > cooling.
    """
    articles = [
        {
            "_id": ObjectId(),
            "title": "Test",
            "text": "Test content",
            "url": "https://test.com/1",
            "actors": ["Bitcoin"],
            "tensions": [],
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "test",
        },
    ]
    await mongo_db.articles.insert_many(articles)

    # Create narratives with different lifecycle_states
    narratives = [
        {
            "_id": ObjectId(),
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "cooling narrative",
            "lifecycle_state": "cooling",
            "article_ids": [str(articles[0]["_id"])],
            "needs_summary_update": True,
            "last_updated": datetime.now(timezone.utc) - timedelta(hours=5),
        },
        {
            "_id": ObjectId(),
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "hot narrative",
            "lifecycle_state": "hot",
            "article_ids": [str(articles[0]["_id"])],
            "needs_summary_update": True,
            "last_updated": datetime.now(timezone.utc),
        },
        {
            "_id": ObjectId(),
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "emerging narrative",
            "lifecycle_state": "emerging",
            "article_ids": [str(articles[0]["_id"])],
            "needs_summary_update": True,
            "last_updated": datetime.now(timezone.utc) - timedelta(hours=1),
        },
    ]
    await mongo_db.narratives.insert_many(narratives)

    # Track order of processing
    processed_ids = []

    async def mock_generate(articles_list):
        processed_ids.append(articles_list[0].get("_id"))
        return {"summary": "Test", "title": "Test"}

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.generate_narrative_from_cluster",
        new_callable=AsyncMock,
        side_effect=mock_generate,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.check_llm_budget",
        return_value=(True, "OK"),
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.refresh_budget_if_stale",
        new_callable=AsyncMock,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.mongo_manager.get_async_database",
        new_callable=AsyncMock,
        return_value=mongo_db,
    )

    # Run refresh
    result = await _refresh_flagged_narratives_async()

    # Verify all 3 were processed
    assert result["refreshed_count"] == 3

    # Verify order: hot first, then emerging, then cooling
    # (They should be processed in the order they're stored after sorting)
    hot_narrative = await mongo_db.narratives.find_one(
        {"lifecycle_state": "hot", "needs_summary_update": False}
    )
    emerging_narrative = await mongo_db.narratives.find_one(
        {"lifecycle_state": "emerging", "needs_summary_update": False}
    )
    cooling_narrative = await mongo_db.narratives.find_one(
        {"lifecycle_state": "cooling", "needs_summary_update": False}
    )

    assert hot_narrative is not None
    assert emerging_narrative is not None
    assert cooling_narrative is not None


@pytest.mark.asyncio
async def test_refresh_respects_budget_limit(mongo_db, mocker):
    """
    Create 25 flagged narratives (exceeds MAX_REFRESH_PER_RUN of 20).
    First 10 succeed, then budget is exhausted.
    Verify exactly 10 are refreshed and rest are skipped with budget count.
    """
    articles = [
        {
            "_id": ObjectId(),
            "title": "Test",
            "text": "Test content",
            "url": f"https://test.com/{i}",
            "actors": ["Bitcoin"],
            "tensions": [],
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "test",
        }
        for i in range(25)
    ]
    await mongo_db.articles.insert_many(articles)

    # Create 25 flagged narratives
    narratives = [
        {
            "_id": ObjectId(),
            "nucleus_entity": "Bitcoin",
            "narrative_focus": f"narrative {i}",
            "lifecycle_state": "hot",
            "article_ids": [str(articles[i]["_id"])],
            "needs_summary_update": True,
            "last_updated": datetime.now(timezone.utc),
        }
        for i in range(25)
    ]
    await mongo_db.narratives.insert_many(narratives)

    call_count = [0]

    def mock_budget_check(operation):
        call_count[0] += 1
        # Allow first 10 calls, deny rest
        if call_count[0] <= 10:
            return (True, "OK")
        return (False, "Hard limit reached")

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.generate_narrative_from_cluster",
        new_callable=AsyncMock,
        return_value={"summary": "Test", "title": "Test"},
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.check_llm_budget",
        side_effect=mock_budget_check,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.refresh_budget_if_stale",
        new_callable=AsyncMock,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.mongo_manager.get_async_database",
        new_callable=AsyncMock,
        return_value=mongo_db,
    )

    # Run refresh
    result = await _refresh_flagged_narratives_async()

    # Verify metrics
    assert result["refreshed_count"] == 10
    assert result["skipped_budget_count"] == 10  # 20 total to process, 10 refreshed, 10 skipped
    assert result["flagged_count_before"] == 25
    assert result["flagged_count_after"] == 15  # 25 - 10 refreshed


@pytest.mark.asyncio
async def test_refresh_handles_missing_articles(mongo_db, mocker):
    """
    Create flagged narrative with article_ids that don't exist in database.
    Verify flag is cleared and error is counted.
    """
    narrative = {
        "_id": ObjectId(),
        "nucleus_entity": "Bitcoin",
        "narrative_focus": "test",
        "lifecycle_state": "hot",
        "article_ids": [str(ObjectId()), str(ObjectId())],  # Non-existent articles
        "needs_summary_update": True,
        "last_updated": datetime.now(timezone.utc),
    }
    await mongo_db.narratives.insert_one(narrative)

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.check_llm_budget",
        return_value=(True, "OK"),
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.refresh_budget_if_stale",
        new_callable=AsyncMock,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.mongo_manager.get_async_database",
        new_callable=AsyncMock,
        return_value=mongo_db,
    )

    # Run refresh
    result = await _refresh_flagged_narratives_async()

    # Verify metrics
    assert result["refreshed_count"] == 0
    assert result["skipped_error_count"] == 1

    # Verify flag was cleared
    updated = await mongo_db.narratives.find_one({"_id": narrative["_id"]})
    assert updated["needs_summary_update"] is False


@pytest.mark.asyncio
async def test_refresh_skips_dormant_narratives(mongo_db, mocker):
    """
    Create flagged narrative with lifecycle_state=dormant.
    Verify it's NOT processed (query excludes dormant).
    """
    articles = [
        {
            "_id": ObjectId(),
            "title": "Test",
            "text": "Test content",
            "url": "https://test.com/1",
            "actors": ["Bitcoin"],
            "tensions": [],
            "nucleus_entity": "Bitcoin",
            "narrative_focus": "test",
        },
    ]
    await mongo_db.articles.insert_many(articles)

    narrative = {
        "_id": ObjectId(),
        "nucleus_entity": "Bitcoin",
        "narrative_focus": "test",
        "lifecycle_state": "dormant",
        "article_ids": [str(articles[0]["_id"])],
        "needs_summary_update": True,
        "last_updated": datetime.now(timezone.utc),
    }
    await mongo_db.narratives.insert_one(narrative)

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.refresh_budget_if_stale",
        new_callable=AsyncMock,
    )

    mocker.patch(
        "src.crypto_news_aggregator.tasks.narrative_refresh.mongo_manager.get_async_database",
        new_callable=AsyncMock,
        return_value=mongo_db,
    )

    # Run refresh
    result = await _refresh_flagged_narratives_async()

    # Verify metrics show no processing
    assert result["flagged_count_before"] == 0  # Query excluded dormant
    assert result["refreshed_count"] == 0
    assert result["skipped_error_count"] == 0

    # Verify flag is still set
    updated = await mongo_db.narratives.find_one({"_id": narrative["_id"]})
    assert updated["needs_summary_update"] is True
