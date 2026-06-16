"""Narrative freshness signal source for BugOps."""

from typing import List
from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
from ..models import BugAlertEventCreate, BugOpsSubsystem
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class NarrativeFreshnessSignalSource:
    """Monitor narrative refresh freshness."""

    source_type = "narrative_freshness"
    root_subsystem = BugOpsSubsystem.NARRATIVES.value
    severity = DETECTOR_SEVERITY["narrative_freshness"]
    dedupe_key = "narrative_freshness:narratives"
    suggested_manual_check = (
        "Check narrative refresh job health and confirm "
        "recent signals are available as input."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if narrative refresh has stalled.

        Returns True if:
        1. Signal scores exist recently (expected input)
        2. No fresh narratives exist (failure condition)

        Returns False if no recent signals (legitimate idle) or narratives are fresh.
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            # Precondition: Check for recent signal score input
            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )
            recent_signal = await db.signal_scores.find_one(
                {"last_updated": {"$gte": freshness_window}}
            )
            if not recent_signal:
                # No recent signals - legitimate idle (no input for narrative refresh)
                return False

            # Failure condition: Check for fresh narratives (primary field)
            fresh_narrative = await db.narratives.find_one(
                {"last_summary_generated_at": {"$gte": freshness_window}}
            )
            if fresh_narrative:
                # Healthy - recent narrative exists
                return False

            # Fallback: Check ObjectId timestamps for narratives WITHOUT last_summary_generated_at
            # Only consider narratives missing the primary field (don't override explicit stale timestamps)
            # Query last 1000 documents (sorted descending by _id) with only _id projection
            recent_narratives = (
                await db.narratives.find({"last_summary_generated_at": {"$exists": False}})
                .sort("_id", -1)
                .limit(1000)
                .projection({"_id": 1})
                .to_list(length=1000)
            )
            for narrative in recent_narratives:
                if "_id" in narrative and isinstance(narrative["_id"], ObjectId):
                    creation_time = narrative["_id"].generation_time
                    # Make generation_time aware if it's naive
                    if creation_time.tzinfo is None:
                        creation_time = creation_time.replace(tzinfo=timezone.utc)
                    if creation_time >= freshness_window:
                        # Found a recent ObjectId - healthy
                        return False

            # No fresh narratives via primary field or ObjectId fallback, and precondition met
            return True

        except Exception as e:
            logger.error(f"Error checking narrative freshness failure: {e}", exc_info=True)
            return False

    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if narrative refresh has recovered.

        Returns True if a fresh narrative exists (via primary field or ObjectId).
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )

            # Primary check: last_summary_generated_at
            fresh_narrative = await db.narratives.find_one(
                {"last_summary_generated_at": {"$gte": freshness_window}}
            )
            if fresh_narrative:
                return True

            # Fallback: Check ObjectId timestamps for narratives WITHOUT last_summary_generated_at
            # Only consider narratives missing the primary field (don't override explicit stale timestamps)
            # Query last 1000 documents (sorted descending by _id) with only _id projection
            recent_narratives = (
                await db.narratives.find({"last_summary_generated_at": {"$exists": False}})
                .sort("_id", -1)
                .limit(1000)
                .projection({"_id": 1})
                .to_list(length=1000)
            )
            for narrative in recent_narratives:
                if "_id" in narrative and isinstance(narrative["_id"], ObjectId):
                    creation_time = narrative["_id"].generation_time
                    # Make generation_time aware if it's naive
                    if creation_time.tzinfo is None:
                        creation_time = creation_time.replace(tzinfo=timezone.utc)
                    if creation_time >= freshness_window:
                        return True

            return False

        except Exception as e:
            logger.error(f"Error checking narrative freshness recovery: {e}", exc_info=True)
            return False

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals (not used - monitor handles alert generation)."""
        return []
