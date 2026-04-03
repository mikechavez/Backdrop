---
id: TASK-035
type: feature
status: backlog
priority: medium
complexity: medium
created: 2026-04-02
updated: 2026-04-02
---

# Daily Pipeline Digest via Slack Webhook

## Problem/Opportunity
TASK-033 (Sentry) catches errors. TASK-034 (heartbeat) catches pipeline stalls. But neither gives a daily "at a glance" view of system health. During BUG-054/055, even basic stats -- articles ingested today: 0, briefings generated today: 0, MongoDB storage: 516 MB -- would have made the problem obvious without digging into logs.

A daily Slack message provides passive, low-effort monitoring. Glance at it during coffee -- if the numbers look normal, move on. If articles ingested is 0 or MongoDB is climbing toward 512 MB, investigate.

Note: Sentry (TASK-033) is already connected to Slack and handles real-time error alerts. This digest covers throughput and health metrics that aren't errors -- things Sentry can't see.

## Proposed Solution
Add a Celery Beat scheduled task that runs once daily, queries MongoDB for pipeline stats, and sends a formatted summary to a Slack channel via incoming webhook. No Slack app or bot required -- just a webhook URL.

## User Story
As a solo operator, I want a daily Slack summary of pipeline health so that I can spot drift and degradation without actively checking dashboards or logs.

## Acceptance Criteria
- [ ] Slack incoming webhook created and `SLACK_WEBHOOK_URL` added to Railway env vars
- [ ] New Celery Beat task `send_daily_digest` scheduled at 9:00 AM EST (after morning briefing)
- [ ] Digest includes: articles ingested (24h), briefings generated (24h), MongoDB storage %, last heartbeat ages
- [ ] Message formatted with Slack Block Kit for readability
- [ ] Task fails gracefully if webhook URL is not set (logs warning, does not crash)
- [ ] Digest appears in Slack channel within 5 minutes of scheduled time

## Dependencies
- TASK-034 (heartbeat) should be deployed first so the digest can report heartbeat ages
- Slack incoming webhook created (see Manual Steps)

## Manual Steps (before code deploy)

### Create Slack Incoming Webhook
1. Go to https://api.slack.com/apps -- click "Create New App" > "From scratch"
2. Name it "Backdrop Alerts" -- select your workspace
3. In the left sidebar, click "Incoming Webhooks" > toggle ON
4. Click "Add New Webhook to Workspace" > select the channel (e.g., #backdrop-alerts)
5. Copy the webhook URL (looks like `https://hooks.slack.com/services/T.../B.../xxx`)
6. Add to Railway: `SLACK_WEBHOOK_URL=<your-webhook-url>` on celery-worker and celery-beat services

This is a one-way webhook -- it can only post messages to the channel you selected. No bot permissions, no reading messages, no other access.

## Implementation Notes

### File Changes

**1. Add dependency**

File: `requirements.txt`
```
# No new dependency needed -- uses stdlib urllib.request or the requests library
# if requests is already in requirements.txt (likely), use that
```

Check if `requests` or `httpx` is already a dependency. If so, use it. If not, use `urllib.request` from stdlib to avoid adding a dependency just for one HTTP POST.

**2. Add config setting**

File: `src/crypto_news_aggregator/core/config.py`

Add to the `Settings` class:
```python
# Slack notifications
SLACK_WEBHOOK_URL: str | None = Field(default=None, env="SLACK_WEBHOOK_URL")
```

**3. Create digest service module**

File: `src/crypto_news_aggregator/services/daily_digest.py` (NEW FILE)

```python
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

    Uses urllib to avoid adding a dependency. If requests/httpx
    is already available, CC can swap this to use that instead.
    """
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
```

CC note on `send_to_slack`: Slack webhook URLs go to `hooks.slack.com` which may not be in the Railway egress allowlist. If the POST fails with a network error, the user will need to add `hooks.slack.com` to their Railway network configuration. Flag this in the PR description.

**4. Create Celery task**

File: `src/crypto_news_aggregator/tasks/digest_tasks.py` (NEW FILE)

```python
"""Daily digest Celery task."""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="send_daily_digest", ignore_result=True)
def send_daily_digest_task():
    """Build and send daily pipeline health digest to Slack."""

    async def _run():
        from crypto_news_aggregator.core.config import get_settings
        from crypto_news_aggregator.db.mongodb import get_database
        from crypto_news_aggregator.services.daily_digest import (
            build_digest,
            format_slack_message,
            send_to_slack,
        )

        settings = get_settings()

        if not settings.SLACK_WEBHOOK_URL:
            logger.warning("SLACK_WEBHOOK_URL not set, skipping daily digest")
            return

        db = await get_database()
        digest = await build_digest(db)
        message = format_slack_message(digest)
        success = await send_to_slack(settings.SLACK_WEBHOOK_URL, message)

        if success:
            logger.info(
                f"Daily digest sent: {digest['article_count_24h']} articles, "
                f"{digest['briefing_count_24h']} briefings"
            )
        else:
            logger.error("Failed to send daily digest to Slack")

    # Follow the same async-in-Celery pattern used by briefing tasks
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
```

CC note: Follow the exact same async execution pattern used in `tasks/briefing_tasks.py` for the event loop handling. If that file uses a helper function like `run_async()`, use the same one.

**5. Add to beat schedule**

File: `src/crypto_news_aggregator/tasks/beat_schedule.py`

Add a new entry to the `beat_schedule` dict:
```python
"send-daily-digest": {
    "task": "send_daily_digest",
    "schedule": crontab(hour=9, minute=0),  # 9:00 AM Eastern (Celery timezone = America/New_York)
    "options": {
        "expires": 3600,
        "queue": "default",
    },
},
```

**6. Register the new task module**

File: `src/crypto_news_aggregator/tasks/__init__.py`

CC: Ensure `digest_tasks` is imported so the `@shared_task` decorator registers. Look at how `briefing_tasks` and `news` are imported and follow the same pattern. Typically this means adding:
```python
from crypto_news_aggregator.tasks import digest_tasks  # noqa: F401
```

### Example Slack Output

```
:large_green_circle: Backdrop Daily Digest

Status: All systems nominal
Articles (24h): 347
Briefings (24h): 3
Storage: 253 MB / 512 MB (49.4%)

---

Pipeline Heartbeats
:white_check_mark: Fetch News: 1.2h ago -- Fetched 127 articles
:white_check_mark: Generate Briefing: 2.1h ago -- Morning briefing generated, 20 signals, 15 narratives

Generated 2026-04-03T09:00:12 UTC
```

### Estimated Effort
- Slack webhook setup: 5 min (manual)
- Config addition: 2 min
- Digest service module: 20 min
- Celery task: 10 min
- Beat schedule entry: 5 min
- Task registration: 2 min
- Test end-to-end: 15 min
- **Total: ~1 hour**

## Open Questions
- [ ] Should the digest also include Anthropic API spend from `api_costs` collection? (Nice-to-have, can add in v2)
- [ ] Network: `hooks.slack.com` may need to be added to Railway egress allowlist. Verify during deployment.

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: