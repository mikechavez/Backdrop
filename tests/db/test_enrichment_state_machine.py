"""
Behavioral tests for the durable enrichment state machine (BUG-108).

These tests run against a real local MongoDB (via the mongo_db fixture) and
exercise the actual claim/complete/fail/lease code paths in
db/operations/enrichment_state.py -- not source/AST inspection.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from crypto_news_aggregator.db.operations.enrichment_state import (
    EnrichmentStatus,
    claim_batch,
    is_legacy_complete,
    mark_completed,
    mark_failed,
    mark_skipped,
    renew_batch_leases,
    renew_lease,
    write_enriched_fields,
)


async def _insert_article(collection, created_at=None, **extra):
    created_at = created_at or datetime.now(timezone.utc)
    doc = {"title": "t", "url": f"https://example.com/{id(extra)}-{created_at.timestamp()}", "created_at": created_at}
    doc.update(extra)
    result = await collection.insert_one(doc)
    return result.inserted_id


@pytest.mark.asyncio
async def test_claim_batch_transitions_to_in_progress(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    assert article_id in claim.article_ids
    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.IN_PROGRESS.value
    assert doc["enrichment"]["owner_token"] == claim.owner_token
    assert doc["enrichment"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_claimed_article_not_claimable_again_until_lease_expires(mongo_db):
    collection = mongo_db.articles
    await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    first_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert len(first_claim.article_ids) == 1

    # Second claim attempt while lease is live must find nothing.
    second_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert second_claim.article_ids == []


@pytest.mark.asyncio
async def test_concurrent_claims_do_not_double_claim_same_article(mongo_db):
    """Deterministic concurrency test: two workers race to claim one article."""
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    results = await asyncio.gather(
        claim_batch(collection, cutoff_date=cutoff, limit=10),
        claim_batch(collection, cutoff_date=cutoff, limit=10),
    )

    total_claimed = sum(len(r.article_ids) for r in results)
    assert total_claimed == 1, "Exactly one worker must win the claim race"

    winners = [r for r in results if article_id in r.article_ids]
    assert len(winners) == 1


@pytest.mark.asyncio
async def test_stale_lease_is_reclaimable(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(minutes=45)

    first_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=past)
    assert article_id in first_claim.article_ids

    # Lease was set to expire 30 minutes after `past`, which is already in
    # the past relative to "now" -- so it should be reclaimable now.
    second_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert article_id in second_claim.article_ids
    assert second_claim.owner_token != first_claim.owner_token


@pytest.mark.asyncio
async def test_renew_lease_extends_expiry_for_current_owner(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    doc_before = await collection.find_one({"_id": article_id})
    lease_before = doc_before["enrichment"]["lease_expires_at"]

    renewed = await renew_lease(collection, article_id, claim.owner_token)
    assert renewed is True

    doc_after = await collection.find_one({"_id": article_id})
    lease_after = doc_after["enrichment"]["lease_expires_at"]
    assert lease_after >= lease_before


@pytest.mark.asyncio
async def test_renew_lease_fails_for_wrong_owner(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    await claim_batch(collection, cutoff_date=cutoff, limit=10)

    renewed = await renew_lease(collection, article_id, "not-the-real-owner-token")
    assert renewed is False


@pytest.mark.asyncio
async def test_mark_completed_sets_terminal_state_and_clears_lease(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    completed = await mark_completed(collection, article_id, claim.owner_token)
    assert completed is True

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.COMPLETED.value
    assert "owner_token" not in doc["enrichment"]
    assert "lease_expires_at" not in doc["enrichment"]
    assert doc["enrichment"]["completed_at"] is not None


@pytest.mark.asyncio
async def test_mark_completed_fenced_against_stale_owner(mongo_db):
    """A worker whose lease already expired and was reclaimed cannot complete
    with its stale owner_token and silently overwrite newer progress."""
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(minutes=45)
    stale_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=past)

    # Someone else reclaims after expiry.
    new_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert new_claim.owner_token != stale_claim.owner_token

    # Stale worker's completion must be rejected.
    completed = await mark_completed(collection, article_id, stale_claim.owner_token)
    assert completed is False

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.IN_PROGRESS.value
    assert doc["enrichment"]["owner_token"] == new_claim.owner_token


@pytest.mark.asyncio
async def test_mark_skipped_sets_terminal_skipped_state(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    skipped = await mark_skipped(collection, article_id, claim.owner_token, reason="tier_2_skip")
    assert skipped is True

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.SKIPPED.value
    assert doc["enrichment"]["last_error"] == "tier_2_skip"

    # A skipped article must not be reclaimable by the normal query.
    second_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert article_id not in second_claim.article_ids


@pytest.mark.asyncio
async def test_mark_failed_retryable_sets_backoff_and_stays_eligible_after_delay(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    failed = await mark_failed(collection, article_id, claim.owner_token, error_reason="llm_timeout")
    assert failed is True

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.FAILED.value
    assert doc["enrichment"]["attempt_count"] == 1
    assert doc["enrichment"]["next_retry_at"] is not None

    # Not yet eligible (backoff not elapsed).
    immediate_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert article_id not in immediate_claim.article_ids

    # Eligible once "now" is past next_retry_at.
    future = doc["enrichment"]["next_retry_at"] + timedelta(seconds=1)
    later_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=future)
    assert article_id in later_claim.article_ids


@pytest.mark.asyncio
async def test_mark_failed_at_exact_retry_cap_becomes_terminal(mongo_db):
    """Verify the exact attempt-count boundary: settings.ENRICHMENT_MAX_RETRY_ATTEMPTS
    total attempts (initial + retries), not retries alone."""
    from crypto_news_aggregator.core.config import get_settings

    settings = get_settings()
    max_attempts = settings.ENRICHMENT_MAX_RETRY_ATTEMPTS

    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    for attempt in range(1, max_attempts + 1):
        claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
        assert article_id in claim.article_ids, f"attempt {attempt} should be claimable"

        doc = await collection.find_one({"_id": article_id})
        assert doc["enrichment"]["attempt_count"] == attempt

        await mark_failed(collection, article_id, claim.owner_token, error_reason=f"failure_{attempt}")

        doc = await collection.find_one({"_id": article_id})
        if attempt < max_attempts:
            assert doc["enrichment"]["next_retry_at"] is not None
            # Force eligibility for the next loop iteration regardless of backoff duration.
            await collection.update_one(
                {"_id": article_id},
                {"$set": {"enrichment.next_retry_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
            )
        else:
            assert doc["enrichment"]["next_retry_at"] is None
            assert doc["enrichment"].get("terminal") is True

    # Terminal failure must never be claimable again.
    final_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert article_id not in final_claim.article_ids


@pytest.mark.asyncio
async def test_mark_failed_fenced_against_stale_owner(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(minutes=45)

    stale_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=past)
    new_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    failed = await mark_failed(collection, article_id, stale_claim.owner_token, error_reason="stale")
    assert failed is False

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["owner_token"] == new_claim.owner_token


@pytest.mark.asyncio
async def test_fairness_oldest_first_rotation(mongo_db):
    """On a fairness-rotation tick, older eligible articles must be claimed
    before newer ones, even though newest-first is the default ordering."""
    collection = mongo_db.articles
    now = datetime.now(timezone.utc)

    old_id = await _insert_article(collection, created_at=now - timedelta(days=5))
    new_id = await _insert_article(collection, created_at=now - timedelta(minutes=1))

    cutoff = now - timedelta(days=30)

    # rotation_tick=0 with interval=3 -> oldest-first (0 % 3 == 0)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=1, rotation_tick=0)
    assert claim.article_ids == [old_id]

    # Non-rotation tick -> newest-first
    collection2_claim = await claim_batch(collection, cutoff_date=cutoff, limit=1, rotation_tick=1)
    assert collection2_claim.article_ids == [new_id]


@pytest.mark.asyncio
async def test_age_cutoff_excludes_old_articles(mongo_db):
    collection = mongo_db.articles
    now = datetime.now(timezone.utc)
    too_old_id = await _insert_article(collection, created_at=now - timedelta(days=40))

    cutoff = now - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    assert too_old_id not in claim.article_ids


@pytest.mark.asyncio
async def test_completed_and_skipped_articles_never_reclaimed(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    await mark_completed(collection, article_id, claim.owner_token)

    second_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert article_id not in second_claim.article_ids


# --- write_enriched_fields fencing (review finding 2) ------------------


@pytest.mark.asyncio
async def test_write_enriched_fields_succeeds_for_current_owner(mongo_db):
    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    wrote = await write_enriched_fields(
        collection, article_id, claim.owner_token, {"relevance_score": 0.9}
    )
    assert wrote is True

    doc = await collection.find_one({"_id": article_id})
    assert doc["relevance_score"] == 0.9


@pytest.mark.asyncio
async def test_write_enriched_fields_rejected_for_stale_owner(mongo_db):
    """A worker whose lease already expired and was reclaimed by another
    worker must not be able to write article content -- fencing only the
    terminal mark_completed/mark_failed transitions is not enough, since the
    content write itself happens earlier and can race the reclaim."""
    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(minutes=45)

    stale_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=past)
    new_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert new_claim.owner_token != stale_claim.owner_token

    wrote = await write_enriched_fields(
        collection, article_id, stale_claim.owner_token, {"relevance_score": 0.1}
    )
    assert wrote is False

    doc = await collection.find_one({"_id": article_id})
    assert "relevance_score" not in doc, "Stale owner's write must not land"


# --- lease renewal wired into worker batches (review finding 1) --------


@pytest.mark.asyncio
async def test_renew_batch_leases_extends_all_owned_articles(mongo_db):
    collection = mongo_db.articles
    id_a = await _insert_article(collection)
    id_b = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)
    assert set(claim.article_ids) == {id_a, id_b}

    doc_before = await collection.find_one({"_id": id_a})
    lease_before = doc_before["enrichment"]["lease_expires_at"]

    still_owned = await renew_batch_leases(collection, [id_a, id_b], claim.owner_token)
    assert set(still_owned) == {id_a, id_b}

    doc_after = await collection.find_one({"_id": id_a})
    assert doc_after["enrichment"]["lease_expires_at"] >= lease_before


@pytest.mark.asyncio
async def test_renew_batch_leases_reports_lost_leases_separately(mongo_db):
    """If one article in a batch loses its lease (reclaimed elsewhere) while
    another is still owned, renew_batch_leases must renew what it can and
    report only the lost one as no-longer-owned, not fail the whole batch."""
    collection = mongo_db.articles
    id_a = await _insert_article(collection)
    id_b = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    past = datetime.now(timezone.utc) - timedelta(minutes=45)

    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=past)
    assert set(claim.article_ids) == {id_a, id_b}

    # Someone else reclaims only id_a after its lease expires.
    reclaim = await claim_batch(collection, cutoff_date=cutoff, limit=1)
    assert reclaim.article_ids == [id_a]

    still_owned = await renew_batch_leases(collection, [id_a, id_b], claim.owner_token)
    assert still_owned == [id_b]


# --- exhausted-retry sweep on stale-lease reclaim (review finding 4) ---


@pytest.mark.asyncio
async def test_stale_lease_recovery_respects_retry_cap(mongo_db):
    """A worker that repeatedly crashes on the same article (never calling
    mark_failed, so only lease expiry ever recovers it) must not be able to
    retry forever -- the total-attempt cap must be enforced even when every
    failure is a crash, not just when mark_failed() runs."""
    from crypto_news_aggregator.core.config import get_settings

    max_attempts = get_settings().ENRICHMENT_MAX_RETRY_ATTEMPTS

    collection = mongo_db.articles
    article_id = await _insert_article(collection)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Each "crash cycle" is simulated by claiming with a `now` that is
    # already past the previous claim's lease expiry (45 min lease + a
    # growing offset), so every iteration sees the prior lease as stale --
    # without ever calling mark_failed/mark_completed in between.
    claimed_attempt_counts = []
    simulated_now = datetime.now(timezone.utc) - timedelta(minutes=45)
    for _ in range(max_attempts):
        claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=simulated_now)
        assert article_id in claim.article_ids
        doc = await collection.find_one({"_id": article_id})
        claimed_attempt_counts.append(doc["enrichment"]["attempt_count"])
        # Advance past this claim's lease expiry for the next iteration,
        # simulating another crash with no mark_failed/mark_completed call.
        simulated_now = doc["enrichment"]["lease_expires_at"] + timedelta(seconds=1)

    assert claimed_attempt_counts == list(range(1, max_attempts + 1))

    # One more crash cycle: the article has now been claimed max_attempts
    # times and crashed every time. It must NOT be claimable again.
    final_claim = await claim_batch(collection, cutoff_date=cutoff, limit=10, now=simulated_now)
    assert article_id not in final_claim.article_ids

    doc = await collection.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.FAILED.value
    assert doc["enrichment"].get("terminal") is True
    assert doc["enrichment"]["attempt_count"] == max_attempts


# --- legacy-complete reconciliation between worker and migration (finding 3) --


def test_is_legacy_complete_tier1_with_sentiment():
    assert is_legacy_complete({"relevance_tier": 1, "sentiment": {"score": 0.0}}) is True


def test_is_legacy_complete_tier1_without_sentiment():
    assert is_legacy_complete({"relevance_tier": 1}) is False


def test_is_legacy_complete_tier2_always_complete():
    assert is_legacy_complete({"relevance_tier": 2}) is True


def test_is_legacy_complete_no_tier():
    assert is_legacy_complete({}) is False


@pytest.mark.asyncio
async def test_legacy_complete_article_not_claimed(mongo_db):
    """A pre-existing (never-initialized) article that already shows
    terminal legacy enrichment output must not be claimed and reprocessed by
    the worker, even though migration hasn't run to formally mark it
    COMPLETED. The worker's own eligibility query must reconcile with
    migration's classification, not just rely on migration having run."""
    collection = mongo_db.articles
    already_enriched_id = await _insert_article(
        collection,
        relevance_tier=1,
        sentiment={"score": 0.6, "label": "positive"},
    )
    genuinely_incomplete_id = await _insert_article(collection, relevance_tier=1)
    never_touched_id = await _insert_article(collection)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    assert already_enriched_id not in claim.article_ids
    assert genuinely_incomplete_id in claim.article_ids
    assert never_touched_id in claim.article_ids


@pytest.mark.asyncio
async def test_legacy_complete_tier2_article_not_claimed(mongo_db):
    collection = mongo_db.articles
    tier2_id = await _insert_article(collection, relevance_tier=2, relevance_reason="low_relevance")

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim = await claim_batch(collection, cutoff_date=cutoff, limit=10)

    assert tier2_id not in claim.article_ids
