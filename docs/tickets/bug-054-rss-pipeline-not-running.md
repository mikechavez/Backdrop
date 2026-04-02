---
id: BUG-054
type: bug
status: open
priority: critical
severity: critical
created: 2026-04-02
updated: 2026-04-02
---

# RSS Ingestion Pipeline Not Running (fetch_news Disabled in Beat Schedule)

## Problem

The entire data pipeline is dead. No new articles have been ingested since March 22. Signals page shows no signals, briefings are stale (last: March 11), and cost monitor shows no data. The root cause is that `fetch_news` was commented out of `beat_schedule.py` during BUG-019 and never replaced with an RSS-based schedule entry.

## Expected Behavior

Celery Beat dispatches `fetch_news` every 3 hours. The worker pulls RSS feeds, ingests articles, runs entity extraction and sentiment analysis, generates signals, and feeds briefing generation downstream.

## Actual Behavior

Celery Beat only dispatches `check_price_alerts` (every 5 min), `warm_cache` (every 10 min), and `consolidate_narratives` (hourly). No `fetch_news` task is ever dispatched. The entire downstream pipeline (articles, entities, signals, briefings, cost tracking) is starved.

## Steps to Reproduce
1. Check Celery Beat logs: no `fetch_news` dispatch appears
2. Check `beat_schedule.py`: the `fetch_news` entry is commented out (lines 24-33)
3. Check articles page: latest article is March 22
4. Check signals page: "no signals"
5. Check briefings: last briefing is March 11
6. Check cost monitor: "no cost data available yet"

## Environment
- Environment: production (Railway)
- Services affected: celery-beat, celery-worker, all frontend pages
- User impact: critical (app is non-functional)

## Root Cause Analysis

Three issues found:

### Issue 1: fetch_news commented out (primary)
In `beat_schedule.py`, the `fetch_news` schedule entry was commented out during BUG-019 with the note "API-based news fetching deprecated / RSS-based system provides articles successfully." The assumption was that the RSS system would continue running independently, but it relies on the same `fetch_news` task to trigger `NewsCollector.collect_all_sources()`.

### Issue 2: Task name mismatch (secondary)
The commented-out entry used `"task": "fetch_news"` (short name), but the `@shared_task` decorator in `tasks/news.py` has no `name=` parameter. Celery auto-generates the name as `crypto_news_aggregator.tasks.news.fetch_news`. Even if the entry were uncommented, Beat would dispatch to a task name no worker recognizes.

### Issue 3: Dead code after return (minor)
The smoke test block at the bottom of `beat_schedule.py` (lines 105-120) falls after `return schedule` and never executes.

## Fix Plan

### Step 1: Manual trigger test
Before making code changes, manually trigger `fetch_news` from Railway shell to verify the task itself runs clean:
```bash
celery -A crypto_news_aggregator.tasks call crypto_news_aggregator.tasks.news.fetch_news
```
Watch worker logs for successful article ingestion.

### Step 2: Add short name to decorator
In `src/crypto_news_aggregator/tasks/news.py`, add `name="fetch_news"` to the `@shared_task` decorator:
```python
@shared_task(
    name="fetch_news",
    bind=True,
    max_retries=3,
    ...
)
def fetch_news(self, source_name=None, days=1):
```

### Step 3: Add schedule entry
In `src/crypto_news_aggregator/tasks/beat_schedule.py`, add inside `get_schedule()` return dict:
```python
"fetch-news-every-3-hours": {
    "task": "fetch_news",
    "schedule": timedelta(hours=3),
    "args": (None,),
    "options": {
        "expires": 5400,      # 1.5 hours
        "time_limit": 1800,   # 30 minutes
        "queue": "news",
    },
},
```

### Step 4: Fix dead smoke test code
Move the smoke test block above `return schedule` so it can actually execute when `SMOKE_BRIEFINGS=1` is set.

### Step 5: Deploy and verify
- Deploy to Railway
- Watch Beat logs for `fetch_news` dispatch
- Watch Worker logs for successful article ingestion
- Confirm articles page shows new articles within 3 hours
- Confirm signals page populates after entity extraction runs
- Confirm next scheduled briefing generates with fresh data

## Files to Change
- `src/crypto_news_aggregator/tasks/news.py` -- add `name="fetch_news"` to decorator
- `src/crypto_news_aggregator/tasks/beat_schedule.py` -- add schedule entry, fix dead code

## Estimated Effort
- 30 min (CC session: manual test + code changes + deploy + verify)

---

## Resolution

**Status:** Code Complete, Awaiting Manual Test
**Branch:** `fix/bug-054-rss-pipeline-not-running`
**Commits:** 
- `b5c0dd7` - fix(tasks): Re-enable RSS ingestion pipeline (BUG-054)
- `cacfd24` - feat(admin): Add /admin/trigger-fetch endpoint for manual testing

### Root Cause
fetch_news disabled in BUG-019, never replaced. Task name mismatch (no `name=` in decorator) would have prevented re-enabling without code change.

### Changes Made

1. **tasks/news.py (line 19):** Added `name="fetch_news"` to `@shared_task` decorator
2. **tasks/beat_schedule.py (lines 18-30):** Re-enabled fetch_news with 3-hour schedule (8 cycles/day)
   - Changed from direct `return {` to `schedule = {` to allow smoke test code to execute
   - Fixed dead smoke test code that fell after `return` statement
3. **api/admin.py (lines 506-551):** Added POST `/admin/trigger-fetch` endpoint
   - Allows manual triggering of fetch_news from HTTP without shell access
   - Returns task_id for monitoring in worker logs

### Testing

**Manual trigger test (PENDING):**
```bash
curl -X POST https://context-owl-production.up.railway.app/admin/trigger-fetch
```

Expected response:
```json
{
  "task_id": "abc123...",
  "task_name": "fetch_news",
  "kwargs": {},
  "message": "✅ News fetch task queued. Check celery-worker logs for task_id=abc123..."
}
```

Then check celery-worker logs for:
- Article count fetched
- Processing time
- Any errors during RSS collection

### Files Changed
- `src/crypto_news_aggregator/tasks/news.py`
- `src/crypto_news_aggregator/tasks/beat_schedule.py`
- `src/crypto_news_aggregator/api/admin.py`

### Deployment Steps
1. Deploy branch to Railway (crypto-news-aggregator service)
2. Run manual trigger test via curl
3. Monitor worker logs for article ingestion
4. Once verified, merge PR and watch beat schedule dispatches every 3 hours