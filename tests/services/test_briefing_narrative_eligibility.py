"""Tests for FEATURE-060: Trusted summary eligibility for briefings."""

import pytest
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.services.briefing_agent import (
    _is_narrative_summary_trusted,
    get_fresh_start_cutoff,
)


class TestNarrativeTrustEligibility:
    """Test the _is_narrative_summary_trusted helper function."""

    def test_new_narrative_with_first_seen_after_cutoff(self):
        """New narrative with first_seen >= cutoff should be trusted."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "New Bitcoin Story",
            "first_seen": datetime(2026, 5, 11, tzinfo=timezone.utc),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_old_narrative_with_fresh_summary_generation(self):
        """Old narrative with last_summary_generated_at >= cutoff should be trusted."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Old But Fresh Summary",
            "first_seen": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "last_summary_generated_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_old_narrative_with_fresh_start_validated(self):
        """Old narrative with _fresh_start_validated_at >= cutoff should be trusted."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Old But Validated",
            "first_seen": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_old_narrative_with_missing_summary_generation(self):
        """Old narrative with missing last_summary_generated_at should be untrusted (fail-closed)."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Old Bitcoin Story",
            "first_seen": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is False

    def test_narrative_with_malformed_timestamp_fails_closed(self):
        """Malformed timestamp should fail closed (narrative untrusted)."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Bad Timestamp",
            "first_seen": "not-a-date",
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is False

    def test_narrative_with_missing_first_seen_uses_other_fields(self):
        """Missing first_seen should check other fields."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Missing first_seen",
            "first_seen": None,
            "last_summary_generated_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_narrative_with_timezone_naive_timestamp(self):
        """Timezone-naive timestamp should be safely compared."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "Naive timezone",
            "first_seen": datetime(2026, 5, 11),  # No timezone
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_narrative_with_iso_string_timestamp(self):
        """ISO string timestamp should be parsed and compared."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        narrative = {
            "title": "ISO string timestamp",
            "first_seen": "2026-05-11T00:00:00Z",
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_narrative_with_timestamp_exactly_at_cutoff(self):
        """Timestamp exactly at cutoff should be trusted (>= comparison)."""
        cutoff = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
        narrative = {
            "title": "At cutoff",
            "first_seen": datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_narrative_with_timestamp_before_cutoff(self):
        """Timestamp just before cutoff should be untrusted."""
        cutoff = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
        narrative = {
            "title": "Before cutoff",
            "first_seen": datetime(2026, 5, 10, 11, 59, 59, tzinfo=timezone.utc),
            "last_summary_generated_at": None,
            "_fresh_start_validated_at": None,
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is False

    def test_narrative_with_any_condition_met_is_trusted(self):
        """If any condition is met, narrative should be trusted."""
        cutoff = datetime(2026, 5, 10, tzinfo=timezone.utc)
        # Only first_seen is trusted, others are old
        narrative = {
            "title": "Mixed trust conditions",
            "first_seen": datetime(2026, 5, 11, tzinfo=timezone.utc),
            "last_summary_generated_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "_fresh_start_validated_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
        }
        assert _is_narrative_summary_trusted(narrative, cutoff) is True

    def test_get_fresh_start_cutoff_returns_parsed_datetime(self):
        """get_fresh_start_cutoff should return a datetime object."""
        cutoff = get_fresh_start_cutoff()
        assert isinstance(cutoff, datetime)
        assert cutoff.tzinfo is not None
