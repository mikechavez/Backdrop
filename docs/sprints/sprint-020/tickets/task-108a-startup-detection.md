---
ticket_id: TASK-108A
title: Implement startup detection semantics
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-108a-startup-detection
effort_estimate: medium
---

# TASK-108A: Implement startup detection semantics

## Problem Statement

TASK-108 wires detectors into the polling loop with `is_first_poll` tracking,
but the startup detection behavior requires additional specification and testing.
If BugOps restarts while production is already broken, the operator needs to know
immediately — not after the first "healthy" cycle that never comes. This ticket
formalizes and tests the startup detection path end-to-end.

---

## Context

TASK-108 adds `self.is_first_poll = True` to `BugOpsMonitor.__init__()` and sets
`detection_type = "startup"` on BugCases created during the first poll. After the
first complete poll cycle `is_first_poll` is set to `False`.

This ticket adds:
1. Explicit tests for startup vs runtime detection_type assignment
2. Confirmation that cascade suppression applies normally to startup-detected failures
   (a startup articles failure still suppresses into a startup ingestion BugCase if
   one exists — not a special code path, just a test coverage gap to close)
3. Confirmation that no healthy baseline is required before a startup BugCase is
   created — the first poll fires immediately

Key behavioral constraints from the sprint doc:
- BugOps does not require observing a healthy-to-unhealthy transition before
  creating a BugCase
- Startup-created BugCases send Slack notifications (same as runtime BugCases)
- Downstream startup failures cascade-suppress into upstream startup BugCases
- Subsequent polls use `detection_type="runtime"` regardless of whether the
  startup failure is still ongoing

---

## Task

1. Verify `is_first_poll` logic in `monitor.py` is correct after TASK-108
2. Add startup detection test file
3. No new production code needed if TASK-108 implemented correctly — this is
   primarily a test and verification ticket

---

## Files to Create

```text
src/tests/bugops/test_startup_detection.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
  (only if gaps found during test writing — document any changes in completion summary)
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/dependency_graph.py
```

---

## Implementation Requirements

### Verify in `monitor.py` (from TASK-108)

- [ ] `self.is_first_poll = True` set in `__init__()`
- [ ] `detection_type = "startup" if self.is_first_poll else "runtime"` in
  `_poll_freshness_detectors()` before `create_case_direct()` call
- [ ] `self.is_first_poll = False` set after the loop over all detectors completes
  (not inside the loop, not per-detector)
- [ ] If `is_first_poll` is set `False` inside the loop, fix it — it must remain
  `True` for the entire first poll so all detectors in that poll create startup cases

### Test cases in `test_startup_detection.py`

Mock pattern: instantiate `BugOpsMonitor`, mock `self.store`, mock all detector
`check_failure()` to return `True`, mock `dependency_graph` to return empty lists
(no cascade), mock `create_case_direct()` to return a fake `BugCase`.

- [ ] First poll: all detectors create BugCases with `detection_type="startup"`
- [ ] Second poll: all detectors create BugCases with `detection_type="runtime"`
- [ ] `is_first_poll` is `True` at monitor init and `False` after first poll completes
- [ ] Startup BugCase creation still triggers Slack notification (same as runtime)
- [ ] Startup failure cascade-suppresses into upstream startup BugCase: if articles
  failure fires on first poll and an ingestion BugCase was also created on first
  poll (same cycle), articles attaches to ingestion rather than creating a second
  BugCase
- [ ] Ongoing failure (failure present on poll 1 and poll 2): poll 1 creates
  startup BugCase, poll 2 attaches as observation (dedupe check), does not create
  a second runtime BugCase
- [ ] No "healthy baseline required" — first poll creates BugCase immediately if
  failure condition is met, without any prior observation

### Commands to Run

```bash
pytest src/tests/bugops/test_startup_detection.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All test cases pass
- [ ] TASK-108 cascade suppression tests still pass

### Manual Verification

- [ ] In dev, stop article ingestion, restart BugOps monitor — confirm a
  `detection_type="startup"` BugCase appears in MongoDB on the first poll
- [ ] Let the monitor run through a second poll with ingestion still stopped —
  confirm no second BugCase created (observation attached to existing startup case)
- [ ] Restart ingestion — confirm auto-resolution eventually resolves the startup case

---

## Acceptance Criteria

- [ ] `is_first_poll` is `True` for the entire first poll (all detectors in poll 1
  see `is_first_poll=True`)
- [ ] `is_first_poll` is `False` for all subsequent polls
- [ ] Startup BugCases have `detection_type="startup"`
- [ ] Runtime BugCases have `detection_type="runtime"`
- [ ] No healthy baseline required before startup BugCase creation
- [ ] Cascade suppression applies normally to startup failures
- [ ] All test cases pass

---

## Impact

Ensures operators are notified of active production failures immediately on
BugOps restart, not only when new failures begin.

---

## Related Tickets

- Depends on: TASK-108
- Blocks: TASK-109 (auto-resolution must handle startup-type BugCases)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
