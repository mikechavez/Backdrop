---
id: BUG-055
type: bug
status: in-progress
priority: critical
severity: critical
created: 2026-04-02
updated: 2026-04-02
---

# SMOKE_BRIEFINGS=1 Left On in Production, Burning API Credits Against Full MongoDB

## Problem

`SMOKE_BRIEFINGS=1` is still set on the Railway celery-beat service, causing `generate_morning_briefing` to fire every 3 minutes via the smoke test schedule entry (beat_schedule.py lines 108-123). Each cycle makes 4 LLM calls to `claude-sonnet-4-5-20250929` (generate, evaluate, refine, evaluate). All runs fail at the save step because MongoDB Atlas is over its 512 MB storage quota (currently 516 MB). The LLM work is discarded every time.

In 18 minutes of observed logs: 6 cycles x 4 API calls = 24 billed Anthropic API calls producing nothing. Extrapolated: ~480 wasted API calls/day if left running.

## Expected Behavior

Smoke test env var removed after testing. Morning briefing fires once per day at 8 AM EST via the crontab entry. Briefings save successfully to MongoDB.

## Actual Behavior

Two schedule entries for `generate_morning_briefing` are active simultaneously:
1. `generate-morning-briefing` (crontab, 8 AM EST) -- correct
2. `smoke-briefing-every-3min` (crontab, */3 minute) -- should have been disabled

Every 3-minute cycle:
1. Task fires with 0 signals, 0 narratives, 0 patterns, 0 articles
2. Makes 4 LLM calls to Anthropic API (billed)
3. Briefing passes quality check
4. `insert_briefing` fails: `OperationFailure: you are over your space quota, using 516 MB of 512 MB`
5. Error handler logs misleading "briefing_already_exists" / "skipped"
6. Repeat 3 minutes later

Secondary issue: after first task run, cost tracking fails with "Event loop is closed" on all subsequent runs (async lifecycle bug in Motor client, separate from quota issue).

## Steps to Reproduce
1. Check Railway celery-beat service env vars: `SMOKE_BRIEFINGS=1` is set
2. Check celery-worker logs: `generate_morning_briefing` dispatched every 3 minutes
3. Every run shows 4 successful Anthropic API 200 responses followed by MongoDB quota error
4. Check Anthropic API dashboard: charges accumulating for empty briefings

## Environment
- Environment: production (Railway)
- Services affected: celery-beat (dispatching), celery-worker (executing), Anthropic API (billed)
- User impact: critical (wasting money, MongoDB full, site non-functional)

## Root Cause Analysis

### Issue 1: SMOKE_BRIEFINGS env var left on (primary - costs money)
The smoke test block in `beat_schedule.py` (lines 106-123) checks `os.getenv("SMOKE_BRIEFINGS") == "1"` and adds a `*/3 minute` schedule for `generate_morning_briefing`. This was set during testing and never removed. It runs alongside the normal 8 AM crontab entry.

### Issue 2: MongoDB Atlas over 512 MB quota (blocks all writes)
Atlas free tier is at 516/512 MB. Every `insert_one` call raises `OperationFailure`. This blocks briefing saves, cost tracking writes, and will block article ingestion when BUG-054's fetch_news fix is deployed. Even if smoke briefings stop, nothing can write to the database until storage is freed.

### Issue 3: No pre-flight guard on empty data (waste)
Briefing generation proceeds with 4 LLM calls even when all inputs are zero (0 signals, 0 narratives, 0 patterns). A simple guard would prevent burning API credits on guaranteed-empty briefings.

### Issue 4: Cost tracker event loop bug (minor)
After the first task run per worker lifecycle, `Failed to track cost: Event loop is closed` appears on every LLM call. The Motor client gets recreated per task but the cost tracker holds a stale event loop reference. Cost tracking silently fails for all subsequent tasks.

---

## Fix Plan

### Step 1: Stop the bleeding (Railway UI, 1 min)
Remove `SMOKE_BRIEFINGS` env var from celery-beat service on Railway. Redeploy beat. Confirm worker logs show no more 3-minute dispatches.

### Step 2: Free MongoDB storage (Railway shell or Atlas UI, 15 min)
Connect to MongoDB and assess collection sizes:
```javascript
// In mongo shell or Atlas Data Explorer
db.getCollectionNames().forEach(c => {
    const stats = db[c].stats();
    print(`${c}: ${(stats.storageSize / 1024 / 1024).toFixed(2)} MB, docs: ${stats.count}`);
});
```

Candidates for cleanup:
- `cost_tracking` -- likely large from repeated failed write attempts and historical data
- `briefings` -- old briefings (cleanup task exists but may not have run)
- `articles` -- stale articles from before March 22 cutoff
- `llm_spend_log` -- accumulated spend records

Target: get below 450 MB to leave headroom for BUG-054 article ingestion.

### Step 3: Add empty-data guard to briefing generation (CC session, 10 min) ✅ DONE
In `services/briefing_agent.py`, added pre-flight check before LLM calls to skip generation when signals/narratives are empty. Prevents wasted API calls when data pipeline is offline.

### Step 4: Remove smoke test block from beat_schedule.py (CC session, 5 min) ✅ DONE
Deleted lines 106-123 entirely. The smoke test served its purpose. Leaving dead env-var-gated code in production schedules is a liability.

### Step 5: Fix event loop bug in cost tracker (CC session, 15 min) ✅ DONE
Changed `asyncio.create_task()` to direct `await` in cost tracker. Event loop may be closed after task completion, so use direct await instead of fire-and-forget task creation.

## Implementation Complete ✅

**Branch:** `fix/bug-055-smoke-briefings-api-credits`
**Commit:** f119256 - fix(briefings): Add empty-data guard and remove smoke test schedule

### Changes Made:
1. ✅ Empty-data guard: Skip briefing generation when signals/narratives empty (briefing_agent.py:145-153)
2. ✅ Remove smoke test block: Deleted conditional schedule from beat_schedule.py (removed lines 109-129)
3. ✅ Fix cost tracker event loop: Changed asyncio.create_task() to await (briefing_agent.py:830)

### Remaining Manual Steps (required before deployment):
1. 🔴 **Remove SMOKE_BRIEFINGS env var** from Railway celery-beat service (1 min)
2. 🔴 **Prune MongoDB collections** to free storage below 512 MB (15 min)

## Files to Change
- **Railway celery-beat env vars** -- remove `SMOKE_BRIEFINGS`
- **MongoDB Atlas** -- prune collections to get under 512 MB
- `src/crypto_news_aggregator/services/briefing_agent.py` -- add empty-data guard
- `src/crypto_news_aggregator/tasks/beat_schedule.py` -- remove smoke test block (lines 106-123)
- `src/crypto_news_aggregator/services/cost_tracker.py` (or equivalent) -- fix event loop reference

## Estimated Effort
- Step 1: 1 min (manual, Railway UI)
- Step 2: 15 min (manual, Atlas UI/shell)
- Step 3-5: 30 min (CC session)

## Depends On
- Must complete Step 2 (free storage) before deploying BUG-054 (RSS ingestion), or article writes will also fail

## Blocks
- BUG-054 deployment (RSS ingestion writes will fail against full MongoDB)
- TASK-028 burn-in validation (system is not stable while this is active)