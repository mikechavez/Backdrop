"""Signal freshness signal source for BugOps."""

from typing import List
from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
from ..models import BugAlertEventCreate, BugOpsSubsystem
from ...db.mongodb import mongo_manager
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class SignalFreshnessSignalSource:
    """Monitor signal score computation freshness."""

    source_type = "signal_freshness"
    root_subsystem = BugOpsSubsystem.SIGNALS.value
    severity = DETECTOR_SEVERITY["signal_freshness"]
    dedupe_key = "signal_freshness:signals"
    suggested_manual_check = (
        "Check signal generation worker health and confirm "
        "recent articles are being processed into signals."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if signal score computation has stalled.

        Returns True if:
        1. Articles exist recently (expected input)
        2. No fresh signal scores exist (failure condition)

        Returns False if no recent articles (legitimate idle) or signals are fresh.
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            # Precondition: Check for recent article input
            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )
            recent_article = await db.articles.find_one(
                {"created_at": {"$gte": freshness_window}}
            )
            if not recent_article:
                # No recent articles - legitimate idle (no input to process)
                return False

            # Failure condition: Check for fresh signal scores
            fresh_signal = await db.signal_scores.find_one(
                {"last_updated": {"$gte": freshness_window}}
            )

            # If fresh signal exists, healthy; if not and precondition met, failure
            return fresh_signal is None

        except Exception as e:
            logger.error(f"Error checking signal freshness failure: {e}", exc_info=True)
            return False

    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if signal score computation has recovered.

        Returns True if a fresh signal score exists, False otherwise.
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )
            fresh_signal = await db.signal_scores.find_one(
                {"last_updated": {"$gte": freshness_window}}
            )

            return fresh_signal is not None

        except Exception as e:
            logger.error(f"Error checking signal freshness recovery: {e}", exc_info=True)
            return False

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals (not used - monitor handles alert generation)."""
        return []
