---
ticket_id: TASK-128
title: Prevent MongoDB storage exhaustion and make startup index initialization resilient
priority: high
status: IN_PROGRESS
phase: B
date_created: 2026-09-10
branch: codex/task-128-mongodb-retention-hardening
effort_estimate: large
depends_on: BUG-105
---

# TASK-128: Prevent MongoDB storage exhaustion and make startup index initialization resilient

## Problem Statement

BUG-105 restored service after MongoDB Atlas reached its 512 MB quota and blocked writes. The system currently relies on retention behavior that may not be sufficient or observable, and a failure creating the LLM trace index aborts every web worker. This ticket implements the durable prevention and resilience work.

## Files to Inspect and Likely Modify

```
src/crypto_news_aggregator/core/config.py
src/crypto_news_aggregator/db/mongodb.py
src/crypto_news_aggregator/main.py
src/crypto_news_aggregator/llm/tracing.py
src/crypto_news_aggregator/llm/cache.py
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/services/cost_tracker.py
src/crypto_news_aggregator/tasks/__init__.py
src/crypto_news_aggregator/tasks/beat_schedule.py
src/crypto_news_aggregator/tasks/worker.py
src/crypto_news_aggregator/tasks/                    # locate the appropriate cleanup-task module
src/crypto_news_aggregator/api/admin.py              # only if an admin/read-only storage endpoint is justified
scripts/mongodb_storage_audit.py                     # share audit logic if created by BUG-105
tests/test_tracing.py
tests/                                                  # add focused retention/startup tests
docs/_generated/system/50-data-model.md
docs/_generated/system/60-llm.md
docs/_generated/system/10-entrypoints.md
docs/sprints/sprint-021/tickets/BUG-105-*.md
```

Before editing, inspect the current task registration and database manager implementation; do not assume the generated docs exactly match the source.

## Requirements

### Retention

- Ensure `llm_traces` has a functioning TTL index on `timestamp` with the approved retention period. The current documented target is 30 days; preserve that unless BUG-105 records a different approved policy.
- Define and enforce expiration for `llm_cache`. Cache records must be recoverable by recomputation and must not be treated as authoritative business data.
- Define article retention by relevance tier, preserving enough recent Tier 1/2 history for active narratives and briefings. Tier 3 may have a shorter retention period only after confirming it is not required by current processing or audit workflows.
- Do not delete `daily_briefings`, active `narratives`, or BugOps evidence by default.
- Make retention windows configurable through settings/environment variables. Document the variable names and safe defaults in `.env.example`; production values belong in deployment secrets/configuration, never in source.

### Cleanup execution

- Add a scheduled, bounded cleanup task through the existing Celery task registration/scheduling pattern.
- Make each cleanup operation idempotent and batch-limited.
- Log collection, cutoff, matched count, deleted count, duration, and errors without logging document contents or secrets.
- Provide a dry-run mode and explicit confirmation for manual invocation.
- Ensure one collection’s cleanup failure does not prevent cleanup of unrelated collections.

### Storage monitoring

- Add a read-only storage audit/report that exposes database total, collection totals, index totals, quota if available, and percentage used.
- Add thresholds for warning and critical conditions before the Atlas quota is reached.
- Route alerts through the project’s existing operational/BugOps mechanism; do not rely solely on Slack until its delivery is verified.
- Add tests for threshold calculation and missing/unavailable quota metrics.

### Startup resilience

- Review `main.py` lifespan and `llm/tracing.py:ensure_trace_indexes()`.
- Required indexes must be validated and failures must remain visible.
- Avoid allowing a noncritical trace TTL/index initialization failure to make the entire API unavailable, if the current architecture permits safe degradation.
- If startup must still fail for a particular index, emit a precise operational error and ensure the failure is represented in the monitoring path.
- Do not silently swallow Atlas quota errors.

### Documentation

Update the relevant generated system docs and add a concise operational runbook covering:

- how to locate `MONGODB_URI` without exposing it;
- how to run the read-only audit;
- how to review retention candidates;
- how to perform bounded cleanup;
- how to verify Atlas headroom and TTL indexes;
- how to restart and validate the application;
- escalation criteria for increasing the Atlas tier.

## Security and Data Safety

- Never commit `.env`, production secrets, or full MongoDB URIs.
- Redact credentials and sensitive document fields from logs and reports.
- No unbounded collection drops or `deleteMany({})` in production code.
- Destructive operations require explicit filters, a dry run, and an auditable result.

## Verification

```bash
pytest tests/test_tracing.py -v
pytest tests/ -q
python scripts/mongodb_storage_audit.py --help
```

Add focused tests for TTL index options, cleanup cutoffs, batch limits, dry-run behavior, alert thresholds, and startup behavior when index creation raises Atlas code 8000.

## Implementation Update (2026-09-12)

- Added configurable trace/cache/article retention, bounded batch size, and estimated storage alert thresholds; documented in the operational runbook. The local `.env.example` template is excluded from the commit by the repository's environment-file security hook.
- Trace TTL initialization now validates the configured TTL and uses `collMod` rather than dropping an existing timestamp index when its TTL changes. Startup treats trace/cache index setup as noncritical, logs exceptions, and continues in degraded mode; `/api/v1/health` reports missing/mismatched TTL indexes.
- Cache writes now set `expires_at` and cache lookups ignore expired entries. Added a TTL index and bounded cleanup backstop.
- Added daily Celery cleanup for expired traces/cache and optional tier-3 articles. Each collection is isolated; each delete selects at most the configured number of `_id`s, then deletes only those IDs. Manual CLI defaults to dry-run and requires both `--execute` and `--confirm`. Tier-3 deletion defaults off and excludes articles referenced by narratives.
- Added dbStats storage estimate reporting and threshold classification through the existing BugOps signal pipeline. Reports and alerts explicitly state that the configured-quota percentage is an estimate and Atlas is authoritative.
- Removed credentials/URI details from MongoDB validation and connection logging; audit output now redacts the entire URI authority.
- Added [MongoDB retention and quota runbook](../../../runbooks/mongodb-retention-and-quota.md) and updated generated data-model, LLM, and entrypoint docs.
- Focused local verification: 51 tests passed across retention, tracing, database validation, and health endpoint suites; the two beat-schedule tests passed; changed Python files compile. A broader command including `tests/tasks/test_briefing_tasks.py` stalled in that existing test module and was interrupted after 52 tests had passed; no production database was accessed.
- At the time of the original implementation update, live MongoDB verification was still pending; the later deployment findings are recorded below.

## Live Deployment Verification (2026-09-13)

- Railway `/api/v1/health` returned HTTP 200. MongoDB and Redis checks were `ok`; `mongodb_retention` was `ok`, reporting the configured trace TTL as 2,592,000 seconds (30 days) and the cache TTL index as 0 seconds on `expires_at`.
- Supplied Railway logs repeatedly reported `llm_traces indexes ensured; ttl_days=30` without index errors.
- Celery logs confirm `mongodb_retention_cleanup` was received and succeeded on 2026-09-12 and 2026-09-13. On the observed runs, no expired traces were found, one expired cache record was deleted on the first run and none on the next, and article cleanup was disabled by configuration. The task used `dry_run: false` and a 1,000-ID per-collection batch limit.
- This verifies the scheduled task is being dispatched and executed in Railway and that the configured TTL indexes are visible to health checks. Actual asynchronous TTL deletion timing and Atlas code-8000 degradation remain unverified. BugOps alert delivery also remains unverified.
- The health response still reported unrelated LLM-routing and pipeline-heartbeat datetime errors; those are tracked separately and are not evidence of a MongoDB retention failure.

## Acceptance Criteria

- [x] Retention policies are explicit, configurable, tested, and documented.
- [ ] `llm_traces` TTL expiration is verified end to end against MongoDB (the live index/configuration is confirmed; actual TTL deletion timing remains unverified).
- [x] Cache cleanup and bounded article cleanup exist with dry-run support; article deletion is off by default.
- [x] Scheduled cleanup runs as a bounded task in the Railway Celery deployment and logs cutoff, matched/selected/deleted counts, duration, and errors.
- [x] Storage usage warning/critical monitoring is implemented via BugOps, using an explicitly labeled dbStats estimate.
- [x] Startup trace/cache index behavior is resilient and observable via logs and health status under index-write failure.
- [x] Focused tests pass locally without production credentials; full suite not yet verified.
- [x] Operational runbook and generated architecture docs are updated.
- [x] Deployment notes and rollback/data irreversibility caveats are documented in the runbook.
