"""Briefing freshness signal source for BugOps."""

from typing import List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
from ..models import BugAlertEventCreate, BugOpsSubsystem
from ...core.config import get_settings

logger = logging.getLogger(__name__)

# EST timezone
EST = ZoneInfo("America/New_York")


class BriefingFreshnessSignalSource:
    """Monitor briefing generation freshness (schedule-based, twice daily)."""

    source_type = "briefing_freshness"
    root_subsystem = BugOpsSubsystem.BRIEFINGS.value
    severity = DETECTOR_SEVERITY["briefing_freshness"]
    dedupe_key = "briefing_freshness:briefings"
    suggested_manual_check = (
        "Check briefing generation schedule, recent narrative "
        "freshness, and whether a briefing insert was attempted."
    )

    def _get_most_recent_window(self, now_est: datetime) -> tuple[datetime, datetime]:
        """
        Determine the most recently elapsed scheduled window (morning or evening).

        Returns tuple of (window_start, window_end) in EST.
        Window extends from scheduled_hour to scheduled_hour + grace_period + tolerance.
        """
        settings = get_settings()
        morning_hour = settings.BUGOPS_BRIEFING_MORNING_HOUR_EST
        evening_hour = settings.BUGOPS_BRIEFING_EVENING_HOUR_EST
        grace_minutes = settings.BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES

        current_date = now_est.date()

        # Create morning and evening window start times for today
        morning_start = datetime(
            current_date.year, current_date.month, current_date.day,
            hour=morning_hour, minute=0, second=0, microsecond=0,
            tzinfo=EST
        )
        evening_start = datetime(
            current_date.year, current_date.month, current_date.day,
            hour=evening_hour, minute=0, second=0, microsecond=0,
            tzinfo=EST
        )

        # Determine which window most recently elapsed
        if now_est >= evening_start:
            window_start = evening_start
        elif now_est >= morning_start:
            window_start = morning_start
        else:
            # Before morning window - use yesterday's evening
            yesterday = current_date - timedelta(days=1)
            window_start = datetime(
                yesterday.year, yesterday.month, yesterday.day,
                hour=evening_hour, minute=0, second=0, microsecond=0,
                tzinfo=EST
            )

        # Window extends from start through grace period + tolerance
        window_end = window_start + timedelta(
            minutes=grace_minutes, seconds=60
        )

        return window_start, window_end

    def _minutes_since_window_start(self, now_est: datetime, window_start: datetime) -> float:
        """Calculate minutes elapsed since the scheduled window started."""
        elapsed = now_est - window_start
        return elapsed.total_seconds() / 60

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if briefing generation has stalled.

        Returns True if:
        1. Grace period has elapsed for the most recently scheduled window
        2. No briefing exists in the expected window (with tolerance)
        3. Fresh narratives exist (expected input)

        Returns False if still in grace period, briefing exists, or no fresh narratives.
        """
        try:
            settings = get_settings()
            now_utc = datetime.now(timezone.utc)
            now_est = now_utc.astimezone(EST)

            window_start, window_end = self._get_most_recent_window(now_est)

            # Check if grace period has elapsed
            minutes_since_start = self._minutes_since_window_start(now_est, window_start)
            if minutes_since_start < settings.BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES:
                # Still in grace period - legitimate idle
                return False

            # Precondition: Check for fresh narratives (expected input for briefing generation)
            narrative_lookback_minutes = settings.BUGOPS_BRIEFING_NARRATIVE_LOOKBACK_MINUTES
            narrative_window = now_utc - timedelta(minutes=narrative_lookback_minutes, seconds=60)

            fresh_narrative = await db.narratives.find_one(
                {"last_summary_generated_at": {"$gte": narrative_window}}
            )
            if not fresh_narrative:
                # No fresh narratives - legitimate idle (no input for briefing generation)
                return False

            # Failure condition: Check for briefing in the expected window range
            # Convert window times to UTC for database query
            window_start_utc = window_start.astimezone(timezone.utc)
            window_end_utc = window_end.astimezone(timezone.utc)

            briefing_in_window = await db.daily_briefings.find_one(
                {"generated_at": {"$gte": window_start_utc, "$lte": window_end_utc}}
            )

            # If briefing exists in window, healthy; if not and preconditions met, failure
            return briefing_in_window is None

        except Exception as e:
            logger.error(f"Error checking briefing freshness failure: {e}", exc_info=True)
            return False

    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool:
        """
        Check if briefing generation has recovered.

        Returns True if a briefing exists in the current scheduled window, False otherwise.
        """
        try:
            now_utc = datetime.now(timezone.utc)
            now_est = now_utc.astimezone(EST)

            window_start, window_end = self._get_most_recent_window(now_est)

            # Convert window times to UTC for database query
            window_start_utc = window_start.astimezone(timezone.utc)
            window_end_utc = window_end.astimezone(timezone.utc)

            briefing_in_window = await db.daily_briefings.find_one(
                {"generated_at": {"$gte": window_start_utc, "$lte": window_end_utc}}
            )

            return briefing_in_window is not None

        except Exception as e:
            logger.error(f"Error checking briefing freshness recovery: {e}", exc_info=True)
            return False

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals (not used - monitor handles alert generation)."""
        return []
