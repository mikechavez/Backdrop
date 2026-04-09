# TASK-046: Register Briefing Tasks with Celery Worker

**Status:** 90% complete (tasks are decorated, need final wiring)  
**Priority:** CRITICAL (unblocks briefing generation)  
**Time:** 5 minutes  
**Files to Change:** 2

---

## Problem

Celery Beat scheduler sends `generate_morning_briefing` task at 8:00 AM EST, but the worker never receives it. Task functions are decorated with `@shared_task` but may not be discovered by Celery worker at startup.

---

## Root Cause

`briefing_tasks.py` exists with proper `@shared_task` decorators, but Celery worker initialization may not import this module, so tasks are never registered with the worker.

---

## Solution

1. Ensure `briefing_tasks.py` is imported in Celery app initialization (`celery.py`)
2. Verify beat schedule references correct task names
3. Confirm autodiscovery is enabled

---

## Step 1: Verify briefing_tasks.py (Already Complete ✅)

Your `src/crypto_news_aggregator/tasks/briefing_tasks.py` already has correct decorators:

```python
@shared_task(
    name="generate_morning_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def generate_morning_briefing_task(self, force: bool = False, is_smoke: bool = False):
    """Generate the morning crypto briefing."""
    # ... implementation
```

**Status:** ✅ No changes needed here.

---

## Step 2: Fix Celery Initialization (celery.py)

**File:** `src/crypto_news_aggregator/celery.py`

Add explicit task import after app initialization:

**Find:**
```python
from celery import Celery

app = Celery('crypto_news_aggregator')
app.config_from_object('...')
# or similar initialization
```

**Add immediately after:**
```python
# Discover all tasks from modules
app.autodiscover_tasks()

# Explicit import to ensure briefing tasks are registered
from crypto_news_aggregator.tasks import briefing_tasks  # noqa: F401
```

**Why:** Celery doesn't automatically scan subdirectories; explicit import ensures `@shared_task` decorators are executed and task names registered with the worker.

---

## Step 3: Verify Beat Schedule (beat_schedule.py)

**File:** `src/crypto_news_aggregator/beat_schedule.py` (already exists)

Your beat schedule is **correct as-is**:

```python
"generate-morning-briefing": {
    "task": "generate_morning_briefing",  # ✅ Matches @shared_task(name="...")
    "schedule": crontab(
        hour=8,
        minute=0,
    ),
    ...
},
```

**Status:** ✅ No changes needed. Task names match what's registered in `briefing_tasks.py`.

---

## Step 4: Verify Celery Configuration (celery_config.py)

**File:** `src/crypto_news_aggregator/celery_config.py`

Your config already has:
```python
from .beat_schedule import get_schedule

# ... later ...

def get_beat_schedule():
    schedule = get_schedule()
    return schedule
```

**Ensure that wherever you initialize the Celery app, you set the beat schedule:**

```python
from crypto_news_aggregator.celery_config import get_beat_schedule

# In your app initialization (celery.py or main entrypoint):
app.conf.beat_schedule = get_beat_schedule()
```

---

## Verification

After changes, verify registration:

```bash
# In container, list all registered briefing tasks
celery -A crypto_news_aggregator.celery inspect registered | grep -i briefing

# Should output:
# crypto_news_aggregator.tasks.briefing_tasks.generate_morning_briefing
# crypto_news_aggregator.tasks.briefing_tasks.generate_evening_briefing
# crypto_news_aggregator.tasks.briefing_tasks.generate_afternoon_briefing
```

If these appear, registration succeeded ✅

---

## Deployment

```bash
git add src/crypto_news_aggregator/celery.py
git commit -m "fix(celery): Ensure briefing tasks imported at worker startup (TASK-046)"
git push origin main
```

Wait for Railway deployment (~2 minutes).

---

## Verification Post-Deployment

**Next briefing cycle:** 8:00 AM EST (13:00 UTC) on 2026-04-09

### Check Worker Logs:
```
Should see within 2 minutes of 8:00 AM EST:
[tasks] Received task: generate_morning_briefing[...]
[briefing_agent] Starting briefing generation...
[llm.gateway] briefing_generate called
```

### Manual Trigger (test immediate):
```bash
celery -A crypto_news_aggregator.celery send_task generate_morning_briefing
# Should execute without "unknown task" error
```

### Check Cost Tracking:
```javascript
// In mongosh
db.llm_traces.countDocuments({ operation: { $regex: "briefing" } })
// Should return > 0 after execution
```

### Check Briefing Output:
```javascript
// In mongosh
db.briefing_drafts.countDocuments({ created_at: { $gte: new Date(Date.now() - 5*60*1000) } })
// Should return > 0 (new briefings in last 5 minutes)
```

---

## Success Criteria

✅ `celery inspect registered` includes briefing task names  
✅ Worker logs show task received (no "unknown task" errors)  
✅ Cost tracking shows briefing operations (`briefing_generate`, etc.)  
✅ `briefing_drafts` collection has new documents after 8:00 AM EST  
✅ No import errors in worker startup logs