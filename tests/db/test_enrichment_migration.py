"""
Behavioral tests for bounded legacy enrichment-state migration (BUG-108).

Verifies dry-run counts, eligibility classification, and that already
completed/enriched articles are preserved (not reset to pending).
"""

from datetime import datetime, timezone

import pytest

from crypto_news_aggregator.db.operations.enrichment_migration import (
    migrate_legacy_enrichment_state,
)
from crypto_news_aggregator.db.operations.enrichment_state import EnrichmentStatus


async def _insert(collection, **fields):
    doc = {"title": "t", "url": f"https://example.com/{fields}", "created_at": datetime.now(timezone.utc)}
    doc.update(fields)
    result = await collection.insert_one(doc)
    return result.inserted_id


@pytest.mark.asyncio
async def test_dry_run_does_not_write(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert(collection, relevance_tier=2)

    report = await migrate_legacy_enrichment_state(collection, dry_run=True)

    assert report.dry_run is True
    assert report.scanned == 1
    assert report.written == 0

    doc = await collection.find_one({"_id": article_id})
    assert "enrichment" not in doc


@pytest.mark.asyncio
async def test_already_initialized_articles_are_skipped(mongo_db):
    collection = mongo_db.articles
    await _insert(collection, enrichment={"status": EnrichmentStatus.COMPLETED.value})
    await _insert(collection, relevance_tier=2)  # legacy, uninitialized

    report = await migrate_legacy_enrichment_state(collection, dry_run=True)

    assert report.scanned == 1  # only the uninitialized one is scanned by the query


@pytest.mark.asyncio
async def test_tier1_with_sentiment_score_classified_complete(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert(
        collection, relevance_tier=1, sentiment={"score": 0.0, "label": "neutral"}
    )

    report = await migrate_legacy_enrichment_state(collection, dry_run=False)

    assert report.classified_complete == 1
    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_tier1_without_sentiment_score_classified_incomplete(mongo_db):
    """A bare zero sentiment_score elsewhere does not by itself prove
    incompleteness, but a tier-1 article with NO sentiment.score at all is
    genuinely incomplete and must be picked up by the worker."""
    collection = mongo_db.articles
    article_id = await _insert(collection, relevance_tier=1)

    report = await migrate_legacy_enrichment_state(collection, dry_run=False)

    assert report.classified_incomplete == 1
    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.PENDING.value


@pytest.mark.asyncio
async def test_tier_2_3_classified_complete_not_reprocessed(mongo_db):
    """Tier 2/3 articles were deliberately skipped by design; migration must
    not mark them pending and cause the worker to reprocess them."""
    collection = mongo_db.articles
    article_id = await _insert(collection, relevance_tier=3)

    report = await migrate_legacy_enrichment_state(collection, dry_run=False)

    assert report.classified_complete == 1
    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_article_with_no_relevance_tier_classified_incomplete(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert(collection)

    report = await migrate_legacy_enrichment_state(collection, dry_run=False)

    assert report.classified_incomplete == 1
    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.PENDING.value


@pytest.mark.asyncio
async def test_migration_is_bounded_by_batch_size_and_max_batches(mongo_db):
    collection = mongo_db.articles
    for i in range(25):
        await _insert(collection, relevance_tier=2, url=f"https://example.com/bounded-{i}")

    report = await migrate_legacy_enrichment_state(
        collection, batch_size=10, max_batches=2, dry_run=True
    )

    # Bounded to batch_size * max_batches = 20, not all 25.
    assert report.scanned == 20
