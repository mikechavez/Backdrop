---
id: FEATURE-059
type: feature
status: backlog
priority: high
complexity: small
created: 2026-05-08
updated: 2026-05-08
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

- [ ] First alert event for a `dedupe_key` creates a new case.
- [ ] Second alert event with same `dedupe_key` attaches to the existing open case.
- [ ] Alert event with same `dedupe_key` creates a new case if prior case is `resolved` or `closed`.
- [ ] No multi-source correlation logic is implemented.
- [ ] Tests prove this is exact dedupe-key passthrough.

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

## Completion Summary

- Actual complexity:
- Key decisions made:
- Deviations from plan:
