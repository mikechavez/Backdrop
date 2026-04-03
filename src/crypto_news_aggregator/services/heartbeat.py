"""Pipeline heartbeat tracking.

Writes timestamps after successful pipeline stages.
Read by health endpoint to detect silent failures.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def record_heartbeat(
    db,
    stage: str,
    duration_seconds: float = 0.0,
    summary: str = "",
) -> None:
    """Record a successful pipeline stage completion.

    Uses upsert on _id=stage so there is exactly one document per stage.

    Args:
        db: MongoDB async database connection
        stage: Pipeline stage identifier (e.g., "fetch_news", "generate_briefing")
        duration_seconds: How long the stage took to complete
        summary: Human-readable summary of what was done (truncated to 500 chars)
    """
    try:
        await db.pipeline_heartbeats.update_one(
            {"_id": stage},
            {
                "$set": {
                    "last_success": datetime.now(timezone.utc),
                    "last_duration_seconds": round(duration_seconds, 1),
                    "last_result_summary": summary[:500],
                }
            },
            upsert=True,
        )
        logger.debug(f"Recorded heartbeat for {stage}: {duration_seconds:.1f}s, {summary[:50]}...")
    except Exception as e:
        # Heartbeat write should never break the pipeline itself
        logger.error(f"Failed to record heartbeat for {stage}: {e}")


async def get_heartbeat(db, stage: str) -> dict | None:
    """Get the latest heartbeat for a pipeline stage.

    Args:
        db: MongoDB async database connection
        stage: Pipeline stage identifier

    Returns:
        Heartbeat document or None if not found
    """
    try:
        return await db.pipeline_heartbeats.find_one({"_id": stage})
    except Exception as e:
        logger.error(f"Failed to get heartbeat for {stage}: {e}")
        return None
