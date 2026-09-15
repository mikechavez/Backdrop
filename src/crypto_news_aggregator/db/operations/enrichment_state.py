"""
Durable enrichment state machine for article processing (BUG-108).

Persists per-article enrichment progress in MongoDB so that RSS/worker
restarts, concurrent workers, and transient failures cannot silently lose
or duplicate work. States live on the article document under the
`enrichment` subdocument:

    enrichment.status: one of PENDING, IN_PROGRESS, COMPLETED, SKIPPED, FAILED
    enrichment.owner_token: str | None      - lease ownership token
    enrichment.lease_expires_at: datetime | None
    enrichment.attempt_count: int           - total attempts made (including current)
    enrichment.next_retry_at: datetime | None
    enrichment.last_error: str | None       - last failure reason (no secrets/content)
    enrichment.completed_at: datetime | None
    enrichment.updated_at: datetime

Claiming uses an atomic find_one_and_update compare-and-set so two workers
racing on the same article never both "win" the claim. Completion and
failure writes are fenced against the owner token so a worker whose lease
already expired (and was reclaimed by someone else) cannot clobber newer
progress.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from ...core.config import get_settings

logger = logging.getLogger(__name__)


class EnrichmentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


ENRICHMENT_FIELD = "enrichment"


def _field(name: str) -> str:
    return f"{ENRICHMENT_FIELD}.{name}"


def new_owner_token() -> str:
    """Generate an unguessable per-claim ownership token."""
    return secrets.token_hex(16)


@dataclass
class ClaimBatch:
    """Result of a claim_batch call."""

    article_ids: List[Any]
    owner_token: str


def _lease_expiry(now: datetime, lease_minutes: Optional[int] = None) -> datetime:
    settings = get_settings()
    minutes = lease_minutes if lease_minutes is not None else settings.ENRICHMENT_LEASE_DURATION_MINUTES
    return now + timedelta(minutes=minutes)


def _retry_delay_minutes(attempt_count: int, base_minutes: Optional[int] = None) -> int:
    """Exponential backoff: base, base*2, base*4, ... indexed by attempt_count (1-based)."""
    settings = get_settings()
    base = base_minutes if base_minutes is not None else settings.ENRICHMENT_RETRY_BACKOFF_BASE_MINUTES
    exponent = max(0, attempt_count - 1)
    return base * (2**exponent)


def is_legacy_complete(article: Dict[str, Any]) -> bool:
    """Whether a legacy article (predating the state machine, no `enrichment`
    subdocument) already shows terminal enrichment output and must be treated
    as already-complete rather than claimable.

    Shared by the worker's own eligibility query (claim_batch/
    build_eligible_query) and by the explicit migration tool
    (enrichment_migration.py), so the two reconcile: a worker must never
    claim and reprocess an article that migration would classify complete,
    regardless of whether migration has actually been run yet.

    Tier 1 articles need a recorded sentiment.score to count as complete
    (a bare zero score is valid output, not proof of incompleteness on its
    own -- but its *absence* is). Tier 2/3 articles were deliberately
    skipped by design, so having a tier at all makes them complete.
    """
    relevance_tier = article.get("relevance_tier")
    if relevance_tier is None:
        return False
    if relevance_tier != 1:
        return True
    sentiment = article.get("sentiment")
    has_sentiment_score = isinstance(sentiment, dict) and sentiment.get("score") is not None
    return has_sentiment_score


def build_eligible_query(
    cutoff_date: datetime,
    now: Optional[datetime] = None,
    max_attempts: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the Mongo filter for articles eligible to be claimed for enrichment.

    Eligible means: within the age cutoff, AND
      - never initialized (no enrichment subdocument) AND NOT already showing
        legacy-complete enrichment output (see is_legacy_complete), OR
      - PENDING, OR
      - FAILED with next_retry_at due, OR
      - IN_PROGRESS with an expired lease AND attempt_count below the total
        attempt cap (stale claim recovery must not bypass the retry limit --
        a worker that crashes mid-attempt without ever calling mark_failed()
        must still be treated as having used up that attempt).
    Terminal states (COMPLETED, SKIPPED), the `terminal` failure flag, and
    live IN_PROGRESS leases are excluded.

    The "never initialized AND not legacy-complete" clause cannot be
    expressed as a single Mongo filter without duplicating is_legacy_complete
    as query operators (relevance_tier ne None, and (relevance_tier != 1 or
    sentiment.score exists)); that duplication is applied here. Keep this in
    sync with is_legacy_complete() if that classification logic changes.
    """
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    max_attempts = max_attempts if max_attempts is not None else settings.ENRICHMENT_MAX_RETRY_ATTEMPTS
    return {
        "created_at": {"$gte": cutoff_date},
        "$or": [
            {
                ENRICHMENT_FIELD: {"$exists": False},
                "$nor": [
                    {
                        "relevance_tier": {"$exists": True, "$ne": None},
                        "$or": [
                            {"relevance_tier": {"$ne": 1}},
                            {"sentiment.score": {"$exists": True, "$ne": None}},
                        ],
                    }
                ],
            },
            {_field("status"): EnrichmentStatus.PENDING.value},
            {
                _field("status"): EnrichmentStatus.FAILED.value,
                _field("next_retry_at"): {"$lte": now},
            },
            {
                _field("status"): EnrichmentStatus.IN_PROGRESS.value,
                _field("lease_expires_at"): {"$lte": now},
                _field("attempt_count"): {"$lt": max_attempts},
            },
        ],
    }


async def _terminally_fail_exhausted_stale_leases(
    collection: AsyncIOMotorCollection,
    cutoff_date: datetime,
    now: datetime,
    max_attempts: int,
) -> int:
    """Sweep IN_PROGRESS articles with an expired lease whose attempt_count has
    already reached the cap. These represent workers that crashed mid-attempt
    without ever calling mark_failed(); left alone they would sit outside
    build_eligible_query() forever (not reclaimable, but also never marked
    terminal). This makes the cap durable across repeated worker crashes
    instead of only being enforced when mark_failed() happens to run.
    """
    result = await collection.update_many(
        {
            "created_at": {"$gte": cutoff_date},
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("lease_expires_at"): {"$lte": now},
            _field("attempt_count"): {"$gte": max_attempts},
        },
        {
            "$set": {
                _field("status"): EnrichmentStatus.FAILED.value,
                _field("last_error"): "stale_lease_exhausted_retries",
                _field("next_retry_at"): None,
                _field("terminal"): True,
                _field("updated_at"): now,
            },
            "$unset": {
                _field("owner_token"): "",
                _field("lease_expires_at"): "",
            },
        },
    )
    return result.modified_count


async def claim_batch(
    collection: AsyncIOMotorCollection,
    cutoff_date: datetime,
    limit: int,
    rotation_tick: int = 0,
    now: Optional[datetime] = None,
) -> ClaimBatch:
    """Atomically claim up to `limit` eligible articles for this worker.

    Fairness: on ticks where `rotation_tick % ENRICHMENT_FAIRNESS_ROTATION_INTERVAL == 0`
    (rotation persisted by the caller across restarts), select oldest-first;
    otherwise newest-first. Each candidate article is claimed individually via
    find_one_and_update with a status/lease compare-and-set so concurrent
    workers cannot double-claim the same document, even when racing over the
    same candidate list.

    Before selecting candidates, sweeps stale IN_PROGRESS leases whose
    attempt_count has already reached the cap into a terminal FAILED state,
    so a worker that crashes repeatedly on the same article cannot bypass
    the total-attempt limit via lease-expiry reclaim (only mark_failed()
    checked the cap previously; crashed workers never reach it).
    """
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    max_attempts = settings.ENRICHMENT_MAX_RETRY_ATTEMPTS
    owner_token = new_owner_token()
    lease_expires_at = _lease_expiry(now)

    await _terminally_fail_exhausted_stale_leases(collection, cutoff_date, now, max_attempts)

    fairness_interval = settings.ENRICHMENT_FAIRNESS_ROTATION_INTERVAL
    oldest_first = fairness_interval > 0 and (rotation_tick % fairness_interval == 0)
    sort_order = 1 if oldest_first else -1

    query = build_eligible_query(cutoff_date, now=now, max_attempts=max_attempts)

    # Overselect candidates since concurrent claims may lose races; this cursor
    # is read-only and does not mutate state.
    candidate_ids: List[Any] = []
    cursor = collection.find(query, {"_id": 1}).sort("created_at", sort_order).limit(limit * 3 or limit)
    async for doc in cursor:
        candidate_ids.append(doc["_id"])
        if len(candidate_ids) >= limit * 3:
            break

    claimed_ids: List[Any] = []
    for article_id in candidate_ids:
        if len(claimed_ids) >= limit:
            break

        # Reuse the same "$or" eligibility clauses as build_eligible_query()
        # (minus the age filter, already applied when candidate_ids was
        # selected) pinned to this specific _id, so the CAS write can never
        # claim an article the read-side query would not itself consider
        # eligible -- including the legacy-complete exclusion.
        cas_filter = {"_id": article_id, "$or": query["$or"]}

        result = await collection.find_one_and_update(
            cas_filter,
            [
                {
                    "$set": {
                        _field("status"): EnrichmentStatus.IN_PROGRESS.value,
                        _field("owner_token"): owner_token,
                        _field("lease_expires_at"): lease_expires_at,
                        _field("attempt_count"): {
                            "$add": [
                                {
                                    "$ifNull": [f"${_field('attempt_count')}", 0]
                                },
                                1,
                            ]
                        },
                        _field("updated_at"): now,
                    }
                }
            ],
            projection={"_id": 1},
        )
        if result is not None:
            claimed_ids.append(result["_id"])

    return ClaimBatch(article_ids=claimed_ids, owner_token=owner_token)


async def renew_lease(
    collection: AsyncIOMotorCollection,
    article_id: Any,
    owner_token: str,
    now: Optional[datetime] = None,
) -> bool:
    """Extend the lease for an article still owned by owner_token. Returns True if renewed."""
    now = now or datetime.now(timezone.utc)
    result = await collection.update_one(
        {
            "_id": article_id,
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {
            "$set": {
                _field("lease_expires_at"): _lease_expiry(now),
                _field("updated_at"): now,
            }
        },
    )
    return result.modified_count == 1


async def renew_batch_leases(
    collection: AsyncIOMotorCollection,
    article_ids: List[Any],
    owner_token: str,
    now: Optional[datetime] = None,
) -> List[Any]:
    """Renew leases for every article in article_ids still owned by owner_token.

    Intended to be called periodically by a worker while it holds a claimed
    batch (e.g. once per entity-extraction sub-batch or every N seconds), so
    a batch that legitimately takes longer than ENRICHMENT_LEASE_DURATION_MINUTES
    is not silently reclaimed out from under the worker mid-processing.

    Returns the subset of article_ids still owned after the renewal attempt
    (i.e. still safe to continue processing). Any id NOT in the returned list
    has lost its lease (likely already reclaimed) and the caller must stop
    writing to it immediately -- further work on it is wasted and any write
    attempt will be rejected by write_enriched_fields()/mark_*() anyway.
    """
    now = now or datetime.now(timezone.utc)
    if not article_ids:
        return []

    result = await collection.update_many(
        {
            "_id": {"$in": article_ids},
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {
            "$set": {
                _field("lease_expires_at"): _lease_expiry(now),
                _field("updated_at"): now,
            }
        },
    )
    if result.matched_count == len(article_ids):
        return list(article_ids)

    # Some ids were no longer ours; find out which ones still are.
    still_owned = []
    cursor = collection.find(
        {
            "_id": {"$in": article_ids},
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {"_id": 1},
    )
    async for doc in cursor:
        still_owned.append(doc["_id"])
    return still_owned


async def write_enriched_fields(
    collection: AsyncIOMotorCollection,
    article_id: Any,
    owner_token: str,
    fields: Dict[str, Any],
) -> bool:
    """Write enrichment output fields (relevance/sentiment/entities/etc.) onto
    the article document, fenced by owner_token.

    Any write of enrichment *content* to the article document must go through
    this helper rather than a bare collection.update_one(), so a worker whose
    lease has already expired and been reclaimed by another worker cannot
    clobber the new owner's in-progress or completed data. Returns False if
    the caller no longer holds the lease; callers must treat that as "stop
    processing this article" rather than continuing to write.
    """
    result = await collection.update_one(
        {
            "_id": article_id,
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {"$set": fields},
    )
    return result.modified_count == 1


async def mark_completed(
    collection: AsyncIOMotorCollection,
    article_id: Any,
    owner_token: str,
    now: Optional[datetime] = None,
) -> bool:
    """Mark an article's enrichment as terminally completed, fenced by owner_token.

    Returns False (no-op) if the lease was reclaimed by another owner in the meantime,
    so callers must not assume their in-memory progress applies.
    """
    now = now or datetime.now(timezone.utc)
    result = await collection.update_one(
        {
            "_id": article_id,
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {
            "$set": {
                _field("status"): EnrichmentStatus.COMPLETED.value,
                _field("completed_at"): now,
                _field("updated_at"): now,
                _field("last_error"): None,
            },
            "$unset": {
                _field("owner_token"): "",
                _field("lease_expires_at"): "",
            },
        },
    )
    return result.modified_count == 1


async def mark_skipped(
    collection: AsyncIOMotorCollection,
    article_id: Any,
    owner_token: str,
    reason: str,
    now: Optional[datetime] = None,
) -> bool:
    """Mark an article as intentionally, terminally skipped (e.g. tier 2/3)."""
    now = now or datetime.now(timezone.utc)
    result = await collection.update_one(
        {
            "_id": article_id,
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {
            "$set": {
                _field("status"): EnrichmentStatus.SKIPPED.value,
                _field("completed_at"): now,
                _field("updated_at"): now,
                _field("last_error"): reason,
            },
            "$unset": {
                _field("owner_token"): "",
                _field("lease_expires_at"): "",
            },
        },
    )
    return result.modified_count == 1


async def mark_failed(
    collection: AsyncIOMotorCollection,
    article_id: Any,
    owner_token: str,
    error_reason: str,
    now: Optional[datetime] = None,
) -> bool:
    """Record a failed attempt, fenced by owner_token.

    If attempt_count has reached ENRICHMENT_MAX_RETRY_ATTEMPTS, the article
    transitions to a terminal FAILED state with no next_retry_at (no further
    automatic retries). Otherwise it becomes retryable FAILED with an
    exponential-backoff next_retry_at.
    """
    settings = get_settings()
    now = now or datetime.now(timezone.utc)

    doc = await collection.find_one(
        {"_id": article_id},
        {_field("attempt_count"): 1, _field("owner_token"): 1, _field("status"): 1},
    )
    if doc is None:
        return False

    enrichment = doc.get(ENRICHMENT_FIELD) or {}
    if (
        enrichment.get("status") != EnrichmentStatus.IN_PROGRESS.value
        or enrichment.get("owner_token") != owner_token
    ):
        return False

    attempt_count = enrichment.get("attempt_count", 1)
    max_attempts = settings.ENRICHMENT_MAX_RETRY_ATTEMPTS
    terminal = attempt_count >= max_attempts

    set_fields: Dict[str, Any] = {
        _field("status"): EnrichmentStatus.FAILED.value,
        _field("last_error"): error_reason[:500],
        _field("updated_at"): now,
    }
    unset_fields = {
        _field("owner_token"): "",
        _field("lease_expires_at"): "",
    }

    if terminal:
        set_fields[_field("next_retry_at")] = None
        set_fields[_field("terminal")] = True
    else:
        delay_minutes = _retry_delay_minutes(attempt_count)
        set_fields[_field("next_retry_at")] = now + timedelta(minutes=delay_minutes)

    result = await collection.update_one(
        {
            "_id": article_id,
            _field("status"): EnrichmentStatus.IN_PROGRESS.value,
            _field("owner_token"): owner_token,
        },
        {"$set": set_fields, "$unset": unset_fields},
    )
    return result.modified_count == 1
