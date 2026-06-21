"""BugOps Slack notification helper."""

import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
from .models import BugCase, AlertSeverity, NotificationAttemptCreate, EvidencePack
from .config import get_bugops_settings

logger = logging.getLogger(__name__)


def is_suppression_active(settings) -> bool:
    """Return True if global deploy suppression is currently active."""
    raw = settings.BUGOPS_SUPPRESSED_UNTIL
    if not raw:
        return False
    try:
        suppressed_until = datetime.fromisoformat(raw)
        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if suppressed_until.tzinfo is None:
            suppressed_until = suppressed_until.replace(tzinfo=timezone.utc)
        return now < suppressed_until
    except (ValueError, TypeError):
        return False


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
    notification_id = f"notif_{case.case_id}_{uuid4().hex}"

    # Global suppression check (FIRST check, before mute/snooze)
    if is_suppression_active(settings):
        logger.info(
            f"[SUPPRESSED] Notification suppressed during maintenance window: "
            f"case_id={case.case_id}"
        )
        # Still update last_notified_at so throttle resets correctly
        await store.update_last_notified_at_only(case.case_id, now)
        # Persist attempt record (TASK-111A)
        attempt = NotificationAttemptCreate(
            notification_id=notification_id,
            bugcase_id=case.case_id,
            event_type=event_type,
            status="suppressed",
            attempted_at=now,
            suppressed_reason="deploy_suppression",
        )
        try:
            await store.create_notification_attempt(attempt)
        except Exception as e:
            logger.error(f"Failed to persist notification attempt: {e}", exc_info=True)
        return "suppressed"

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
        await store.update_last_notified_at_only(case.case_id, now)
        # Persist suppressed attempt record
        attempt = NotificationAttemptCreate(
            notification_id=notification_id,
            bugcase_id=case.case_id,
            event_type=event_type,
            status="suppressed",
            attempted_at=now,
            suppressed_reason="muted",
        )
        try:
            await store.create_notification_attempt(attempt)
        except Exception as e:
            logger.error(f"Failed to persist notification attempt: {e}", exc_info=True)
        return "suppressed"

    if case.snoozed_until and case.snoozed_until > now:
        logger.info(f"BugCase {case.case_id} notification suppressed (snoozed)")
        await store.update_last_notified_at_only(case.case_id, now)
        # Persist suppressed attempt record
        attempt = NotificationAttemptCreate(
            notification_id=notification_id,
            bugcase_id=case.case_id,
            event_type=event_type,
            status="suppressed",
            attempted_at=now,
            suppressed_reason="snoozed",
        )
        try:
            await store.create_notification_attempt(attempt)
        except Exception as e:
            logger.error(f"Failed to persist notification attempt: {e}", exc_info=True)
        return "suppressed"

    # Send notification
    if not settings.BUGOPS_SLACK_ENABLED:
        logger.debug(f"Slack notifications disabled, skipping case {case.case_id}")
        return "skipped"

    success, error_type, error_msg = await _send_notification_and_persist(
        case, event_type, store, notification_id, now
    )
    if success:
        await store.update_notification_state(case.case_id, now)
        return "sent"
    else:
        return "failed"


async def _send_notification_and_persist(
    case: BugCase,
    event_type: str,
    store,
    notification_id: str,
    now: datetime,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Send notification via send_case_notification and persist attempt record.

    Returns: (success: bool, error_type: str | None, error_msg: str | None)
    """
    try:
        success = await send_case_notification(case, event_type)
        if success:
            # Persist sent attempt record
            attempt = NotificationAttemptCreate(
                notification_id=notification_id,
                bugcase_id=case.case_id,
                event_type=event_type,
                status="sent",
                attempted_at=now,
            )
            try:
                await store.create_notification_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to persist notification attempt: {e}", exc_info=True)
            return True, None, None
        else:
            # Persist failed attempt record (reason unknown from send_case_notification)
            attempt = NotificationAttemptCreate(
                notification_id=notification_id,
                bugcase_id=case.case_id,
                event_type=event_type,
                status="failed",
                attempted_at=now,
                error_type="UnknownError",
                error_message="Slack send returned False",
            )
            try:
                await store.create_notification_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to persist notification attempt: {e}", exc_info=True)
            return False, "UnknownError", "Slack send returned False"
    except Exception as e:
        # Persist failed attempt record
        attempt = NotificationAttemptCreate(
            notification_id=notification_id,
            bugcase_id=case.case_id,
            event_type=event_type,
            status="failed",
            attempted_at=now,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        try:
            await store.create_notification_attempt(attempt)
        except Exception as store_error:
            logger.error(f"Failed to persist notification attempt: {store_error}", exc_info=True)
        logger.error(f"Error in _send_notification_and_persist: {e}", exc_info=True)
        return False, type(e).__name__, str(e)


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


async def send_suppression_summary(cases: list[BugCase]) -> bool:
    """Send a single Slack summary of cases active during suppression window.

    Args:
        cases: List of unresolved BugCases to include in summary

    Returns:
        True if sent successfully, False otherwise
    """
    settings = get_bugops_settings()

    if not settings.BUGOPS_SLACK_ENABLED:
        logger.debug("Slack notifications disabled, skipping suppression summary")
        return False

    if not settings.BUGOPS_SLACK_WEBHOOK_URL:
        logger.warning("BUGOPS_SLACK_WEBHOOK_URL not configured, cannot send suppression summary")
        return False

    if not cases:
        logger.debug("No unresolved cases for suppression summary")
        return False

    message = _build_suppression_summary_message(cases)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.BUGOPS_SLACK_WEBHOOK_URL,
                json=message,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Suppression expiry summary sent ({len(cases)} unresolved cases)")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send suppression summary: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending suppression summary: {e}", exc_info=True)
        return False


def _build_suppression_summary_message(cases: list[BugCase]) -> dict:
    """Build a Slack message payload for suppression expiry summary.

    Args:
        cases: List of unresolved BugCases

    Returns:
        A Slack message payload dict
    """
    # Build case list lines (sorted by severity then case_id for consistency)
    severity_order = {"critical": 0, "high": 1}
    sorted_cases = sorted(
        cases,
        key=lambda c: (severity_order.get(c.severity.value, 999), c.case_id)
    )

    case_lines = [
        f"- {c.severity.value.upper()} {c.title} — {c.case_id}"
        for c in sorted_cases
    ]

    text = (
        f"Deploy suppression ended\n\n"
        f"{len(sorted_cases)} unresolved BugCase{'s' if len(sorted_cases) != 1 else ''} "
        f"{'were' if len(sorted_cases) != 1 else 'was'} active during suppression:\n\n"
        + "\n".join(case_lines)
    )

    return {
        "attachments": [
            {
                "color": "#ff6600",
                "title": "🔔 Deploy Suppression Ended",
                "text": text,
                "footer": "BugOps Suppression Summary",
                "ts": int(datetime.utcnow().timestamp())
            }
        ]
    }


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


async def send_evidence_collected_notification(
    bugcase: BugCase,
    pack: EvidencePack,
    settings,
) -> bool:
    """
    Notify operator that evidence has been collected and investigation is pending.

    Message includes:
    - Case ID and severity
    - Sections collected (comma-separated list)
    - Count of collection errors if any
    - First sentence: "Evidence collected for [case_id] — investigation pending"

    Uses same Slack webhook and enabled check as existing notifications.
    Failures are logged but do not raise.

    Returns:
        True if sent successfully, False otherwise
    """
    if not settings.BUGOPS_SLACK_ENABLED:
        logger.debug(f"Slack notifications disabled, skipping evidence notification for {bugcase.case_id}")
        return False

    if not settings.BUGOPS_SLACK_WEBHOOK_URL:
        logger.warning("BUGOPS_SLACK_WEBHOOK_URL not configured, cannot send evidence notification")
        return False

    message = _build_evidence_collected_message(bugcase, pack)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.BUGOPS_SLACK_WEBHOOK_URL,
                json=message,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Evidence collected notification sent for case {bugcase.case_id}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send evidence notification for case {bugcase.case_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending evidence notification: {e}", exc_info=True)
        return False


def _build_evidence_collected_message(bugcase: BugCase, pack: EvidencePack) -> dict:
    """Build a Slack message payload for evidence collection completion.

    Args:
        bugcase: The BugCase the evidence was collected for
        pack: The completed EvidencePack

    Returns:
        A Slack message payload dict
    """
    severity_colors = {
        "info": "#36a64f",
        "warning": "#ffa500",
        "high": "#ff6600",
        "critical": "#ff0000",
    }

    color = severity_colors.get(bugcase.severity.value, "#808080")

    # Build sections collected line
    sections_list = ", ".join(pack.sections_collected) if pack.sections_collected else "none"

    # Build error count line if present
    error_count = len(pack.collection_errors) if pack.collection_errors else 0
    error_line = f"Collection errors: {error_count}\n" if error_count > 0 else ""

    text = (
        f"Evidence collected for {bugcase.case_id} — investigation pending\n\n"
        f"Case: {bugcase.case_id}\n"
        f"Severity: {bugcase.severity.value.capitalize()}\n"
        f"Root subsystem: {bugcase.root_subsystem}\n"
        f"Sections collected: {sections_list}\n"
        f"{error_line}"
        f"Status: {pack.collection_status.value.capitalize()}"
    )

    return {
        "attachments": [
            {
                "color": color,
                "title": "📦 Evidence Pack Complete",
                "text": text,
                "footer": "BugOps Evidence Collection",
                "ts": int(pack.created_at.timestamp()) if pack.created_at else int(datetime.utcnow().timestamp())
            }
        ]
    }
