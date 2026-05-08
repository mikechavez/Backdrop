"""Tests for SignalSource base interface."""

import pytest
from typing import List

from crypto_news_aggregator.bugops.models import BugAlertEventCreate, AlertSeverity
from crypto_news_aggregator.bugops.signal_sources.base import SignalSource
from crypto_news_aggregator.bugops.signal_sources.llm_traces import LLMTraceSignalSource
from crypto_news_aggregator.bugops.signal_sources.railway_logs import RailwayLogSignalSource


@pytest.mark.asyncio
async def test_llm_trace_signal_source_returns_empty_list():
    """Test that LLMTraceSignalSource returns empty list (placeholder)."""
    source = LLMTraceSignalSource()
    alerts = await source.collect()
    assert isinstance(alerts, list)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_railway_log_signal_source_returns_empty_list():
    """Test that RailwayLogSignalSource returns empty list (placeholder)."""
    source = RailwayLogSignalSource()
    alerts = await source.collect()
    assert isinstance(alerts, list)
    assert len(alerts) == 0


def test_llm_trace_signal_source_has_source_type():
    """Test that LLMTraceSignalSource has source_type attribute."""
    source = LLMTraceSignalSource()
    assert hasattr(source, "source_type")
    assert source.source_type == "llm_traces"


def test_railway_log_signal_source_has_source_type():
    """Test that RailwayLogSignalSource has source_type attribute."""
    source = RailwayLogSignalSource()
    assert hasattr(source, "source_type")
    assert source.source_type == "railway_logs"
