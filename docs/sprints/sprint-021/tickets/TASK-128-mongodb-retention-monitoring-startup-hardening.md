---
ticket_id: TASK-128
title: Prevent MongoDB storage exhaustion and make startup index initialization resilient
priority: high
status: OPEN
phase: B
date_created: 2026-09-10
branch: task/bugops-126-mongodb-retention-monitoring-hardening
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

## Acceptance Criteria

- [ ] Retention policies are explicit, configurable, tested, and documented.
- [ ] `llm_traces` TTL behavior is verified end to end.
- [ ] Cache cleanup and bounded article cleanup exist with dry-run support.
- [ ] Scheduled cleanup runs safely and logs auditable results.
- [ ] Storage usage warning/critical monitoring is implemented.
- [ ] Startup behavior is resilient and still observable under index-write failure.
- [ ] Tests pass locally without requiring production credentials.
- [ ] Operational runbook and generated architecture docs are updated.
- [ ] PR includes migration/deployment notes and a rollback approach.
