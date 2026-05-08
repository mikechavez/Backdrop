---
id: FEATURE-057
type: feature
status: complete
priority: high
complexity: medium
created: 2026-05-08
updated: 2026-05-08
branch: feature/057-bugops-normalized-event-case-store
completed: 2026-05-08
---

# FEATURE-057: BugOps Normalized Alert-Event and Case Store

## Problem/Opportunity

BugOps needs a source-agnostic data model. `llm_traces` is only the first signal source; Railway logs and freshness checks will come later. The schema must not hard-code `llm_traces` assumptions.

## Proposed Solution

Create write helpers and Pydantic models for `bug_alert_events`, `bug_cases`, `bug_case_events`, and `bug_tool_calls`. Sprint 018 only requires `bug_alert_events` and `bug_cases` to be actively used, but the collection names and model stubs should exist.

## User Story

As a BugOps maintainer, I want every signal source to normalize into the same alert-event shape so cases, Slack alerts, and reports can work across traces, logs, freshness checks, and manual input later.

## Implementation Scope

### Files to Create/Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
tests/bugops/test_bugops_store.py
tests/bugops/test_bugops_models.py
```

### Do Not Modify

```text
src/crypto_news_aggregator/db/mongodb.py
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/services/cost_tracker.py
```

## Exact Implementation Requirements

### `bug_alert_events` required fields

```python
{
    "alert_id": str,                       # generated stable ID
    "case_id": str | None,
    "source_type": str,                    # e.g. "llm_traces", "railway_logs"
    "source_id": str,                      # e.g. "llm_traces.cost_runaway"
    "alert_type": str,                     # e.g. "cost_runaway"
    "severity": str,                       # "info" | "warning" | "high" | "critical"
    "status": str,                         # "new" | "attached" | "ignored"
    "title": str,
    "summary": str,
    "domain": list[str],                   # e.g. ["llm", "cost"]
    "service": str | None,
    "operation": str | None,
    "model": str | None,
    "dedupe_key": str,
    "correlation_keys": list[str],
    "metric": dict,
    "raw_sample_ref": str | None,
    "created_at": datetime,
    "updated_at": datetime,
}
```

### `severity` enum

Use exactly:

```text
info
warning
high
critical
```

Do not omit `severity` just because the first cost source is simple. Railway logs will need this field.

### `bug_cases` required fields

```python
{
    "case_id": str,
    "status": str,                         # "open" | "resolved" | "closed"
    "severity": str,
    "title": str,
    "summary": str,
    "dedupe_key": str,
    "source_types": list[str],
    "alert_ids": list[str],
    "correlation_keys": list[str],
    "created_at": datetime,
    "updated_at": datetime,
    "resolved_at": datetime | None,
    "closed_at": datetime | None,
    "deterministic_report": str | None,
}
```

### Case lifecycle for Sprint 018

- New cases are created with `status="open"`.
- No API/UI/Slack action is implemented to acknowledge, resolve, or close cases.
- Cases are manual-only lifecycle in Sprint 018.
- Do not implement auto-close behavior.
- Only attach new alert events to `open` cases.

### Store helpers

Implement `BugOpsStore` with methods:

```python
async def create_alert_event(event: BugAlertEventCreate) -> BugAlertEvent
async def find_open_case_by_dedupe_key(dedupe_key: str) -> BugCase | None
async def create_case_from_alert(event: BugAlertEvent) -> BugCase
async def attach_alert_to_case(case_id: str, alert_id: str) -> BugCase
async def get_case(case_id: str) -> BugCase | None
```

## Acceptance Criteria

- [ ] `BugAlertEventCreate`, `BugAlertEvent`, `BugCaseCreate`, and `BugCase` models exist.
- [ ] `severity` is required on alert events.
- [ ] `dedupe_key` is required on alert events and cases.
- [ ] Cases use manual-only lifecycle: `open`, `resolved`, `closed`.
- [ ] Store helpers write only to `bug_*` collections.
- [ ] Store helpers do not modify `llm_traces`, `api_costs`, or production app collections.

## Dependencies

- FEATURE-056.

## Test Plan

Create tests:

```text
tests/bugops/test_bugops_models.py
tests/bugops/test_bugops_store.py
```

Test cases:

- Model validation requires `severity`.
- `dedupe_key` is required.
- `find_open_case_by_dedupe_key()` ignores `resolved` and `closed` cases.
- `create_case_from_alert()` creates `status="open"`.
- `attach_alert_to_case()` appends alert ID and updates timestamp.

## Manual Verification

Use a local/test Mongo database or mocked Motor collection to confirm documents are created in:

```text
bug_alert_events
bug_cases
```

## Rollback Plan

Remove BugOps collection writes and model files. New collections are isolated and can be dropped if needed.

## Completion Summary

- Actual complexity: Medium (as expected) — models, store methods, and comprehensive test coverage
- Key decisions made:
  - Used AlertSeverity, AlertStatus, CaseStatus enums for type safety
  - Implemented Motor async database integration for async/await pattern
  - Used $addToSet in attach_alert_to_case to prevent duplicate alert IDs
  - Created model stubs (BugCaseEvent, BugToolCall) to satisfy schema requirements
- Deviations from plan: None — implementation matches spec exactly

## Implementation Details

### Models (src/crypto_news_aggregator/bugops/models.py)
- AlertSeverity enum: info, warning, high, critical
- AlertStatus enum: new, attached, ignored
- CaseStatus enum: open, resolved, closed
- BugAlertEventCreate / BugAlertEvent with all required fields
- BugCaseCreate / BugCase with manual-only lifecycle
- BugCaseEvent and BugToolCall stubs for future use
- Pydantic v2 with Config.populate_by_name for _id alias support

### Store (src/crypto_news_aggregator/bugops/store.py)
- BugOpsStore class with Motor AsyncIOMotorDatabase integration
- create_alert_event() — inserts to bug_alert_events collection
- find_open_case_by_dedupe_key() — filters by status=open only
- create_case_from_alert() — creates new open case with source type and alert ID
- attach_alert_to_case() — appends alert ID, updates timestamp
- get_case() — retrieves case by case_id

### Tests
- test_bugops_models.py: 11 tests covering validation, defaults, enum values, lifecycle
- test_bugops_store.py: 11 tests covering CRUD, filtering, update semantics
- All tests use AsyncMock for Motor mocks, pytest.mark.asyncio for async methods
- Test coverage: severity required, dedupe_key required, open-case filtering, status transitions

### Collections Created (MongoDB)
- bug_alert_events
- bug_cases
- bug_case_events (stub)
- bug_tool_calls (stub)

## Post-Implementation Fixes

### Issue: CI/CD Test Failures
Two test files failed on GitHub CI due to import incompatibilities with FEATURE-057 changes:
- `tests/bugops/test_bugops_monitor_config.py` — ImportError: cannot import BugAlertStore
- `tests/bugops/test_signal_source_base.py` — ImportError: cannot import BugAlertSeverity

### Fixes Applied
1. **monitor.py**: Updated to use BugOpsStore instead of BugAlertStore
   - Store initialized at runtime with database connection (not at instantiation)
   - Refactored _poll_signals() to call create_alert_event() instead of store_alerts()

2. **signal_sources/llm_traces.py**: Changed import from BugAlertSeverity to AlertSeverity

3. **tests/bugops/test_bugops_monitor_config.py**: 
   - Updated test_bugops_monitor_initializes to expect store=None (initialized at runtime)

4. **tests/bugops/test_signal_source_base.py**: 
   - Changed import from BugAlertSeverity to AlertSeverity

### Verification
✅ All 32 bugops tests passing:
- 11 model validation tests
- 11 store CRUD tests  
- 10 monitor and signal source tests

Commits:
- `337ac62` — feat(bugops): Implement normalized alert-event and case store
- `a06850c` — docs(feature-057): Mark as complete with implementation summary
- `e53139c` — docs(sprint-018): Update with FEATURE-057 completion and session log
- `e092f6d` — fix(bugops): Update monitor and signal sources to use new store and model names
