"""
Shared narrative trust helpers for summary freshness and validity.

Used by briefing agent and narrative API to determine if a narrative's
generated summary is fresh and trustworthy for display/synthesis.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from crypto_news_aggregator.core.config import get_settings

logger = logging.getLogger(__name__)

# Fresh-start cutoff cache (parsed once at module load)
_fresh_start_cutoff: Optional[datetime] = None


def get_fresh_start_cutoff() -> datetime:
    """Parse and cache the fresh-start cutoff from config.

    Falls back to explicit default 2026-05-10T00:00:00Z if config is malformed.
    Logs errors to alert operators of misconfiguration.
    """
    global _fresh_start_cutoff
    if _fresh_start_cutoff is not None:
        return _fresh_start_cutoff

    settings = get_settings()
    cutoff_str = settings.FRESH_START_CUTOFF

    try:
        _fresh_start_cutoff = datetime.fromisoformat(cutoff_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        logger.error(
            f"Invalid FRESH_START_CUTOFF config: {cutoff_str} — {e}. "
            f"Falling back to explicit default 2026-05-10T00:00:00Z. "
            f"Please check environment configuration."
        )
        # Fail safe: use explicit default (not epoch)
        _fresh_start_cutoff = datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc)

    return _fresh_start_cutoff


def is_narrative_summary_trusted(narrative: Dict[str, Any], cutoff: datetime) -> bool:
    """Return True if this narrative summary is trusted.

    A narrative is trusted if ANY of these are true:
    - first_seen >= cutoff
    - last_summary_generated_at >= cutoff
    - _fresh_start_validated_at >= cutoff

    Returns False for missing or malformed timestamps (fail-closed).
    """
    # Check first_seen
    first_seen = narrative.get("first_seen")
    if first_seen:
        try:
            if isinstance(first_seen, datetime):
                first_seen_dt = first_seen
            else:
                first_seen_dt = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))

            # Ensure timezone aware for comparison
            if first_seen_dt.tzinfo is None:
                first_seen_dt = first_seen_dt.replace(tzinfo=timezone.utc)

            if first_seen_dt >= cutoff:
                return True
        except (ValueError, AttributeError, TypeError):
            pass  # Malformed: fail closed

    # Check last_summary_generated_at
    last_summary_gen = narrative.get("last_summary_generated_at")
    if last_summary_gen:
        try:
            if isinstance(last_summary_gen, datetime):
                last_summary_gen_dt = last_summary_gen
            else:
                last_summary_gen_dt = datetime.fromisoformat(str(last_summary_gen).replace("Z", "+00:00"))

            # Ensure timezone aware for comparison
            if last_summary_gen_dt.tzinfo is None:
                last_summary_gen_dt = last_summary_gen_dt.replace(tzinfo=timezone.utc)

            if last_summary_gen_dt >= cutoff:
                return True
        except (ValueError, AttributeError, TypeError):
            pass  # Malformed: fail closed

    # Check _fresh_start_validated_at
    fresh_start_validated = narrative.get("_fresh_start_validated_at")
    if fresh_start_validated:
        try:
            if isinstance(fresh_start_validated, datetime):
                fresh_start_validated_dt = fresh_start_validated
            else:
                fresh_start_validated_dt = datetime.fromisoformat(
                    str(fresh_start_validated).replace("Z", "+00:00")
                )

            # Ensure timezone aware for comparison
            if fresh_start_validated_dt.tzinfo is None:
                fresh_start_validated_dt = fresh_start_validated_dt.replace(tzinfo=timezone.utc)

            if fresh_start_validated_dt >= cutoff:
                return True
        except (ValueError, AttributeError, TypeError):
            pass  # Malformed: fail closed

    # None of the three conditions are met
    return False
