"""
Behavioral tests for idempotent entity mention persistence (BUG-108).

A retried enrichment attempt after a partial write must not create
duplicate mentions for the same article/entity/type/primary combination.
"""

import pytest

from crypto_news_aggregator.db.operations.entity_mentions import (
    create_entity_mentions_batch_idempotent,
)


@pytest.mark.asyncio
async def test_idempotent_insert_creates_mentions(mongo_db):
    mentions = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "coindesk",
            "is_primary": True,
        }
    ]

    count = await create_entity_mentions_batch_idempotent(mentions)
    assert count == 1

    stored = await mongo_db.entity_mentions.find({"article_id": "abc123"}).to_list(length=10)
    assert len(stored) == 1
    assert stored[0]["entity"] == "Bitcoin"


@pytest.mark.asyncio
async def test_retry_after_partial_write_does_not_duplicate(mongo_db):
    """Simulates a retry: same mentions submitted twice must not double the count."""
    mentions = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "coindesk",
            "is_primary": True,
        },
        {
            "entity": "Ethereum",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "neutral",
            "confidence": 0.8,
            "source": "coindesk",
            "is_primary": False,
        },
    ]

    await create_entity_mentions_batch_idempotent(mentions)
    # Retry with identical input (as would happen after a crash mid-batch).
    await create_entity_mentions_batch_idempotent(mentions)

    stored = await mongo_db.entity_mentions.find({"article_id": "abc123"}).to_list(length=10)
    assert len(stored) == 2, "Retry must not create duplicate mentions"


@pytest.mark.asyncio
async def test_retry_updates_sentiment_without_duplicating(mongo_db):
    """A retry with updated sentiment/confidence should update in place, not duplicate."""
    first = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "neutral",
            "confidence": 0.5,
            "source": "coindesk",
            "is_primary": True,
        }
    ]
    await create_entity_mentions_batch_idempotent(first)

    second = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "positive",
            "confidence": 0.95,
            "source": "coindesk",
            "is_primary": True,
        }
    ]
    await create_entity_mentions_batch_idempotent(second)

    stored = await mongo_db.entity_mentions.find({"article_id": "abc123"}).to_list(length=10)
    assert len(stored) == 1
    assert stored[0]["sentiment"] == "positive"
    assert stored[0]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_primary_and_context_mention_for_same_entity_are_distinct(mongo_db):
    """is_primary is part of the uniqueness key: the same entity can appear
    both as a primary and context mention on distinct records if extraction
    logic ever produces that (defensive; normal pipeline dedupes upstream)."""
    mentions = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "positive",
            "is_primary": True,
        },
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "abc123",
            "sentiment": "positive",
            "is_primary": False,
        },
    ]
    await create_entity_mentions_batch_idempotent(mentions)

    stored = await mongo_db.entity_mentions.find({"article_id": "abc123"}).to_list(length=10)
    assert len(stored) == 2


# The concurrent-upsert-under-a-real-unique-index test and the index
# rollout tests themselves (preflight, creation, idempotency) live in
# test_entity_mentions_index_rollout.py, using a dedicated scratch
# collection. Creating a real persistent unique index in a test that shares
# the entity_mentions collection with every other test in this file was
# found to race the mongo_db fixture's per-test drop_database/recreate
# cycle under sustained load (a background index build from one test
# overlapping the next test's drop_database), causing cross-test data
# bleed. Isolating index-creating tests to their own collection eliminates
# that interaction entirely rather than relying on timing to avoid it.
