"""BugOps Slack notification helper."""

import logging
import httpx
from typing import Optional
from .models import BugCase
from .config import get_bugops_settings

logger = logging.getLogger(__name__)


async def send_case_notification(case: BugCase) -> bool:
    """Send a Slack notification for a new case.

    Args:
        case: The BugCase to notify about

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

    message = _build_slack_message(case)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.BUGOPS_SLACK_WEBHOOK_URL,
                json=message,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Slack notification sent for case {case.case_id}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to send Slack notification for case {case.case_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Slack notification: {e}", exc_info=True)
        return False


def _build_slack_message(case: BugCase) -> dict:
    """Build a Slack message payload for a case.

    Args:
        case: The BugCase to format

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

    fields = [
        {
            "title": "Case ID",
            "value": case.case_id,
            "short": True
        },
        {
            "title": "Severity",
            "value": case.severity.value.upper(),
            "short": True
        },
        {
            "title": "Alert Type",
            "value": case.alert_type,
            "short": True
        },
        {
            "title": "Source Type",
            "value": ", ".join(case.source_types),
            "short": True
        },
        {
            "title": "Status",
            "value": case.status.value.upper(),
            "short": True
        }
    ]

    if case.metric:
        metric_str = "\n".join(f"{k}: {v}" for k, v in case.metric.items())
        fields.append({
            "title": "Metrics",
            "value": metric_str,
            "short": False
        })

    if case.suggested_manual_check:
        fields.append({
            "title": "Suggested Manual Check",
            "value": case.suggested_manual_check,
            "short": False
        })

    return {
        "attachments": [
            {
                "color": color,
                "title": case.title,
                "text": case.summary,
                "fields": fields,
                "footer": "BugOps Alert",
                "ts": int(case.created_at.timestamp())
            }
        ]
    }
