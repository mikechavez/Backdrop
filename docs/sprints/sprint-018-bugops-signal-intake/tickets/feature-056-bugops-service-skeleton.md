---
id: FEATURE-056
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-08
updated: 2026-05-08
branch: feature/bugops-signal-intake
---

# FEATURE-056: BugOps Service Skeleton and SignalSource Seam

## Problem/Opportunity

BugOps needs to run independently from FastAPI, Celery worker, and Celery Beat. Sprint 018 should prove one signal path without depending on the scheduler it may later monitor.

The implementation must also preserve a seam for future signal sources, especially Railway logs, without building full Railway log ingestion yet.

## Proposed Solution

Create a new `src/crypto_news_aggregator/bugops/` package with a separate monitor entrypoint and a thin `SignalSource` interface. Add a `bugops` process to `Procfile`.

## User Story

As a solo operator, I want BugOps to run as its own monitor process so it can detect operational signals and send alerts without depending on the main Celery Beat scheduler.

## Implementation Scope

### Files to Create

```text
src/crypto_news_aggregator/bugops/__init__.py
src/crypto_news_aggregator/bugops/config.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/signal_sources/__init__.py
src/crypto_news_aggregator/bugops/signal_sources/base.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py
```

### Files to Modify

```text
Procfile
src/crypto_news_aggregator/core/config.py
```

### Do Not Modify

```text
src/crypto_news_aggregator/tasks/*
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/services/cost_tracker.py
context-owl-ui/*
```

## Exact Implementation Requirements

1. Add BugOps config settings to `Settings` in `src/crypto_news_aggregator/core/config.py`:

```python
BUGOPS_ENABLED: bool = False
BUGOPS_POLL_INTERVAL_SECONDS: int = 300
BUGOPS_COST_5MIN_THRESHOLD_USD: float = 0.25
BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD: float = 1.00
BUGOPS_SLACK_ENABLED: bool = False
BUGOPS_SLACK_WEBHOOK_URL: str = ""
```

2. Add a new `bugops` process to `Procfile`:

```text
bugops: python -m crypto_news_aggregator.bugops.monitor
```

3. `bugops/monitor.py` must be runnable with:

```bash
python -m crypto_news_aggregator.bugops.monitor
```

4. `monitor.py` must:

- Load settings using existing `get_settings()`.
- Exit cleanly if `BUGOPS_ENABLED=false`.
- Initialize Mongo using existing `mongo_manager` patterns.
- Run a polling loop using `BUGOPS_POLL_INTERVAL_SECONDS`.
- Log startup and shutdown events.
- Not start FastAPI, Celery worker, or Celery Beat.

5. `signal_sources/base.py` must define a thin async interface:

```python
class SignalSource(Protocol):
    source_type: str
    async def collect(self) -> list[BugAlertEventCreate]: ...
```

6. `railway_logs.py` must define a placeholder `RailwayLogSignalSource` class that raises `NotImplementedError` or returns `[]` with a clear TODO. Do not implement log ingestion in this ticket.

## Acceptance Criteria

- [ ] `python -m crypto_news_aggregator.bugops.monitor` starts and exits cleanly when `BUGOPS_ENABLED=false`.
- [ ] `Procfile` includes `bugops` process.
- [ ] New BugOps package exists with the expected layout.
- [ ] `SignalSource` interface exists and is used by the monitor loop.
- [ ] `RailwayLogSignalSource` placeholder exists but does not ingest logs.
- [ ] No Celery or Beat dependency is introduced for BugOps monitor execution.

## Dependencies

- None.

## Test Plan

Create tests:

```text
tests/bugops/test_signal_source_base.py
tests/bugops/test_bugops_monitor_config.py
```

Suggested commands:

```bash
pytest tests/bugops/test_signal_source_base.py tests/bugops/test_bugops_monitor_config.py
python -m crypto_news_aggregator.bugops.monitor
```

## Manual Verification

Run locally with:

```bash
BUGOPS_ENABLED=false python -m crypto_news_aggregator.bugops.monitor
```

Expected: process logs that BugOps is disabled and exits without error.

## Rollback Plan

Remove the `bugops` Procfile entry and the new `src/crypto_news_aggregator/bugops/` package. Remove added `BUGOPS_*` config fields if unused.

## Completion Summary

- Actual complexity:
- Key decisions made:
- Deviations from plan:
