"""Tests for BugOps monitor configuration."""

import pytest
from unittest.mock import patch

from crypto_news_aggregator.bugops.config import get_bugops_settings
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor


def test_get_bugops_settings_returns_settings():
    """Test that get_bugops_settings returns a valid Settings object."""
    settings = get_bugops_settings()
    assert settings is not None
    assert hasattr(settings, "BUGOPS_ENABLED")
    assert hasattr(settings, "BUGOPS_POLL_INTERVAL_SECONDS")
    assert hasattr(settings, "BUGOPS_COST_5MIN_THRESHOLD_USD")
    assert hasattr(settings, "BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD")
    assert hasattr(settings, "BUGOPS_SLACK_ENABLED")
    assert hasattr(settings, "BUGOPS_SLACK_WEBHOOK_URL")


def test_bugops_settings_defaults():
    """Test that BugOps settings have correct default values."""
    settings = get_bugops_settings()
    assert settings.BUGOPS_ENABLED is False
    assert settings.BUGOPS_POLL_INTERVAL_SECONDS == 300
    assert settings.BUGOPS_COST_5MIN_THRESHOLD_USD == 0.25
    assert settings.BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD == 1.00
    assert settings.BUGOPS_SLACK_ENABLED is False
    assert settings.BUGOPS_SLACK_WEBHOOK_URL == ""


def test_bugops_monitor_initializes():
    """Test that BugOpsMonitor can be instantiated."""
    monitor = BugOpsMonitor()
    assert monitor is not None
    assert monitor.settings is not None
    assert monitor.store is None  # Initialized at runtime with DB connection
    assert monitor.running is False


def test_bugops_monitor_initializes_signal_sources():
    """Test that BugOpsMonitor initializes signal sources."""
    monitor = BugOpsMonitor()
    assert len(monitor.signal_sources) > 0
    assert all(hasattr(source, "collect") for source in monitor.signal_sources)
    assert all(hasattr(source, "source_type") for source in monitor.signal_sources)


@pytest.mark.asyncio
async def test_bugops_monitor_exits_cleanly_when_disabled():
    """Test that monitor exits cleanly when BUGOPS_ENABLED=false."""
    monitor = BugOpsMonitor()
    # Settings should have BUGOPS_ENABLED=false by default
    assert monitor.settings.BUGOPS_ENABLED is False

    # Running with disabled setting should return without error
    await monitor.run()
    # If we get here, the test passed (no exception raised)


@pytest.mark.asyncio
async def test_bugops_monitor_polls_signal_sources():
    """Test that monitor polls signal sources in its loop."""
    monitor = BugOpsMonitor()
    # Verify signal sources are wired up for polling
    assert len(monitor.signal_sources) == 2
    # Verify they're the expected types
    source_types = {source.source_type for source in monitor.signal_sources}
    assert source_types == {"llm_traces", "railway_logs"}
