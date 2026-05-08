"""Deterministic case report generation."""

from typing import Optional
from .models import BugCase, BugAlertEvent


def generate_case_report(case: BugCase, alert_events: list[BugAlertEvent]) -> str:
    """Generate a deterministic Markdown report from case and alert event data.

    Args:
        case: The BugCase to report on
        alert_events: List of BugAlertEvent objects associated with the case

    Returns:
        Markdown string report
    """
    lines = []

    # Header
    lines.append(f"# Case {case.case_id}: {case.title}")
    lines.append("")

    # Status and Severity
    lines.append(f"**Status:** {case.status.value}")
    lines.append(f"**Severity:** {case.severity.value}")
    lines.append("")

    # Timestamps
    lines.append(f"**Created At:** {case.created_at.isoformat()}")
    lines.append(f"**Updated At:** {case.updated_at.isoformat()}")
    lines.append("")

    # Source Types
    if case.source_types:
        lines.append(f"**Source Types:** {', '.join(case.source_types)}")
    lines.append("")

    # Dedupe Key
    lines.append(f"**Dedupe Key:** {case.dedupe_key}")
    lines.append("")

    # Summary
    if case.summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(case.summary)
        lines.append("")

    # Alert Events
    if alert_events:
        lines.append("## Alert Events")
        lines.append("")
        for event in alert_events:
            lines.append(f"- **{event.title}** ({event.alert_id})")
            if event.summary:
                lines.append(f"  - Summary: {event.summary}")
            if event.source_type:
                lines.append(f"  - Source: {event.source_type}")
            if event.severity:
                lines.append(f"  - Severity: {event.severity.value}")
        lines.append("")

    # Observed Metrics (from case metric field)
    if case.metric:
        lines.append("## Observed Metrics")
        lines.append("")
        for key, value in case.metric.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    # Known Facts (from alert event metrics)
    alert_metrics = {}
    for event in alert_events:
        if event.metric:
            for key, value in event.metric.items():
                if key not in alert_metrics:
                    alert_metrics[key] = []
                alert_metrics[key].append(value)

    if alert_metrics:
        lines.append("## Known Facts")
        lines.append("")
        for key, values in alert_metrics.items():
            lines.append(f"- {key}: {', '.join(str(v) for v in values)}")
        lines.append("")

    # Suggested Manual Checks
    if case.suggested_manual_check:
        lines.append("## Suggested Manual Checks")
        lines.append("")
        lines.append(case.suggested_manual_check)
        lines.append("")

    return "\n".join(lines).strip() + "\n"
