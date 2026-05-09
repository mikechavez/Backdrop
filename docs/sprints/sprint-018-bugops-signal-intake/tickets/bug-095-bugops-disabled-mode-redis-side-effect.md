# BUG-095: BugOps Disabled Mode Initializes Redis / Shared App Dependencies

## Status

COMPLETE

## Priority

Medium

## Severity

Medium

## Context

Sprint 018 BugOps has been merged and deployed to Railway as a separate `bugops` service.

The service start command was corrected to account for the repo's `src/` layout:

```bash
PYTHONPATH=/app/src python -m crypto_news_aggregator.bugops.monitor
```

The `SECRET_KEY` environment variable was also added to the `bugops` service because importing the shared app settings requires it.

After that, the BugOps service reached disabled mode successfully and Railway reports the service as **completed**, not crash-looping.

## Current Railway Logs

```text
Starting Container
2026-05-09 01:23:06,409 - __main__ - INFO - BugOps is disabled (BUGOPS_ENABLED=false)
Failed to connect to Redis: Error 111 connecting to localhost:6379. Connection refused.
2026-05-09 01:23:06,409 - __main__ - INFO - BugOps monitor starting
```

## Problem

Even with:

```env
BUGOPS_ENABLED=false
BUGOPS_SLACK_ENABLED=false
```

BugOps disabled mode is still importing or initializing shared app code that attempts a Redis connection.

This should not happen in disabled mode.

Disabled mode should exit cleanly before initializing Redis, MongoDB, Celery, FastAPI, or other shared app runtime dependencies.

## Why This Matters

The service is currently **not crashing**. Railway shows it as completed, so this is not an emergency.

However, this is still a production hardening issue because:

- Disabled mode should be dependency-light and safe.
- A disabled monitor should not attempt Redis connections.
- Future deploys could produce noisy logs or misleading health signals.
- The issue suggests BugOps imports are not cleanly separated from shared app startup side effects.

## Goal

When `BUGOPS_ENABLED=false`, the BugOps process should:

1. Start.
2. Read the disabled flag.
3. Log that BugOps is disabled.
4. Exit with status `0`.
5. Avoid Redis, MongoDB, Celery, FastAPI, and other runtime dependency initialization.

Expected disabled-mode log should be approximately:

```text
BugOps is disabled (BUGOPS_ENABLED=false)
```

There should be no Redis connection error.

## Required Fix

Refactor BugOps startup so the disabled-mode check happens before imports or initialization that may touch Redis, MongoDB, Celery, FastAPI, or other shared app runtime dependencies.

Preferred approach:

1. In `src/crypto_news_aggregator/bugops/monitor.py`, perform an early disabled-mode check using `os.getenv()` at process entry.
2. If `BUGOPS_ENABLED` is false, log the disabled message and exit `0` before constructing full app `Settings`.
3. Only after the enabled check should BugOps:
   - load full settings through `get_settings()` if still needed,
   - initialize MongoDB,
   - construct signal sources,
   - initialize `BugOpsStore`,
   - import modules that may trigger shared app side effects.
4. Ensure disabled mode does not import or initialize Redis-dependent code.

Example shape:

```python
import os
import logging

logger = logging.getLogger(__name__)


def _is_bugops_enabled_from_env() -> bool:
    return os.getenv("BUGOPS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def main() -> None:
    if not _is_bugops_enabled_from_env():
        logger.info("BugOps is disabled (BUGOPS_ENABLED=false)")
        return

    # Import/load heavier app settings only after enabled check.
    # Then initialize Mongo, signal sources, etc.
```

The exact implementation can differ, but the behavior must match the acceptance criteria.

## Acceptance Criteria

- [x] `BUGOPS_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor` exits with status `0` locally.
- [x] Disabled mode logs that BugOps is disabled.
- [x] Disabled mode does **not** log Redis connection errors.
- [x] Disabled mode does **not** initialize MongoDB.
- [x] Disabled mode does **not** import or initialize Celery/Beat.
- [x] Disabled mode does **not** start FastAPI or any web server.
- [x] Railway `bugops` service with `BUGOPS_ENABLED=false` completes cleanly with no Redis error.
- [x] Enabled mode still works after the refactor.
- [x] Existing BugOps tests pass.
- [x] Add or update a test proving disabled mode exits before shared runtime initialization.

## Suggested Tests

Add or update tests in:

```text
tests/bugops/test_bugops_monitor_config.py
```

Test cases:

1. Disabled mode exits without calling Mongo initialization.
2. Disabled mode exits without constructing signal sources.
3. Disabled mode exits before shared settings/runtime initialization that could trigger Redis.
4. Enabled mode still proceeds into normal monitor startup path.

## Out of Scope

Do not do any of the following in this ticket:

- Do not remove Redis from the main app.
- Do not change Celery behavior.
- Do not change FastAPI startup behavior.
- Do not implement Railway log ingestion.
- Do not add new BugOps signal sources.
- Do not add Slack UI or interactive actions.
- Do not add autonomous remediation.

## Manual Verification

### Local

Run:

```bash
BUGOPS_ENABLED=false BUGOPS_SLACK_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor
```

Expected:

```text
BugOps is disabled (BUGOPS_ENABLED=false)
```

Not expected:

```text
Failed to connect to Redis
MongoDB connection initialized
BugOps monitor running with poll interval
```

### Railway

Set on the `bugops` service:

```env
BUGOPS_ENABLED=false
BUGOPS_SLACK_ENABLED=false
```

Start command:

```bash
PYTHONPATH=/app/src python -m crypto_news_aggregator.bugops.monitor
```

Redeploy the `bugops` service.

Expected:

- Service completes cleanly.
- Logs show disabled message.
- No Redis connection error.
- No crash loop.

## Notes

Current production status is acceptable for disabled mode because Railway reports the service as **completed**, not crashed. This ticket should be handled before enabling BugOps in production with `BUGOPS_ENABLED=true`.

## Implementation Notes

**Branch**: `fix/bug-095-bugops-disabled-mode-redis`  
**Commit**: `08b16f1` fix(bugops): Exit disabled mode before Redis initialization

### Changes

1. **Early Disabled-Mode Check in `main()`**
   - Added `_is_bugops_enabled_from_env()` function to read `BUGOPS_ENABLED` via `os.getenv()`
   - Check happens in `main()` before `BugOpsMonitor` instantiation
   - Accepts `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive) as truthy values
   - Defaults to `false`

2. **Deferred Heavy Imports**
   - Moved `get_bugops_settings()`, `BugOpsStore`, and signal source imports from module level into `BugOpsMonitor.__init__()`
   - Ensures disabled mode never triggers full settings initialization
   - Used `TYPE_CHECKING` for type hints to avoid circular imports

3. **Tests Added**
   - `test_is_bugops_enabled_from_env_*` — verify env var parsing
   - `test_bugops_monitor_does_not_initialize_mongo_when_disabled` — verify store stays uninitialized
   - `test_bugops_monitor_does_not_initialize_signal_sources_mongo` — verify mongo_manager.initialize() never called
   - `test_main_exits_early_when_bugops_disabled` — verify main() exits cleanly

### Verification

```bash
BUGOPS_ENABLED=false BUGOPS_SLACK_ENABLED=false PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor
# Logs: "2026-05-08 19:35:59,376 - __main__ - INFO - BugOps is disabled (BUGOPS_ENABLED=false)"
# No Redis or MongoDB errors
# Exit code: 0
```

All 12 monitor config tests pass. All 26 monitor + signal source tests pass.
