"""BugOps Slack notification helper."""

import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional
from .models import BugCase, AlertSeverity
from .config import get_bugops_settings

logger = logging.getLogger(__name__)


async def route_and_send_notification(
    case: BugCase,
    event_type: str,
    store,
) -> str:
    """Route and send notification based on BugCase severity and event type.

    Returns:
        "sent" | "suppressed" | "skipped" | "failed"
    """
    settings = get_bugops_settings()
    now = datetime.utcnow()

    # Severity-based routing
    if case.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH):
        pass  # Proceed to deduplication/throttle checks
    elif case.severity == AlertSeverity.WARNING:  # Medium
        logger.info(
            f"[DIGEST-PENDING] BugCase {case.case_id} queued for digest "
            f"(severity=medium, event_type={event_type})"
        )
        await store.update_notification_state(case.case_id, now)
        return "skipped"
    elif case.severity == AlertSeverity.INFO:  # Low
        logger.debug(f"BugCase {case.case_id} not notified (severity=low)")
        return "skipped"

    # Deduplication check (bugcase_created only)
    if event_type == "bugcase_created" and case.notification_count > 0:
        logger.debug(
            f"BugCase {case.case_id} already notified (notification_count={case.notification_count})"
        )
        return "skipped"

    # Throttle check (skip for bugcase_reopened and severity_escalated)
    if event_type not in ("bugcase_reopened", "severity_escalated"):
        if case.last_notified_at is not None:
            elapsed = now - case.last_notified_at
            throttle_window = timedelta(minutes=settings.BUGOPS_NOTIFICATION_THROTTLE_MINUTES)
            if elapsed < throttle_window:
                logger.debug(
                    f"BugCase {case.case_id} throttled (last_notified={elapsed.total_seconds():.0f}s ago)"
                )
                return "skipped"

    # Mute/snooze check
    if case.muted_until and case.muted_until > now:
        logger.info(f"BugCase {case.case_id} notification suppressed (muted)")
        await store.update_notification_state(case.case_id, now)
        return "suppressed"

    if case.snoozed_until and case.snoozed_until > now:
        logger.info(f"BugCase {case.case_id} notification suppressed (snoozed)")
        await store.update_notification_state(case.case_id, now)
        return "suppressed"

    # Send notification
    if not settings.BUGOPS_SLACK_ENABLED:
        logger.debug(f"Slack notifications disabled, skipping case {case.case_id}")
        return "skipped"

    success = await send_case_notification(case, event_type)
    if success:
        await store.update_notification_state(case.case_id, now)
        return "sent"
    else:
        return "failed"


async def send_case_notification(case: BugCase, event_type: str = "bugcase_created") -> bool:
    """Send a Slack notification for a case.

    Args:
        case: The BugCase to notify about
        event_type: The event type triggering the notification

    Returns:
        True if sent successfully, False otherwise
    """
    settings = get_bugops_settings()

    if not settings.BUGOPS_SLACK_ENABLED:
        logger.debug(f"Slack notifications disabled, skipping case {case.case_id}")
        return False

    if not settings.BUGOPS_SLACK_WEBHOOK_URL:
        logger.warning("BUGOPS_SLACK_WEBHOOK_URL not configured, cannot send Slack notification")
        return False

    message = _build_slack_message(case, event_type)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.BUGOPS_SLACK_WEBHOOK_URL,
                json=message,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Slack notification sent for case {case.case_id} (event={event_type})")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Slack notification for case {case.case_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Slack notification: {e}", exc_info=True)
        return False


def _build_slack_message(case: BugCase, event_type: str = "bugcase_created") -> dict:
    """Build a Slack message payload for a case.

    Args:
        case: The BugCase to format
        event_type: The event type (bugcase_created, bugcase_reopened, severity_escalated)

    Returns:
        A Slack message payload dict
    """
    severity_colors = {
        "info": "#36a64f",
        "warning": "#ffa500",
        "high": "#ff6600",
        "critical": "#ff0000",
    }

    color = severity_colors.get(case.severity.value, "#808080")

    # Message format varies by event type
    if event_type == "bugcase_reopened":
        title = "🔄 CASE REOPENED"
        text = (
            f"Case: {case.case_id}\n"
            f"Severity: {case.severity.value.capitalize()}\n"
            f"Root: {case.root_subsystem}\n"
            f"Summary: {case.summary}\n"
            f"Reopen count: {case.reopen_count}"
        )
    else:
        # bugcase_created or severity_escalated
        severity_emoji = "🚨" if case.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) else "⚠️"
        title = f"{severity_emoji} {case.severity.value.upper()} — {case.title}"
        affected = ", ".join(case.affected_subsystems) if case.affected_subsystems else "none"
        text = (
            f"Case: {case.case_id}\n"
            f"Detection: {case.detection_type}\n"
            f"Root subsystem: {case.root_subsystem}\n"
            f"Affected: {affected}\n"
            f"Summary: {case.summary}\n"
            f"First seen: {case.first_seen_at.strftime('%Y-%m-%d %H:%M') if case.first_seen_at else 'N/A'} UTC\n"
            f"Last seen: {case.last_seen_at.strftime('%Y-%m-%d %H:%M') if case.last_seen_at else 'N/A'} UTC\n"
            f"Observations: {case.observation_count}\n"
            f"Suggested check: {case.suggested_manual_check if case.suggested_manual_check else 'N/A'}"
        )

    fields = [
        {"title": "Case ID", "value": case.case_id, "short": True},
        {"title": "Bugcase ID", "value": case.case_id, "short": True},
        {"title": "Severity", "value": case.severity.value.upper(), "short": True},
        {"title": "Status", "value": case.status.value.upper(), "short": True},
        {"title": "Root Subsystem", "value": case.root_subsystem or "unknown", "short": True},
        {"title": "Dedupe Key", "value": case.dedupe_key, "short": True},
        {"title": "Detection Type", "value": case.detection_type or "unknown", "short": True},
    ]

    if case.affected_subsystems:
        fields.append({
            "title": "Affected Subsystems",
            "value": ", ".join(case.affected_subsystems),
            "short": True
        })

    suppression_status = "not_applicable"  # Default; TASK-112A will set this
    fields.append({
        "title": "Suppression Status",
        "value": suppression_status,
        "short": True
    })

    return {
        "attachments": [
            {
                "color": color,
                "title": title,
                "text": text,
                "fields": fields,
                "footer": "BugOps Alert",
                "ts": int(case.created_at.timestamp())
            }
        ]
    }
