"""
Scheduled task to refresh narrative summaries flagged for update.

Consumes narratives where needs_summary_update=True, regenerates their
summaries via generate_narrative_from_cluster, and clears the flag.

Budget-aware: respects check_llm_budget soft/hard limits.
Capped at 20 narratives per run to prevent cost spikes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from bson import ObjectId
from celery import shared_task
from celery.utils.log import get_task_logger

from ..db.mongodb import mongo_manager
from ..services.narrative_themes import generate_narrative_from_cluster
from ..services.cost_tracker import check_llm_budget, refresh_budget_if_stale

logger = get_task_logger(__name__)

MAX_REFRESH_PER_RUN = 20

# Priority order for lifecycle_state (lower index = higher priority)
LIFECYCLE_PRIORITY = {
    "hot": 0,
    "emerging": 1,
    "rising": 2,
    "reactivated": 3,
    "cooling": 4,
}


async def _refresh_flagged_narratives_async() -> dict:
    """
    Core async logic. Returns metrics dict.
    """
    await refresh_budget_if_stale()
    db = await mongo_manager.get_async_database()

    # Explicit positive match on True. Do NOT use $ne: False (session 33 post-mortem:
    # $ne: False matches missing fields, which inflated the query to 245+ narratives).
    query = {
        "needs_summary_update": True,
        "lifecycle_state": {"$ne": "dormant"},
    }

    flagged_count_before = await db.narratives.count_documents(query)
    logger.info(f"refresh_flagged_narratives start: flagged_count={flagged_count_before}")

    cursor = db.narratives.find(query)
    candidates = await cursor.to_list(length=None)

    # Sort: lifecycle priority first, then last_updated desc
    candidates.sort(key=lambda n: (
        LIFECYCLE_PRIORITY.get(n.get("lifecycle_state", "cooling"), 99),
        -(n.get("last_updated", datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
    ))

    to_process = candidates[:MAX_REFRESH_PER_RUN]

    refreshed_count = 0
    skipped_budget_count = 0
    skipped_error_count = 0

    for narrative in to_process:
        # Per-narrative budget check
        allowed, reason = check_llm_budget("narrative_generate")
        if not allowed:
            logger.warning(
                f"refresh_flagged_narratives stopping: budget limit hit "
                f"({reason}) after {refreshed_count} refreshes"
            )
            skipped_budget_count = len(to_process) - refreshed_count - skipped_error_count
            break

        narrative_id = narrative["_id"]
        article_ids = narrative.get("article_ids", [])

        if not article_ids:
            logger.warning(f"Narrative {narrative_id} has no article_ids, clearing flag")
            await db.narratives.update_one(
                {"_id": narrative_id},
                {"$set": {"needs_summary_update": False}}
            )
            skipped_error_count += 1
            continue

        # Fetch articles
        article_object_ids = [ObjectId(aid) if isinstance(aid, str) else aid for aid in article_ids]
        articles_cursor = db.articles.find({"_id": {"$in": article_object_ids}})
        articles = await articles_cursor.to_list(length=None)

        if not articles:
            logger.warning(
                f"Narrative {narrative_id} article fetch returned empty, clearing flag"
            )
            await db.narratives.update_one(
                {"_id": narrative_id},
                {"$set": {"needs_summary_update": False}}
            )
            skipped_error_count += 1
            continue

        try:
            new_narrative = await generate_narrative_from_cluster(articles)
        except Exception as e:
            logger.exception(f"generate_narrative_from_cluster failed for {narrative_id}: {e}")
            skipped_error_count += 1
            continue

        if not new_narrative:
            logger.warning(
                f"generate_narrative_from_cluster returned None for {narrative_id}; "
                f"clearing flag to prevent retry loop"
            )
            await db.narratives.update_one(
                {"_id": narrative_id},
                {"$set": {"needs_summary_update": False}}
            )
            skipped_error_count += 1
            continue

        # Update with fresh summary, clear flag, stamp timestamp
        await db.narratives.update_one(
            {"_id": narrative_id},
            {"$set": {
                "summary": new_narrative.get("summary", narrative.get("summary")),
                "title": new_narrative.get("title", narrative.get("title")),
                "needs_summary_update": False,
                "last_summary_generated_at": datetime.now(timezone.utc),
            }}
        )
        refreshed_count += 1
        logger.info(
            f"Refreshed narrative {narrative_id} "
            f"(lifecycle_state={narrative.get('lifecycle_state')}, "
            f"article_count={len(article_ids)})"
        )

    flagged_count_after = await db.narratives.count_documents(query)

    metrics = {
        "flagged_count_before": flagged_count_before,
        "flagged_count_after": flagged_count_after,
        "refreshed_count": refreshed_count,
        "skipped_budget_count": skipped_budget_count,
        "skipped_error_count": skipped_error_count,
    }
    logger.info(f"refresh_flagged_narratives complete: {metrics}")
    return metrics


@shared_task(name="refresh_flagged_narratives")
def refresh_flagged_narratives_task() -> dict:
    """
    Celery entry point. Bridges to async core.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_refresh_flagged_narratives_async())
        return result
    finally:
        asyncio.set_event_loop(None)
        loop.close()
