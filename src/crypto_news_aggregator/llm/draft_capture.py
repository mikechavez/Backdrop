"""
Briefing draft capture for eval dataset building.

Saves pre-refine and post-refine briefing outputs to MongoDB
for Sprint 14 quality evaluation.
"""

import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

COLLECTION_NAME = "briefing_drafts"
TTL_DAYS = 90


async def ensure_draft_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes on briefing_drafts collection."""
    collection = db[COLLECTION_NAME]
    await collection.create_index("timestamp", expireAfterSeconds=TTL_DAYS * 86400)
    await collection.create_index("briefing_id")
    await collection.create_index([("briefing_id", 1), ("stage", 1)])
    logger.info("briefing_drafts indexes ensured")


async def save_draft(
    db: AsyncIOMotorDatabase,
    briefing_id: str,
    trace_id: str,
    stage: str,
    model: str,
    generated,  # GeneratedBriefing dataclass
    critique: str | None = None,
) -> None:
    """Save a briefing draft to the collection."""
    try:
        collection = db[COLLECTION_NAME]
        await collection.insert_one({
            "briefing_id": briefing_id,
            "trace_id": trace_id,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc),
            "model": model,
            "narrative": generated.narrative,
            "key_insights": generated.key_insights,
            "entities_mentioned": generated.entities_mentioned,
            "detected_patterns": generated.detected_patterns,
            "recommendations": generated.recommendations,
            "confidence_score": generated.confidence_score,
            "critique": critique,
        })
        logger.info(f"Saved draft: briefing_id={briefing_id}, stage={stage}")
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        # Don't raise — draft capture is observability, not critical path
