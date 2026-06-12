"""Sprint 020 freshness detector severity mapping.

Assigns deterministic severity to freshness detectors at detection time.
Severity is not computed dynamically from observation count or blast radius.
"""

from crypto_news_aggregator.bugops.models import AlertSeverity

DETECTOR_SEVERITY = {
    "article_freshness": AlertSeverity.HIGH,
    "signal_freshness": AlertSeverity.HIGH,
    "narrative_freshness": AlertSeverity.HIGH,
    "briefing_freshness": AlertSeverity.HIGH,
}
