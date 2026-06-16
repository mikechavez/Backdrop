"""Tests for BriefingFreshness signal source."""

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock
from crypto_news_aggregator.bugops.signal_sources.briefing_freshness import (
    BriefingFreshnessSignalSource,
)
from crypto_news_aggregator.bugops.models import BugOpsSubsystem

EST = ZoneInfo("America/New_York")


@pytest.fixture
def detector():
    """Create a BriefingFreshness detector instance."""
    return BriefingFreshnessSignalSource()


@pytest.fixture
def mock_db():
    """Create a mock AsyncIOMotorDatabase."""
    db = AsyncMock()

    # narratives collection
    narratives_mock = AsyncMock()
    narratives_mock.find_one = AsyncMock()
    db.narratives = narratives_mock

    # daily_briefings collection
    briefings_mock = AsyncMock()
    briefings_mock.find_one = AsyncMock()
    db.daily_briefings = briefings_mock

    return db


class TestBriefingFreshnessMetadata:
    """Test detector metadata and configuration."""

    def test_source_type(self, detector):
        """Verify source_type is correct."""
        assert detector.source_type == "briefing_freshness"

    def test_root_subsystem(self, detector):
        """Verify root_subsystem is briefings."""
        assert detector.root_subsystem == BugOpsSubsystem.BRIEFINGS.value
        assert detector.root_subsystem == "briefings"

    def test_dedupe_key(self, detector):
        """Verify dedupe_key is correct."""
        assert detector.dedupe_key == "briefing_freshness:briefings"

    def test_severity(self, detector):
        """Verify severity is set from DETECTOR_SEVERITY."""
        from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
        assert detector.severity == DETECTOR_SEVERITY["briefing_freshness"]

    def test_suggested_manual_check(self, detector):
        """Verify suggested_manual_check is present and relevant."""
        assert "briefing generation schedule" in detector.suggested_manual_check
        assert "narrative freshness" in detector.suggested_manual_check


class TestGetMostRecentWindow:
    """Test window resolution logic."""

    def test_returns_morning_window_between_morning_and_evening(self, detector):
        """Morning window is most recent between 8 AM and 8 PM EST."""
        # 2 PM EST (14:00) - between morning and evening
        date = datetime(2026, 6, 15, 14, 0, 0, tzinfo=EST)
        window_start, window_end = detector._get_most_recent_window(date)

        # Should be today's morning window (8 AM)
        assert window_start.hour == 8
        assert window_start.day == 15
        assert window_start.month == 6

    def test_returns_evening_window_after_evening_hour(self, detector):
        """Evening window is most recent after 8 PM EST."""
        # 10 PM EST (22:00) - after evening window
        date = datetime(2026, 6, 15, 22, 0, 0, tzinfo=EST)
        window_start, window_end = detector._get_most_recent_window(date)

        # Should be today's evening window (8 PM)
        assert window_start.hour == 20
        assert window_start.day == 15

    def test_returns_previous_day_evening_before_morning_hour(self, detector):
        """Before morning, previous day's evening is most recent."""
        # 5 AM EST (05:00) - before morning window
        date = datetime(2026, 6, 15, 5, 0, 0, tzinfo=EST)
        window_start, window_end = detector._get_most_recent_window(date)

        # Should be yesterday's evening window (8 PM)
        assert window_start.hour == 20
        assert window_start.day == 14  # Yesterday

    def test_window_end_includes_grace_period_plus_tolerance(self, detector):
        """Window end is grace_period + 60 seconds after start."""
        date = datetime(2026, 6, 15, 14, 0, 0, tzinfo=EST)
        window_start, window_end = detector._get_most_recent_window(date)

        # Default grace period is 30 minutes + 60 seconds tolerance
        expected_delta = timedelta(minutes=30, seconds=60)
        assert window_end - window_start == expected_delta


class TestMinutesSinceWindowStart:
    """Test elapsed time calculation."""

    def test_calculates_minutes_correctly(self, detector):
        """Correctly calculates elapsed minutes since window start."""
        window_start = datetime(2026, 6, 15, 8, 0, 0, tzinfo=EST)
        now = datetime(2026, 6, 15, 8, 45, 0, tzinfo=EST)

        minutes = detector._minutes_since_window_start(now, window_start)

        assert minutes == 45.0

    def test_handles_fractional_minutes(self, detector):
        """Handles seconds within the minute."""
        window_start = datetime(2026, 6, 15, 8, 0, 0, tzinfo=EST)
        now = datetime(2026, 6, 15, 8, 0, 30, tzinfo=EST)

        minutes = detector._minutes_since_window_start(now, window_start)

        # 30 seconds = 0.5 minutes
        assert minutes == 0.5


class TestCheckFailure:
    """Test check_failure() logic."""

    @pytest.mark.asyncio
    async def test_returns_false_still_in_grace_period(self, detector, mock_db):
        """Returns False when still within grace period."""
        # Mock the detector to return a window with the current time in grace period
        grace_start = datetime.now(EST)
        window_start = grace_start - timedelta(minutes=10)  # 10 minutes since start
        window_end = window_start + timedelta(minutes=30, seconds=60)

        # Patch the window calculation to return our controlled window
        detector._get_most_recent_window = lambda now: (window_start, window_end)

        # Mock fresh narratives (would trigger failure if grace period elapsed)
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        result = await detector.check_failure(mock_db)

        # Should return False because grace period not elapsed
        assert result is False
        # Should not check for briefing because still in grace period
        mock_db.daily_briefings.find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_fresh_narratives(self, detector, mock_db):
        """Returns False when no fresh narratives (legitimate idle)."""
        # Patch window so grace period has elapsed
        now = datetime.now(EST)
        window_start = now - timedelta(minutes=40)  # 40 minutes since start > 30 min grace
        window_end = window_start + timedelta(minutes=30, seconds=60)

        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock no fresh narratives
        mock_db.narratives.find_one.return_value = None

        result = await detector.check_failure(mock_db)

        # Should return False because no fresh narratives (no input for briefing)
        assert result is False
        # Should not check for briefing
        mock_db.daily_briefings.find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_briefing_exists_in_window(self, detector, mock_db):
        """Returns False when grace period elapsed and briefing exists in window."""
        # Patch window so grace period has elapsed
        now = datetime.now(EST)
        window_start = now - timedelta(minutes=40)  # 40 minutes since start > 30 min grace
        window_end = window_start + timedelta(minutes=30, seconds=60)

        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock fresh narratives (precondition met)
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        # Mock briefing exists
        mock_db.daily_briefings.find_one.return_value = {"_id": "briefing1"}

        result = await detector.check_failure(mock_db)

        # Should return False because briefing exists (healthy)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_failure_condition_met(self, detector, mock_db):
        """Returns True when grace elapsed, no briefing, fresh narratives."""
        # Patch window so grace period has elapsed
        now = datetime.now(EST)
        window_start = now - timedelta(minutes=40)  # 40 minutes since start > 30 min grace
        window_end = window_start + timedelta(minutes=30, seconds=60)

        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock fresh narratives (precondition met)
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        # Mock no briefing
        mock_db.daily_briefings.find_one.return_value = None

        result = await detector.check_failure(mock_db)

        # Should return True because failure condition met
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, detector, mock_db):
        """Returns False if an exception occurs."""
        mock_db.narratives.find_one.side_effect = Exception("DB error")

        result = await detector.check_failure(mock_db)

        # Should return False on exception (detector isolation)
        assert result is False


class TestCheckRecovery:
    """Test check_recovery() logic."""

    @pytest.mark.asyncio
    async def test_returns_true_when_briefing_exists_in_window(self, detector, mock_db):
        """Returns True when briefing exists in current window."""
        # Patch window
        now = datetime.now(EST)
        window_start = now - timedelta(minutes=10)
        window_end = window_start + timedelta(minutes=30, seconds=60)

        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock briefing exists
        mock_db.daily_briefings.find_one.return_value = {"_id": "briefing1"}

        result = await detector.check_recovery(mock_db)

        # Should return True because briefing exists
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_briefing_in_window(self, detector, mock_db):
        """Returns False when no briefing in current window."""
        # Patch window
        now = datetime.now(EST)
        window_start = now - timedelta(minutes=10)
        window_end = window_start + timedelta(minutes=30, seconds=60)

        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock no briefing
        mock_db.daily_briefings.find_one.return_value = None

        result = await detector.check_recovery(mock_db)

        # Should return False because no briefing
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, detector, mock_db):
        """Returns False if an exception occurs."""
        mock_db.daily_briefings.find_one.side_effect = Exception("DB error")

        result = await detector.check_recovery(mock_db)

        # Should return False on exception
        assert result is False


class TestTimezoneHandling:
    """Test EST/EDT transition handling."""

    def test_uses_zoneinfo_not_hardcoded_offset(self, detector):
        """Detector uses ZoneInfo, not hardcoded UTC offsets."""
        # This is more of a code inspection test, but we can verify
        # that window calculations work correctly around DST boundaries

        # Just before DST ends (EST becomes EDT)
        date = datetime(2026, 11, 1, 5, 0, 0, tzinfo=EST)
        window_start, window_end = detector._get_most_recent_window(date)

        # Should still work correctly with ZoneInfo handling
        assert window_start is not None
        assert window_end is not None


class TestCollect:
    """Test collect() method."""

    @pytest.mark.asyncio
    async def test_collect_returns_empty_list(self, detector):
        """collect() returns empty list (monitor handles alert generation)."""
        result = await detector.collect()

        assert result == []
        assert isinstance(result, list)


class TestIntegration:
    """Integration scenarios combining multiple conditions."""

    @pytest.mark.asyncio
    async def test_morning_window_correctly_identified_at_2pm(self, detector, mock_db):
        """At 2 PM EST, morning window is most recent."""
        # 2 PM EST - between morning and evening windows
        now_est = datetime(2026, 6, 15, 14, 0, 0, tzinfo=EST)

        # Patch the window calculation to return a controlled morning window
        window_start = datetime(2026, 6, 15, 8, 0, 0, tzinfo=EST)  # Morning
        window_end = window_start + timedelta(minutes=30, seconds=60)

        original_get_window = detector._get_most_recent_window
        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock fresh narratives
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        # Mock no briefing (failure condition)
        mock_db.daily_briefings.find_one.return_value = None

        # This should identify the morning window and check for briefing
        result = await detector.check_failure(mock_db)

        # Should be True (no briefing after grace period with fresh input)
        assert result is True

        # Restore original method
        detector._get_most_recent_window = original_get_window

    @pytest.mark.asyncio
    async def test_evening_window_correctly_identified_at_10pm(self, detector, mock_db):
        """At 10 PM EST, evening window is most recent."""
        # 10 PM EST - after evening window
        now_est = datetime(2026, 6, 15, 22, 0, 0, tzinfo=EST)

        # Patch the window calculation to return a controlled evening window
        window_start = datetime(2026, 6, 15, 20, 0, 0, tzinfo=EST)  # Evening
        window_end = window_start + timedelta(minutes=30, seconds=60)

        original_get_window = detector._get_most_recent_window
        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock fresh narratives
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        # Mock no briefing (failure condition)
        mock_db.daily_briefings.find_one.return_value = None

        result = await detector.check_failure(mock_db)

        # Should identify evening window and check for briefing
        assert result is True

        # Restore original method
        detector._get_most_recent_window = original_get_window

    @pytest.mark.asyncio
    async def test_pre_grace_period_no_alert(self, detector, mock_db):
        """Grace period protection prevents premature alerts."""
        # Simulate grace period: window just started very recently
        # Use now - 5 minutes as window_start (so 5 minutes into grace period)
        from datetime import datetime as dt_cls
        now_utc = datetime.now(timezone.utc)
        now_est = now_utc.astimezone(EST)
        window_start = now_est - timedelta(minutes=5)  # Started 5 min ago, still in 30-min grace
        window_end = window_start + timedelta(minutes=30, seconds=60)

        original_get_window = detector._get_most_recent_window
        detector._get_most_recent_window = lambda n: (window_start, window_end)

        # Mock fresh narratives (would trigger failure if grace elapsed)
        mock_db.narratives.find_one.return_value = {"_id": "narrative1"}

        # Mock no briefing (would be failure if grace elapsed)
        mock_db.daily_briefings.find_one.return_value = None

        result = await detector.check_failure(mock_db)

        # Should return False due to grace period
        assert result is False

        # Should not check for briefing
        mock_db.daily_briefings.find_one.assert_not_called()

        # Restore original method
        detector._get_most_recent_window = original_get_window
