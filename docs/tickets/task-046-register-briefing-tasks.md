# TASK-046: Register Briefing Tasks with Celery Worker

**Status:** ✅ COMPLETE (verified all infrastructure in place)
**Priority:** CRITICAL (unblocks briefing generation)  
**Time:** ~10 minutes  
**Files Changed:** 1 (added test_task_registration.py)

---

## Summary

All briefing tasks are correctly registered with the Celery worker. The infrastructure was already 100% in place - all that was needed was verification that task discovery is working properly.

---

## Verification Complete ✅

### Step 1: Task Decorators ✅

All briefing tasks properly decorated in `src/crypto_news_aggregator/tasks/briefing_tasks.py`:
- `generate_morning_briefing` (8:00 AM EST daily)
- `generate_evening_briefing` (8:00 PM EST daily)
- `generate_afternoon_briefing` (manual trigger only)
- `cleanup_old_briefings` (Sunday 3:00 AM EST weekly)
- `force_generate_briefing` (admin use)

### Step 2: Celery Initialization ✅

`src/crypto_news_aggregator/tasks/__init__.py` correctly:
1. **Imports all briefing tasks** (lines 27-32)
2. **Creates Celery app** (line 40)
3. **Configures from celery_config** (line 41)
4. **Sets beat schedule** (line 44)
5. **Calls autodiscover_tasks()** (lines 67-79) with briefing_tasks module listed

### Step 3: Beat Schedule ✅

`src/crypto_news_aggregator/tasks/beat_schedule.py` has correct task names matching @shared_task decorators:
- `"generate_morning_briefing"` ✅
- `"generate_evening_briefing"` ✅
- `"cleanup_old_briefings"` ✅
- `"consolidate_narratives"` ✅
- `"warm_cache"` ✅
- `"send_daily_digest"` ✅

### Step 4: Celery Configuration ✅

`src/crypto_news_aggregator/tasks/celery_config.py` correctly:
- Imports `get_beat_schedule()` from beat_schedule.py
- Provides `get_beat_schedule()` function for app initialization
- Beat schedule properly applied via `app.conf.beat_schedule`

---

## Task Discovery Chain

Worker command on Railway:
```bash
celery -A crypto_news_aggregator.tasks worker --loglevel=info
```

Discovery flow:
1. ✅ Worker imports `crypto_news_aggregator.tasks` (the `__init__.py`)
2. ✅ `__init__.py` imports all task modules (lines 23-38)
3. ✅ `@shared_task` decorators execute and register tasks with Celery app
4. ✅ `app.autodiscover_tasks()` scans and confirms all tasks registered
5. ✅ Worker is ready to receive tasks from beat scheduler

---

## Added Verification Script

**File:** `test_task_registration.py`

Can be run locally to verify task registration:
```bash
python test_task_registration.py
```

Checks:
- All required briefing tasks are registered
- Beat schedule entries reference correct task names
- No missing or unregistered tasks

---

## Success Criteria ✅

✅ Celery app properly initialized with all imports  
✅ Task decorators match beat_schedule task names  
✅ Autodiscovery enabled and scans all task modules  
✅ No celery.py file needed (uses tasks/__init__.py pattern)  
✅ Verification script confirms all tasks discoverable  

---

## Next Steps

1. Monitor Celery beat scheduler to confirm tasks are dispatched
2. Monitor worker logs to confirm tasks are received and executed
3. Monitor cost tracking to confirm briefing operations are recorded
4. Verify briefing_drafts collection shows new documents after scheduled times