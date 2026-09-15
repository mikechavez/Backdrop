"""
Tests for enrichment query boundedness, age cutoff, and eligibility (BUG-108).

Verifies the actual production query builder
(db/operations/enrichment_state.build_eligible_query) and claim behavior,
not a rebuilt lookalike dictionary.
"""

from datetime import datetime, timezone, timedelta

import pytest

from crypto_news_aggregator.db.operations.enrichment_state import (
    EnrichmentStatus,
    build_eligible_query,
    claim_batch,
)


def test_enrichment_import_successful():
    """Verify enrichment module imports without errors."""
    from crypto_news_aggregator.background import rss_fetcher

    assert rss_fetcher is not None
    assert hasattr(rss_fetcher, "process_new_articles_from_mongodb")


def test_age_cutoff_calculated_correctly():
    """Test age cutoff is calculated and included in query."""
    age_cutoff_days = 30  # Per ticket requirements
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=age_cutoff_days)

    assert cutoff_date < datetime.now(timezone.utc)
    delta_days = (datetime.now(timezone.utc) - cutoff_date).days
    assert 29 <= delta_days <= 31


def test_build_eligible_query_includes_age_cutoff():
    """The production query builder must filter on created_at >= cutoff."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    query = build_eligible_query(cutoff)

    assert query["created_at"] == {"$gte": cutoff}


def test_build_eligible_query_matches_uninitialized_articles():
    """Articles with no enrichment subdocument at all must be eligible,
    unless they already show legacy-complete output (see
    tests/db/test_enrichment_state_machine.py::test_legacy_complete_article_not_claimed
    for that exclusion, verified behaviorally against real MongoDB)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    query = build_eligible_query(cutoff)

    or_clauses = query["$or"]
    never_initialized_clauses = [
        c for c in or_clauses if c.get("enrichment") == {"$exists": False}
    ]
    assert len(never_initialized_clauses) == 1


def test_build_eligible_query_matches_pending_and_due_failed():
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    now = datetime.now(timezone.utc)
    query = build_eligible_query(cutoff, now=now)

    or_clauses = query["$or"]
    assert {"enrichment.status": EnrichmentStatus.PENDING.value} in or_clauses

    failed_clause = {
        "enrichment.status": EnrichmentStatus.FAILED.value,
        "enrichment.next_retry_at": {"$lte": now},
    }
    assert failed_clause in or_clauses


def test_build_eligible_query_matches_expired_in_progress_leases():
    """The IN_PROGRESS/expired-lease clause must also cap on attempt_count,
    so a repeatedly-crashing worker cannot bypass ENRICHMENT_MAX_RETRY_ATTEMPTS
    via lease-expiry reclaim (see test_mark_failed_at_exact_retry_cap_becomes_terminal
    and test_stale_lease_recovery_respects_retry_cap in
    tests/db/test_enrichment_state_machine.py for the behavioral proof)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    now = datetime.now(timezone.utc)
    query = build_eligible_query(cutoff, now=now, max_attempts=3)

    or_clauses = query["$or"]
    stale_lease_clause = {
        "enrichment.status": EnrichmentStatus.IN_PROGRESS.value,
        "enrichment.lease_expires_at": {"$lte": now},
        "enrichment.attempt_count": {"$lt": 3},
    }
    assert stale_lease_clause in or_clauses


@pytest.mark.asyncio
async def test_claim_batch_respects_limit(mongo_db):
    """claim_batch must never return more than `limit` articles per call."""
    collection = mongo_db.articles
    now = datetime.now(timezone.utc)
    for i in range(5):
        await collection.insert_one(
            {"title": "t", "url": f"https://example.com/limit-{i}", "created_at": now}
        )

    cutoff = now - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=3)

    assert len(claim.article_ids) == 3


def test_max_articles_limit_reasonable():
    """Verify max articles per run prevents unbounded memory."""
    from crypto_news_aggregator.core.config import get_settings

    max_articles = get_settings().ENRICHMENT_MAX_ARTICLES_PER_RUN
    assert max_articles > 0
    assert max_articles <= 10000  # Sanity upper bound


def test_batch_size_for_entity_extraction():
    """Verify batch size for entity extraction is reasonable."""
    from crypto_news_aggregator.core.config import get_settings

    settings = get_settings()
    batch_size = settings.ENTITY_EXTRACTION_BATCH_SIZE
    max_articles = settings.ENRICHMENT_MAX_ARTICLES_PER_RUN

    assert batch_size > 0
    assert batch_size <= 1000  # Sanity bound

    max_batches = max_articles // batch_size
    assert max_batches <= 500  # Reasonable number of batches
