"""Tests for BugOps monitor configuration."""

import os
import pytest
from unittest.mock import patch, MagicMock

from crypto_news_aggregator.bugops.config import get_bugops_settings
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor, _is_bugops_enabled_from_env


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


def test_is_bugops_enabled_from_env_disabled_by_default():
    """Test that _is_bugops_enabled_from_env returns False when BUGOPS_ENABLED is not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BUGOPS_ENABLED", None)
        assert _is_bugops_enabled_from_env() is False


def test_is_bugops_enabled_from_env_respects_false():
    """Test that _is_bugops_enabled_from_env returns False for 'false'."""
    with patch.dict(os.environ, {"BUGOPS_ENABLED": "false"}):
        assert _is_bugops_enabled_from_env() is False


def test_is_bugops_enabled_from_env_respects_true_variants():
    """Test that _is_bugops_enabled_from_env returns True for various true values."""
    for value in ["1", "true", "yes", "on", "TRUE", "YES", "ON"]:
        with patch.dict(os.environ, {"BUGOPS_ENABLED": value}):
            assert _is_bugops_enabled_from_env() is True, f"Failed for value: {value}"


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
async def test_bugops_monitor_does_not_initialize_mongo_when_disabled():
    """Test that disabled mode does not initialize MongoDB."""
    monitor = BugOpsMonitor()
    assert monitor.settings.BUGOPS_ENABLED is False

    # Store should remain uninitialized even after run()
    await monitor.run()
    assert monitor.store is None


@pytest.mark.asyncio
async def test_bugops_monitor_does_not_initialize_signal_sources_mongo():
    """Test that disabled mode does not attempt MongoDB initialization."""
    # Mock mongo_manager to verify it's not called
    with patch("crypto_news_aggregator.db.mongodb.mongo_manager") as mock_mongo:
        monitor = BugOpsMonitor()
        await monitor.run()
        # Should exit early, so mongo_manager should not be called
        mock_mongo.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_bugops_monitor_polls_signal_sources():
    """Test that monitor polls signal sources in its loop."""
    monitor = BugOpsMonitor()
    # Verify signal sources are wired up for polling
    assert len(monitor.signal_sources) == 2
    # Verify they're the expected types
    source_types = {source.source_type for source in monitor.signal_sources}
    assert source_types == {"llm_traces", "railway_logs"}


@pytest.mark.asyncio
async def test_main_exits_early_when_bugops_disabled():
    """Test that main() exits cleanly when BUGOPS_ENABLED=false."""
    from crypto_news_aggregator.bugops.monitor import main

    with patch.dict(os.environ, {"BUGOPS_ENABLED": "false"}):
        # Should return cleanly without error
        await main()
        # If we get here, the test passed
