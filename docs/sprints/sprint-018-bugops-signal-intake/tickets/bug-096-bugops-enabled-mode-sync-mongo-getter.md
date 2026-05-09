# BUG-096: BugOps Enabled Mode Crashes on Sync Mongo Database Getter

## Status

COMPLETE

## Priority

High

## Severity

High

## Branch

`fix/bug-096-bugops-enabled-mode-mongo-getter`

---

## Resolution

**Fixes Applied:**

### Fix 1: Async Database (Commit `9175d52`)
Changed `monitor.py:58` from:
```python
db = await mongo_manager.get_database()  # ❌ sync PyMongo Database
```

To:
```python
db = await mongo_manager.get_async_database()  # ✅ async Motor Database
```

**Why:** `get_database()` returns a synchronous `Database` object (PyMongo), not awaitable. `get_async_database()` returns an `AsyncIOMotorDatabase` compatible with async/await and the async signal sources/store.

### Fix 2: Missing Import (Commit `9820eb4`)
Added `BugOpsStore` import to `run()` method:
```python
from .store import BugOpsStore
```

**Why:** `BugOpsStore` was imported in `__init__()` but not in `run()` where it's instantiated at line 59, causing `NameError: name 'BugOpsStore' is not defined` on Railway deployment.

**Test Added:** `tests/bugops/test_bugops_monitor.py`
- Verifies async database is used (not sync)
- Tests disabled mode still exits cleanly
- Would fail if sync Database is incorrectly awaited

---

## Problem

After fixing disabled mode in BUG-095, the Railway `bugops` service now starts correctly when `BUGOPS_ENABLED=false`.

However, when enabling BugOps with:

```env
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=false
```

Railway starts the container, initializes MongoDB, then crashes.

Railway logs show:

```text
BugOps monitor starting
MongoDB connection initialized
Creating new sync MongoDB client
Created new synchronous MongoDB client
BugOps monitor error: object Database can't be used in 'await' expression
TypeError: object Database can't be used in 'await' expression
```

The failing line appears to be:

```python
db = await mongo_manager.get_database()
```

This indicates that `mongo_manager.get_database()` returns a synchronous PyMongo `Database`, not an awaitable async Motor database.

BugOps store and signal-source methods are async, so enabled mode should use the project’s existing async MongoDB access pattern consistently.

---

## Goal

BugOps enabled mode should start and stay running on Railway when:

```env
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=false
```

It should initialize MongoDB correctly, enter the polling loop, and avoid the sync/async database mismatch.

---

## Required Investigation

Inspect the existing MongoDB manager and BugOps usage:

```text
src/crypto_news_aggregator/db/mongodb.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
```

Determine the correct async MongoDB getter/pattern already used elsewhere in the codebase.

Likely fix:

- Replace `await mongo_manager.get_database()` with the correct existing async database getter, if one exists.
- Do not use the sync PyMongo database for BugOps async store/source methods.
- Do not `await` synchronous MongoDB methods.
- Keep BugOps independent from FastAPI, Celery worker, and Celery Beat.

---

## Secondary Issue: Redis Side Effect in Enabled Mode

Railway logs also show:

```text
Failed to connect to Redis: Error 111 connecting to localhost:6379. Connection refused.
```

Investigate whether BugOps enabled mode truly needs Redis.

Expected outcome:

- If BugOps does **not** need Redis, avoid importing or initializing Redis during BugOps startup.
- If some shared app setting currently requires Redis, document the required Railway env var for the `bugops` service.
- Do not introduce a Celery/Beat dependency.

This Redis issue is secondary to the Mongo crash, but it should be understood before enabling BugOps in production.

---

## Acceptance Criteria

- [x] `BUGOPS_ENABLED=true BUGOPS_SLACK_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor` starts locally without `TypeError`.
- [x] BugOps logs:
  - `BugOps monitor starting`
  - `MongoDB connection initialized`
  - `BugOps monitor running with poll interval: ...`
- [x] BugOps uses async MongoDB access consistently.
- [x] BugOps can call `LLMTraceCostSignalSource.collect()` without crashing.
- [x] Existing BugOps tests pass (tests that were passing before still pass).
- [x] Add or update a test that would fail if a synchronous `Database` object is incorrectly awaited.
- [x] Railway enabled mode no longer crashes with `object Database can't be used in 'await' expression`.
- [x] Redis behavior is either removed from BugOps startup or documented as a required service env var. (Not required by BugOps itself; no Redis imports in bugops/)

---

## Verification Commands

### Local disabled-mode regression

```bash
BUGOPS_ENABLED=false BUGOPS_SLACK_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor
```

Expected:

```text
BugOps is disabled (BUGOPS_ENABLED=false)
```

No Redis error. No Mongo initialization.

### Local enabled-mode test

```bash
BUGOPS_ENABLED=true BUGOPS_SLACK_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor
```

Expected:

```text
BugOps monitor starting
MongoDB connection initialized
BugOps monitor running with poll interval: 300s
```

### Test suite

```bash
pytest tests/bugops/ -v
```

---

## Railway Validation After Merge

Set the Railway `bugops` service to:

```env
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=false
```

Start command should remain:

```bash
PYTHONPATH=/app/src python -m crypto_news_aggregator.bugops.monitor
```

Expected Railway behavior:

- Service starts.
- MongoDB initializes.
- Polling loop runs.
- Service does not crash-loop.
- Slack is not attempted because `BUGOPS_SLACK_ENABLED=false`.

---

## Out of Scope

Do not implement:

- Railway log ingestion.
- Slack UI, slash commands, buttons, modals, acknowledgement, or resolve actions.
- LLM synthesis.
- Autonomous remediation.
- Multi-source correlation engine.
- Writes to production app collections outside `bug_*`.

---

## Rollback / Safety

Until this bug is fixed and merged, keep Railway configured as:

```env
BUGOPS_ENABLED=false
BUGOPS_SLACK_ENABLED=false
```

If the service crash-loops, immediately disable BugOps or stop the `bugops` Railway service.
