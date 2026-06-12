"""Tests for Sprint 020 freshness detector severity mapping."""

import pytest
from crypto_news_aggregator.bugops.signal_sources.severity import DETECTOR_SEVERITY
from crypto_news_aggregator.bugops.models import AlertSeverity


def test_detector_severity_has_all_four_detectors():
    """Test that DETECTOR_SEVERITY includes all four freshness detectors."""
    assert len(DETECTOR_SEVERITY) == 4
    assert "article_freshness" in DETECTOR_SEVERITY
    assert "signal_freshness" in DETECTOR_SEVERITY
    assert "narrative_freshness" in DETECTOR_SEVERITY
    assert "briefing_freshness" in DETECTOR_SEVERITY


def test_article_freshness_severity_is_high():
    """Test ArticleFreshness detector severity is High."""
    assert DETECTOR_SEVERITY["article_freshness"] == AlertSeverity.HIGH


def test_signal_freshness_severity_is_high():
    """Test SignalFreshness detector severity is High."""
    assert DETECTOR_SEVERITY["signal_freshness"] == AlertSeverity.HIGH


def test_narrative_freshness_severity_is_high():
    """Test NarrativeFreshness detector severity is High."""
    assert DETECTOR_SEVERITY["narrative_freshness"] == AlertSeverity.HIGH


def test_briefing_freshness_severity_is_high():
    """Test BriefingFreshness detector severity is High."""
    assert DETECTOR_SEVERITY["briefing_freshness"] == AlertSeverity.HIGH


def test_all_detectors_have_high_severity():
    """Test that all Sprint 020 freshness detectors have High severity."""
    for detector_name, severity in DETECTOR_SEVERITY.items():
        assert severity == AlertSeverity.HIGH, f"{detector_name} should have High severity"
