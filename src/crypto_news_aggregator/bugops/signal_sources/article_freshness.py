"""Article freshness signal source for BugOps."""

from typing import List
from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
from ..models import BugAlertEventCreate, BugOpsSubsystem
from ...db.mongodb import mongo_manager
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class ArticleFreshnessSignalSource:
    """Monitor article ingestion freshness."""

    source_type = "article_freshness"
    root_subsystem = BugOpsSubsystem.ARTICLES.value
    severity = DETECTOR_SEVERITY["article_freshness"]
    dedupe_key = "article_freshness:articles"
    suggested_manual_check = (
        "Check RSS ingestion health, recent fetch attempts, source availability, "
        "and whether articles are being inserted with created_at timestamps."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if article ingestion has stalled.

        Returns True if:
        1. Articles were fetched recently (precondition 1)
        2. This is a publishing hour based on historical activity (precondition 2)
        3. No fresh articles exist (failure condition)

        Returns False if any precondition fails (legitimate idle) or articles are fresh.
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            # Precondition 1: Check for recent fetch activity
            fetch_lookback = now - timedelta(
                minutes=settings.BUGOPS_ARTICLE_FETCH_LOOKBACK_MINUTES
            )
            fetch_activity = await db.articles.find_one(
                {"fetched_at": {"$gte": fetch_lookback}}
            )
            if not fetch_activity:
                # No fetch attempts in lookback window - legitimate idle
                return False

            # Precondition 2: Check for historical activity at this time-of-day
            current_hour = now.hour
            history_lookback = now - timedelta(
                days=settings.BUGOPS_ARTICLE_HISTORY_LOOKBACK_DAYS
            )

            # Query documents created in the lookback window
            recent_docs = await db.articles.find(
                {"created_at": {"$gte": history_lookback}}
            ).to_list(None)

            # Filter in Python for hour matching (±1 hour window)
            has_historical_activity = False
            for doc in recent_docs:
                doc_hour = doc.get("created_at").hour
                hour_distance = min(
                    abs(doc_hour - current_hour),
                    24 - abs(doc_hour - current_hour),
                )
                if hour_distance <= 1:
                    has_historical_activity = True
                    break

            if not has_historical_activity:
                # No historical activity at this hour - legitimate idle
                return False

            # Failure condition: Check for fresh articles
            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )
            fresh_article = await db.articles.find_one(
                {"created_at": {"$gte": freshness_window}}
            )

            # If fresh article exists, healthy; if not and preconditions met, failure
            return fresh_article is None

        except Exception as e:
            logger.error(f"Error checking article freshness failure: {e}", exc_info=True)
            return False

    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if article ingestion has recovered.

        Returns True if a fresh article exists, False otherwise.
        """
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)

            freshness_window = now - timedelta(
                minutes=settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES,
                seconds=60,
            )
            fresh_article = await db.articles.find_one(
                {"created_at": {"$gte": freshness_window}}
            )

            return fresh_article is not None

        except Exception as e:
            logger.error(f"Error checking article freshness recovery: {e}", exc_info=True)
            return False

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals (not used - monitor handles alert generation)."""
        return []
