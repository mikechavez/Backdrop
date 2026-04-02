---
id: TASK-034
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-04-02
updated: 2026-04-02
---

# Pipeline Heartbeat Health Check (Catch Silent Failures)

## Problem/Opportunity
BUG-054 (fetch_news disabled) went undetected for 11+ days because the health endpoint only checks connectivity -- MongoDB reachable, Redis reachable, LLM key valid. It returned 200 OK the entire time the data pipeline was dead. UptimeRobot was monitoring this endpoint and saw green while every frontend page showed stale data.

Sentry (TASK-033) catches errors that happen. This ticket catches things that DON'T happen -- the silent absence of expected pipeline activity. The fix: write heartbeat timestamps after each pipeline stage completes, then make the health endpoint return HTTP 500 when any stage is stale beyond its threshold. UptimeRobot (already running) then alerts automatically.

## Proposed Solution
1. Write a `last_success` timestamp to a `pipeline_heartbeats` MongoDB collection after each critical pipeline stage completes successfully (article fetch, briefing generation)
2. Enhance the existing `/api/v1/health` endpoint to query these timestamps and return HTTP 500 (not 200-with-warning) when any stage exceeds its staleness threshold
3. UptimeRobot (already configured) picks up the 500 and sends an alert with zero additional setup

## User Story
As a solo operator, I want the health endpoint to fail loudly when the data pipeline stalls so that UptimeRobot alerts me automatically, without me having to check logs or the frontend manually.

## Acceptance Criteria
- [ ] `pipeline_heartbeats` collection created with documents for each pipeline stage
- [ ] `fetch_news` task writes heartbeat timestamp on successful completion
- [ ] `generate_morning_briefing` (and afternoon/evening) tasks write heartbeat timestamp on successful completion
- [ ] Health endpoint returns HTTP 500 with details when article heartbeat is older than 6 hours
- [ ] Health endpoint returns HTTP 500 with details when briefing heartbeat is older than 18 hours
- [ ] Health endpoint continues to return HTTP 200 when all heartbeats are fresh
- [ ] Existing connectivity checks (MongoDB, Redis, LLM) still run and still fail on connection errors
- [ ] UptimeRobot detects the 500 and sends alert (verify with manual test)

## Dependencies
- BUG-054 must be verified working (fetch_news running) so heartbeats start populating
- Independent of TASK-033 (Sentry) and TASK-035 (daily digest)

## Implementation Notes

### Data Model

**Collection:** `pipeline_heartbeats`

```javascript
// One document per pipeline stage, upserted on each successful run
{
  "_id": "fetch_news",              // stage identifier (string, not ObjectId)
  "last_success": ISODate("..."),   // when the stage last completed successfully
  "last_duration_seconds": 45.2,    // how long the last run took
  "last_result_summary": "Fetched 127 articles from 8 feeds"  // human-readable
}

{
  "_id": "generate_briefing",
  "last_success": ISODate("..."),
  "last_duration_seconds": 38.7,
  "last_result_summary": "Morning briefing generated, 20 signals, 15 narratives"
}
```

Using `_id` as the stage name means upserts are simple and no extra index needed.

### Staleness Thresholds

| Stage | Schedule | Threshold | Rationale |
|---|---|---|---|
| `fetch_news` | Every 3 hours | 6 hours | Two missed cycles means something is wrong |
| `generate_briefing` | 2x daily (morning + evening) | 18 hours | ~6 hours past expected gap, allows one missed cycle before alerting |

### File Changes

**1. Add config settings**

File: `src/crypto_news_aggregator/core/config.py`

Add to the `Settings` class:
```python
# Pipeline heartbeat staleness thresholds (seconds)
HEARTBEAT_FETCH_NEWS_MAX_AGE: int = Field(default=21600, env="HEARTBEAT_FETCH_NEWS_MAX_AGE")  # 6 hours
HEARTBEAT_BRIEFING_MAX_AGE: int = Field(default=64800, env="HEARTBEAT_BRIEFING_MAX_AGE")  # 18 hours
```

**2. Create heartbeat helper module**

File: `src/crypto_news_aggregator/services/heartbeat.py` (NEW FILE)

```python
"""Pipeline heartbeat tracking.

Writes timestamps after successful pipeline stages.
Read by health endpoint to detect silent failures.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def record_heartbeat(
    db,
    stage: str,
    duration_seconds: float = 0.0,
    summary: str = "",
) -> None:
    """Record a successful pipeline stage completion.

    Uses upsert on _id=stage so there is exactly one document per stage.
    """
    try:
        await db.pipeline_heartbeats.update_one(
            {"_id": stage},
            {
                "$set": {
                    "last_success": datetime.now(timezone.utc),
                    "last_duration_seconds": round(duration_seconds, 1),
                    "last_result_summary": summary[:500],
                }
            },
            upsert=True,
        )
    except Exception as e:
        # Heartbeat write should never break the pipeline itself
        logger.error(f"Failed to record heartbeat for {stage}: {e}")


async def get_heartbeat(db, stage: str) -> dict | None:
    """Get the latest heartbeat for a pipeline stage."""
    return await db.pipeline_heartbeats.find_one({"_id": stage})
```

**3. Write heartbeat after successful article fetch**

File: `src/crypto_news_aggregator/tasks/news.py`

CC: Find the point in `fetch_news` where the task completes successfully (after articles are saved to MongoDB). Add AFTER the success path, BEFORE the return.

```python
# --- Add these imports at top of file ---
import time
from crypto_news_aggregator.services.heartbeat import record_heartbeat

# --- At the start of the fetch_news function body, add ---
_hb_start = time.time()

# --- After successful article processing, before return ---
await record_heartbeat(
    db,
    stage="fetch_news",
    duration_seconds=time.time() - _hb_start,
    summary=f"Fetched {article_count} articles",  # CC: use whatever count var exists
)
```

CC note: This task uses `asyncio.run()` or `asyncio.new_event_loop()` to run async code. The `record_heartbeat` call must be inside the async function that has access to the db connection. Follow the same pattern as other async MongoDB operations in this task.

**4. Write heartbeat after successful briefing generation**

File: `src/crypto_news_aggregator/services/briefing_agent.py`

CC: Find the point after `insert_briefing` succeeds (around line 890 based on docs). Add AFTER the successful save.

```python
# --- Add import at top of file ---
from crypto_news_aggregator.services.heartbeat import record_heartbeat

# --- After successful insert_briefing call ---
await record_heartbeat(
    db,
    stage="generate_briefing",
    duration_seconds=generation_duration,  # CC: use whatever timing var exists
    summary=f"{briefing_type} briefing generated, {metadata.get('signal_count', 0)} signals, {metadata.get('narrative_count', 0)} narratives",
)
```

CC note: The briefing agent already has db access and runs in async context. The metadata dict (signal_count, narrative_count) is constructed earlier in the function -- reference those same variables.

**5. Enhance health endpoint**

File: `src/crypto_news_aggregator/api/v1/endpoints/health.py`

CC: Find the existing health check function. Add pipeline freshness checks AFTER the existing connectivity checks (MongoDB, Redis, LLM).

```python
# --- Add imports at top ---
from datetime import datetime, timezone
from crypto_news_aggregator.services.heartbeat import get_heartbeat
from crypto_news_aggregator.core.config import get_settings

# --- Add inside the health check function, after existing checks ---

settings = get_settings()
pipeline_ok = True
pipeline_checks = {}

# Check article fetch heartbeat
fetch_hb = await get_heartbeat(db, "fetch_news")
if fetch_hb is None:
    pipeline_checks["fetch_news"] = {
        "status": "warning",
        "message": "No heartbeat recorded yet (pipeline may not have run since deploy)",
    }
    # Don't fail on missing heartbeat -- newly deployed
else:
    age_seconds = (datetime.now(timezone.utc) - fetch_hb["last_success"]).total_seconds()
    if age_seconds > settings.HEARTBEAT_FETCH_NEWS_MAX_AGE:
        pipeline_ok = False
        pipeline_checks["fetch_news"] = {
            "status": "critical",
            "message": f"Last successful fetch was {age_seconds / 3600:.1f} hours ago",
            "last_success": fetch_hb["last_success"].isoformat(),
            "threshold_hours": settings.HEARTBEAT_FETCH_NEWS_MAX_AGE / 3600,
        }
    else:
        pipeline_checks["fetch_news"] = {
            "status": "ok",
            "last_success": fetch_hb["last_success"].isoformat(),
            "last_summary": fetch_hb.get("last_result_summary", ""),
        }

# Check briefing heartbeat (same pattern)
briefing_hb = await get_heartbeat(db, "generate_briefing")
if briefing_hb is None:
    pipeline_checks["generate_briefing"] = {
        "status": "warning",
        "message": "No heartbeat recorded yet",
    }
else:
    age_seconds = (datetime.now(timezone.utc) - briefing_hb["last_success"]).total_seconds()
    if age_seconds > settings.HEARTBEAT_BRIEFING_MAX_AGE:
        pipeline_ok = False
        pipeline_checks["generate_briefing"] = {
            "status": "critical",
            "message": f"Last briefing was {age_seconds / 3600:.1f} hours ago",
            "last_success": briefing_hb["last_success"].isoformat(),
            "threshold_hours": settings.HEARTBEAT_BRIEFING_MAX_AGE / 3600,
        }
    else:
        pipeline_checks["generate_briefing"] = {
            "status": "ok",
            "last_success": briefing_hb["last_success"].isoformat(),
            "last_summary": briefing_hb.get("last_result_summary", ""),
        }

# CRITICAL CHANGE: Return HTTP 500 when pipeline is stale
# CC: Add "pipeline": pipeline_checks to the existing response dict
# CC: When pipeline_ok is False, return JSONResponse(content=response_body, status_code=500)
# This is what triggers UptimeRobot alerts
```

CC note: The existing health endpoint likely returns a dict via `JSONResponse` or a FastAPI return. The key change is returning `status_code=500` when `pipeline_ok is False`. Keep all existing connectivity checks intact -- they should continue to fail the endpoint on connection errors.

### UptimeRobot (no changes needed)
UptimeRobot is already monitoring the health endpoint URL. When the endpoint returns 500, UptimeRobot detects it and alerts. No configuration changes required.

### Estimated Effort
- New heartbeat module: 10 min
- Wire into fetch_news: 10 min
- Wire into briefing_agent: 10 min
- Enhance health endpoint: 20 min
- Config additions: 5 min
- Test end-to-end: 15 min
- **Total: ~1 hour**

## Open Questions
- [ ] Should we also track entity extraction and narrative detection heartbeats? (Recommend: skip for v1, add later if needed)

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: