"""
Bounded legacy migration for enrichment state (BUG-108).

Initializes the `enrichment` subdocument on legacy article records that
predate the state machine. Never runs automatically; must be invoked
explicitly (e.g. via a one-off script), and defaults to dry-run.

Eligibility rules:
  - Skip any article that already has an `enrichment` subdocument.
  - Classify as "already complete" (state = COMPLETED, no reprocessing) if the
    article shows terminal enrichment output: relevance_tier is set AND
    (relevance_tier != 1 OR sentiment.score is present). This intentionally
    does not use a bare "sentiment_score == 0.0" check, since zero is a valid
    score and does not by itself prove incompleteness.
  - Otherwise classify as "incomplete" (state = PENDING, eligible for the
    normal enrichment worker to pick up).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorCollection

from .enrichment_state import ENRICHMENT_FIELD, EnrichmentStatus, is_legacy_complete

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    scanned: int = 0
    already_initialized_skipped: int = 0
    classified_complete: int = 0
    classified_incomplete: int = 0
    written: int = 0
    dry_run: bool = True
    sample_ids: List[str] = field(default_factory=list)


async def migrate_legacy_enrichment_state(
    collection: AsyncIOMotorCollection,
    batch_size: int = 500,
    max_batches: int = 20,
    dry_run: bool = True,
) -> MigrationReport:
    """Bounded, observable initialization of enrichment state on legacy articles.

    Processes at most `batch_size * max_batches` articles per invocation so it
    can never run unbounded. Must be called explicitly; never wired into
    application startup.
    """
    report = MigrationReport(dry_run=dry_run)
    now = datetime.now(timezone.utc)

    last_id = None

    for _ in range(max_batches):
        query: Dict[str, Any] = {ENRICHMENT_FIELD: {"$exists": False}}
        if last_id is not None:
            # Paginate by _id so a dry run (which never writes) advances
            # through the collection instead of re-reading the same page.
            query["_id"] = {"$gt": last_id}

        batch: List[Dict[str, Any]] = []
        cursor = collection.find(query).sort("_id", 1).limit(batch_size)
        async for doc in cursor:
            batch.append(doc)

        if not batch:
            break

        last_id = batch[-1]["_id"]

        for article in batch:
            report.scanned += 1
            if len(report.sample_ids) < 10:
                report.sample_ids.append(str(article["_id"]))

            if is_legacy_complete(article):
                report.classified_complete += 1
                new_state = {
                    "status": EnrichmentStatus.COMPLETED.value,
                    "attempt_count": 1,
                    "completed_at": now,
                    "updated_at": now,
                    "owner_token": None,
                    "lease_expires_at": None,
                    "next_retry_at": None,
                    "last_error": None,
                }
            else:
                report.classified_incomplete += 1
                new_state = {
                    "status": EnrichmentStatus.PENDING.value,
                    "attempt_count": 0,
                    "completed_at": None,
                    "updated_at": now,
                    "owner_token": None,
                    "lease_expires_at": None,
                    "next_retry_at": None,
                    "last_error": None,
                }

            if not dry_run:
                # Guard against a concurrent claimer having initialized this
                # document between the read above and this write.
                result = await collection.update_one(
                    {"_id": article["_id"], ENRICHMENT_FIELD: {"$exists": False}},
                    {"$set": {ENRICHMENT_FIELD: new_state}},
                )
                if result.modified_count == 1:
                    report.written += 1

        if len(batch) < batch_size:
            break

    logger.info(
        "Legacy enrichment migration %s: scanned=%d complete=%d incomplete=%d written=%d",
        "DRY-RUN" if dry_run else "APPLIED",
        report.scanned,
        report.classified_complete,
        report.classified_incomplete,
        report.written,
    )
    return report
