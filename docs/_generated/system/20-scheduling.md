# Scheduling & Task Dispatch

## Overview

The system generates three daily briefings (morning, afternoon, evening) via Celery Beat—a distributed task scheduler that dispatches periodic tasks to worker processes. This document traces the guarantee that "tomorrow's briefing will be generated" by verifying the three critical components: the beat schedule configuration, worker task registration, and manual trigger capability.

**Anchor:** `#scheduling-task-dispatch`

## Architecture

### Key Components

- **Celery Beat Scheduler**: Long-running process that checks cron schedules every second and dispatches tasks to the message broker (Redis)
- **Celery Worker**: Processes listening on queues that receive dispatched tasks and execute them
- **Task Registration**: Celery `@shared_task` decorator registers functions with short names for reliable dispatch
- **Beat Schedule**: Dictionary of cron schedules and task names defined in `beat_schedule.py`
- **Message Broker**: Redis stores task messages and prevents duplicate queueing

### Data Flow

1. **Beat Scheduler Tick** → Beat process checks system time against cron schedules
2. **Task Dispatch** → When schedule matches (e.g., 8:00 AM EST), beat sends task name + args to Redis queue
3. **Worker Dequeue** → Available worker pulls task from queue
4. **Execution** → Worker runs the task function and stores result in result backend
5. **Briefing Save** → Task saves generated briefing to MongoDB and logs execution

## Implementation Details

### Beat Schedule Configuration

The beat schedule defines the following tasks. Note: several entries are currently commented out in `beat_schedule.py` — see status notes below.

**File:** `src/crypto_news_aggregator/tasks/beat_schedule.py`

**Active scheduled tasks:**

- **Morning briefing** (line 47-61): `crontab(hour=8, minute=0)` → 8:00 AM EST
- **Afternoon briefing** (line 64-75): `crontab(hour=14, minute=0)` → 2:00 PM EST
- **Evening briefing** (line 77-88): `crontab(hour=20, minute=0)` → 8:00 PM EST
- **Narrative summary refresh — morning** (lines 119-126): `crontab(hour=7, minute=30)` → 7:30 AM EST. Drains the `needs_summary_update` queue; runs up to 20 narratives per cycle. Added FEATURE-012 (Sprint 15).
- **Narrative summary refresh — evening** (lines 127-134): `crontab(hour=19, minute=30)` → 7:30 PM EST. Same consumer, second daily run. Added FEATURE-012 (Sprint 15).

**Disabled/commented-out entries:**

- **fetch_news** (lines 22-30, commented out): Was re-enabled in BUG-054, then disabled in BUG-057 when both configured news API sources (CoinDesk JSON API, Bloomberg) were confirmed dead — CoinDesk returns HTML, Bloomberg returns 403. RSS fetcher handles all article ingestion. Manual trigger available via `POST /admin/trigger-fetch`.
- **check-price-alerts** (lines 33-41, commented out): Placeholder stub only — no price API is integrated. Never a real feature.

Each active schedule entry includes:
- `task`: Short task name matching `@shared_task(name=...)` (src/crypto_news_aggregator/tasks/briefing_tasks.py:69, 130, 191)
- `schedule`: Crontab expression using `celery.schedules.crontab` (src/crypto_news_aggregator/tasks/beat_schedule.py:4)
- `kwargs`: Task parameters (e.g., `force=False` prevents duplicate generation)
- `options`: Celery execution settings (expires, time_limit, queue routing)

### Periodic Worker Tasks (Not Beat Schedule)

Some recurring tasks run inside the Celery worker process on a timed interval rather than via beat schedule. These are registered in `worker.py` and do not appear in `beat_schedule.py`.

**Auto-dormant zombie narratives** (`tasks/narrative_cleanup.py`, `worker.py` line 267):
- **Interval:** Every 1 hour
- **Function:** `auto_dormant_zombie_narratives()` — queries for active narratives where all source articles have been deleted (zero surviving articles). Marks them dormant to prevent fabricated or un-verifiable content from appearing in briefings.
- **Logging:** Emits a Railway-visible warning with narrative titles when zombies are found.
- Added TASK-073 (Sprint 15).

### Task Registration

The briefing tasks are registered with **short names** that must match beat schedule references:

**File:** `src/crypto_news_aggregator/tasks/briefing_tasks.py`

```
@shared_task(name="generate_morning_briefing")   # Line 69
@shared_task(name="generate_evening_briefing")   # Line 130
@shared_task(name="generate_afternoon_briefing") # Line 191
```

**File:** `src/crypto_news_aggregator/tasks/narrative_refresh.py`

```
@shared_task(name="refresh_flagged_narratives")  # FEATURE-012
```

These names are passed to the beat schedule without module paths (short form), enabling reliable dispatch.

**Why this matters:** Past bugs (BUG-014, BUG-022) occurred when task names in beat schedule didn't match `@shared_task(name=...)` registrations, causing beat to queue tasks that workers couldn't find. The current implementation uses consistent short names everywhere.

### Task Execution Pattern

Each briefing task follows this pattern:

1. **Wrapped async execution** (src/crypto_news_aggregator/tasks/briefing_tasks.py:28-36): Uses `asyncio.new_event_loop()` to run async code in Celery worker context
2. **MongoDB initialization** (line 39-46): Ensures async database connection is ready
3. **Briefing generation** (line 49-65): Calls `generate_morning_briefing()` service function with task_id for correlation
4. **Error handling** (line 123-126): Catches exceptions and retries up to 2 times with 5-minute delays
5. **Logging** (line 92-93, 153-154): Logs task start, duration, result, and any errors

**Key file:** `src/crypto_news_aggregator/tasks/briefing_tasks.py`

### Manual Trigger Capability

The system provides an HTTP endpoint to manually trigger briefing generation for testing:

**File:** `src/crypto_news_aggregator/api/admin.py:415-490`

- **Endpoint:** `POST /admin/trigger-briefing`
- **Parameters:**
  - `briefing_type`: "morning", "afternoon", or "evening" (auto-detected if omitted)
  - `force`: If `true`, bypasses duplicate check (allows multiple briefings per day)
  - `is_smoke`: If `true`, marks as test (doesn't appear in production feed)
- **Implementation:** Maps briefing type to task function and calls `delay()` to queue immediately
- **Verification:** Returns task ID for tracking and logs entry point (line 450-451)

This enables the "tomorrow briefing guarantee" verification: operators can manually trigger a briefing at any time and confirm it executes within 10 minutes.

## Operational Checks

### Health Verification

**Check 1: Beat scheduler is running**
```bash
# Query Celery to list scheduled tasks
celery -A crypto_news_aggregator.tasks inspect active_queues
# Should show worker processes listening on "default" and "alerts" queues
```
*File reference:* `src/crypto_news_aggregator/tasks/beat_schedule.py:32-41` (queue configuration)

**Check 2: Task registration is correct**
```bash
# List all registered task names
celery -A crypto_news_aggregator.tasks inspect registered
# Should include: "generate_morning_briefing", "generate_evening_briefing",
#                 "generate_afternoon_briefing", "refresh_flagged_narratives"
```
*File reference:* `src/crypto_news_aggregator/tasks/briefing_tasks.py:69, 130, 191`; `src/crypto_news_aggregator/tasks/narrative_refresh.py` (task names)

**Check 3: Manual trigger works (proves worker is listening)**
```bash
curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&force=true"
# Should return 200 with task_id and message
```
*File reference:* `src/crypto_news_aggregator/api/admin.py:415, 453-454` (endpoint definition and response)

**Check 4: Briefing was saved to MongoDB**
```bash
# Query for latest briefing
db.briefings.findOne({briefing_type: "morning"}, {generated_at: 1, _id: 1}).sort({generated_at: -1})
# Should show a document with generated_at timestamp matching manual trigger time
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:836-894` (save logic)

### "Tomorrow Briefing Guarantee" Verification

To verify briefings will run tomorrow at 8 AM EST:

1. **Verify beat schedule at runtime:**
   ```bash
   celery -A crypto_news_aggregator.tasks inspect scheduled
   # Lists all scheduled tasks; confirm morning/afternoon/evening briefings are present
   ```
   *Reference:* `src/crypto_news_aggregator/tasks/beat_schedule.py:47-88`

2. **Verify worker can execute (dry run):**
   ```bash
   # Manually trigger and confirm successful execution within 10 seconds
   curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&force=true"
   # Task should complete and briefing appear in MongoDB within 10 seconds
   ```
   *Reference:* `src/crypto_news_aggregator/api/admin.py:453-454` (response includes task_id)

3. **Verify task execution logs:**
   ```bash
   # Check worker logs for "Starting morning briefing generation task"
   docker logs <worker-container> | grep "briefing generation"
   ```
   *Reference:* `src/crypto_news_aggregator/tasks/briefing_tasks.py:92-94` (logging statement)

4. **Verify MongoDB persistence:**
   ```bash
   # Confirm briefing document was saved
   db.briefings.findOne({_id: ObjectId("...")})
   # Should have: _id, briefing_type, generated_at, content, task_id
   ```
   *Reference:* `src/crypto_news_aggregator/db/operations/briefing.py` (insert_briefing function)

### Debugging

**Issue:** Beat scheduler not dispatching tasks at scheduled times
- **Root cause:** Beat process crashed or lost connection to Redis
- **Verification:** Check beat process logs and Redis connectivity
- **Fix:** Restart beat service: `celery -A crypto_news_aggregator.tasks beat -l info`

**Issue:** Briefing task queued but worker doesn't execute (task name mismatch)
- **Root cause:** `@shared_task(name=...)` doesn't match task name in beat schedule
- **Verification:** Run `celery -A crypto_news_aggregator.tasks inspect registered` and compare to `beat_schedule.py`
- **Fix:** Ensure names match exactly (e.g., "generate_morning_briefing" in both places)
  *Reference:* `src/crypto_news_aggregator/tasks/briefing_tasks.py:69` vs. `beat_schedule.py:48`

**Issue:** Task executed but briefing not saved to MongoDB
- **Root cause:** Async/await error in briefing generation, MongoDB connection failed
- **Verification:** Check worker logs for exceptions; query MongoDB connectivity
- **Fix:** Check briefing service logs and MongoDB cluster status
  *Reference:* `src/crypto_news_aggregator/tasks/briefing_tasks.py:123-126` (exception handler)

**Issue:** Multiple briefings generated for same day (force=true accidentally left on)
- **Root cause:** `force=False` not set in beat schedule kwargs, or manual trigger used force=true
- **Verification:** Query MongoDB for multiple briefings with same `briefing_type` and date
- **Fix:** Set `force=False` in beat schedule for production (line 56)
  *Reference:* `src/crypto_news_aggregator/tasks/beat_schedule.py:56, 70, 83`

## Relevant Files

### Core Logic
- `src/crypto_news_aggregator/tasks/beat_schedule.py` - Beat schedule definition and cron timing
- `src/crypto_news_aggregator/tasks/briefing_tasks.py` - Task registration and execution wrapper
- `src/crypto_news_aggregator/tasks/narrative_refresh.py` - Narrative summary refresh consumer (FEATURE-012)
- `src/crypto_news_aggregator/tasks/narrative_cleanup.py` - Auto-dormant zombie narrative periodic task (TASK-073)
- `src/crypto_news_aggregator/tasks/celery_config.py` - Celery app configuration (registers beat schedule)
- `src/crypto_news_aggregator/tasks/__init__.py:25` - Applies beat schedule to Celery app

### Integration Points
- `src/crypto_news_aggregator/api/admin.py:415` - HTTP trigger endpoint
- `src/crypto_news_aggregator/services/briefing_agent.py:111` - Briefing generation entry point
- `src/crypto_news_aggregator/services/briefing_agent.py:836` - MongoDB save operation
- `src/crypto_news_aggregator/db/operations/briefing.py` - Database persistence layer

### Configuration
- `src/crypto_news_aggregator/core/config.py` - Celery broker/backend settings
- `.env` or environment variables - CELERY_BROKER_URL (Redis), CELERY_RESULT_BACKEND (Redis)

## Related Documentation
- **Data Model (50-data-model.md)** - MongoDB briefing collection schema and fields
- **LLM Integration (60-llm.md)** - How briefing content is generated via Claude API

---
*Last updated: 2026-04-25* | *Generated from: 02-celery-beat.txt, 02-celery-registration.txt, 05-briefing-generation.txt* | *Anchor: scheduling-task-dispatch*