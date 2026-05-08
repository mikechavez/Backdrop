---
id: FEATURE-059
type: feature
status: complete
priority: high
complexity: small
created: 2026-05-08
updated: 2026-05-08
completed: 2026-05-08
branch: feature/bugops-signal-intake
---

# FEATURE-059: Alert-to-Case Flow by dedupe_key

## Problem/Opportunity

BugOps needs a path from normalized alert event to case. Sprint 018 does not have multiple live signal sources, so a correlation engine would be speculative. The correct v1 behavior is a simple dedupe-key passthrough.

## Proposed Solution

Implement `process_alert_event()` that creates an alert event, finds or creates an open case by exact `dedupe_key`, attaches the alert to that case, and returns the case.

## User Story

As a BugOps maintainer, I want every alert event to produce or attach to a case so Slack and reports can point to a stable incident record.

## Implementation Scope

### Files to Create/Modify

```text
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
tests/bugops/test_alert_to_case_flow.py
```

### Do Not Modify

```text
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/services/cost_tracker.py
```

## Exact Implementation Requirements

1. Add a function/method equivalent to:

```python
async def process_alert_event(event: BugAlertEventCreate) -> BugCase:
    alert = await store.create_alert_event(event)
    case = await store.find_open_case_by_dedupe_key(alert.dedupe_key)
    if case is None:
        case = await store.create_case_from_alert(alert)
    else:
        case = await store.attach_alert_to_case(case.case_id, alert.alert_id)
    return case
```

2. Only attach to cases with `status="open"`.
3. Do not attach to `resolved` or `closed` cases.
4. Do not implement fuzzy correlation by time window, service, operation, model, or domain.
5. Keep `correlation_keys` fields on alert/case records for future use, but do not use them for matching in Sprint 018.

## Acceptance Criteria

- [x] First alert event for a `dedupe_key` creates a new case.
- [x] Second alert event with same `dedupe_key` attaches to the existing open case.
- [x] Alert event with same `dedupe_key` creates a new case if prior case is `resolved` or `closed`.
- [x] No multi-source correlation logic is implemented.
- [x] Tests prove this is exact dedupe-key passthrough.

## Dependencies

- FEATURE-057.
- FEATURE-058.

## Test Plan

Create tests:

```text
tests/bugops/test_alert_to_case_flow.py
```

Test cases:

- New alert creates case.
- Same hourly cost alert reuses case.
- Closed case is not reused.
- Correlation keys are preserved but not used for matching.

## Manual Verification

Run monitor twice with same simulated threshold breach in same UTC hour. Confirm:

```text
bug_alert_events: 2 documents
bug_cases: 1 open case
case.alert_ids: contains both alerts
```

## Rollback Plan

Disable `BUGOPS_ENABLED`. Collections are isolated to `bug_*`.

## Implementation Details

### Files Modified

**src/crypto_news_aggregator/bugops/store.py (lines 83-91)**
```python
async def process_alert_event(self, event: BugAlertEventCreate) -> BugCase:
    """Process alert event: create alert, find or create case by dedupe_key."""
    alert = await self.create_alert_event(event)
    case = await self.find_open_case_by_dedupe_key(alert.dedupe_key)
    if case is None:
        case = await self.create_case_from_alert(alert)
    else:
        case = await self.attach_alert_to_case(case.case_id, alert.alert_id)
    return case
```
- Exact implementation matches pseudocode in ticket requirements
- Creates alert first, then looks for open case by dedupe_key only
- Leverages existing store methods (create_alert_event, find_open_case_by_dedupe_key, create_case_from_alert, attach_alert_to_case)
- Returns BugCase for caller to log or further process

**src/crypto_news_aggregator/bugops/monitor.py (line 72)**
- Changed `_poll_signals()` to call `await self.store.process_alert_event(event)` instead of `await self.store.create_alert_event(event)`
- This integrates the alert-to-case flow into the main signal collection loop
- Every signal now automatically creates or attaches to a case

### Test Coverage: 8 Tests in test_alert_to_case_flow.py

**TestProcessAlertEventNewCase (2 tests)**
- `test_new_alert_creates_case`: Verifies first alert for a dedupe_key creates an open case
- `test_correlation_keys_preserved_in_new_case`: Verifies correlation keys from alert are preserved in case record

**TestProcessAlertEventReusesOpenCase (1 test)**
- `test_same_dedupe_key_attaches_to_existing_case`: Verifies second alert with same dedupe_key attaches to existing open case, resulting in 2 alert_ids in case

**TestProcessAlertEventClosedCaseHandling (2 tests)**
- `test_creates_new_case_if_prior_case_is_resolved`: Verifies resolved cases are not reused; new case created
- `test_creates_new_case_if_prior_case_is_closed`: Verifies closed cases are not reused; new case created

**TestProcessAlertEventCorrelationKeys (1 test)**
- `test_correlation_keys_not_used_for_matching`: Verifies alerts with same dedupe_key but different correlation_keys reuse case (only dedupe_key used for matching)

**TestProcessAlertEventNoFuzzyCorrelation (2 tests)**
- `test_no_time_window_correlation`: Verifies alerts with same service/model but different hourly dedupe_keys create separate cases
- `test_no_service_correlation`: Verifies alerts with same service but different dedupe_keys create separate cases

### Test Results
- All 8 new tests pass ✅
- All 11 existing store tests still pass ✅
- All 50 BugOps tests pass (8 new + 42 existing) ✅
- No regressions introduced

## Completion Summary

- **Status:** ✅ COMPLETE
- **Actual complexity:** Small (exact as planned)
- **Key decisions made:**
  - Implemented `process_alert_event()` in BugOpsStore following exact pseudocode from ticket
  - Updated BugOpsMonitor._poll_signals() to call process_alert_event instead of create_alert_event directly
  - Created comprehensive test suite covering all acceptance criteria with 6 test classes and 8 test scenarios
  - Used mocks to isolate process_alert_event logic from database details
- **Test coverage:** 8 tests in test_alert_to_case_flow.py
  - New case creation for new dedupe_key
  - Case reuse for same dedupe_key with open status only
  - Rejection of resolved/closed cases (new case created instead)
  - Correlation keys preserved in case record (for future use)
  - No fuzzy correlation by time window or service (exact dedupe_key passthrough only)
- **Deviations from plan:** None
- **Branch:** feature/bugops-signal-intake
- **Dependencies satisfied:** FEATURE-057 ✅, FEATURE-058 ✅
