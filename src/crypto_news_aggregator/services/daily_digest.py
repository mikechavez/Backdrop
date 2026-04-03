"""Daily pipeline health digest sent via Slack webhook."""

import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def build_digest(db) -> dict:
    """Query MongoDB for pipeline health stats. Returns a dict of metrics."""

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    # Articles ingested in last 24h
    article_count = await db.articles.count_documents(
        {"fetched_at": {"$gte": yesterday}}
    )

    # Briefings generated in last 24h
    briefing_count = await db.daily_briefings.count_documents(
        {"generated_at": {"$gte": yesterday}, "is_smoke": {"$ne": True}}
    )

    # MongoDB storage (approximate from collection stats)
    # Note: dbStats requires admin-level access on Atlas free tier.
    # If this fails, fall back gracefully.
    try:
        db_stats = await db.command("dbStats")
        storage_mb = round(db_stats.get("storageSize", 0) / (1024 * 1024), 1)
        storage_pct = round((storage_mb / 512) * 100, 1)  # 512 MB Atlas free tier
    except Exception:
        storage_mb = None
        storage_pct = None

    # Pipeline heartbeats (from TASK-034)
    heartbeats = {}
    for stage in ["fetch_news", "generate_briefing"]:
        hb = await db.pipeline_heartbeats.find_one({"_id": stage})
        if hb and "last_success" in hb:
            age_hours = (now - hb["last_success"]).total_seconds() / 3600
            heartbeats[stage] = {
                "last_success": hb["last_success"].isoformat(),
                "age_hours": round(age_hours, 1),
                "summary": hb.get("last_result_summary", ""),
            }
        else:
            heartbeats[stage] = {"last_success": None, "age_hours": None}

    return {
        "article_count_24h": article_count,
        "briefing_count_24h": briefing_count,
        "storage_mb": storage_mb,
        "storage_pct": storage_pct,
        "heartbeats": heartbeats,
        "generated_at": now.isoformat(),
    }


def format_slack_message(digest: dict) -> dict:
    """Format digest as Slack Block Kit message."""

    # Status emoji logic
    articles = digest["article_count_24h"]
    briefings = digest["briefing_count_24h"]
    storage_pct = digest.get("storage_pct")

    if articles == 0 or briefings == 0:
        status_emoji = ":red_circle:"
        status_text = "Issues detected"
    elif storage_pct and storage_pct > 90:
        status_emoji = ":large_orange_circle:"
        status_text = "Storage warning"
    else:
        status_emoji = ":large_green_circle:"
        status_text = "All systems nominal"

    # Storage line
    if storage_pct is not None:
        storage_line = f"*Storage:* {digest['storage_mb']} MB / 512 MB ({storage_pct}%)"
    else:
        storage_line = "*Storage:* Unable to query"

    # Heartbeat lines
    hb_lines = []
    for stage, data in digest.get("heartbeats", {}).items():
        label = stage.replace("_", " ").title()
        if data["age_hours"] is not None:
            age = data["age_hours"]
            emoji = ":white_check_mark:" if age < 12 else ":warning:"
            hb_lines.append(f"{emoji} *{label}:* {age}h ago -- {data.get('summary', '')}")
        else:
            hb_lines.append(f":question: *{label}:* No heartbeat recorded")

    hb_text = "\n".join(hb_lines) if hb_lines else "No heartbeats configured"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Backdrop Daily Digest",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Status:* {status_text}\n"
                        f"*Articles (24h):* {articles}\n"
                        f"*Briefings (24h):* {briefings}\n"
                        f"{storage_line}"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Pipeline Heartbeats*\n{hb_text}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Generated {digest['generated_at'][:19]} UTC",
                    }
                ],
            },
        ]
    }


async def send_to_slack(webhook_url: str, message: dict) -> bool:
    """POST message payload to Slack incoming webhook.

    Uses httpx if available (it's already a dependency for briefing agent),
    otherwise falls back to urllib.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=message)
            return response.status_code == 200
    except ImportError:
        # Fallback to urllib if httpx is not available
        import urllib.request
        try:
            data = json.dumps(message).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send Slack digest: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Slack digest: {e}")
        return False
