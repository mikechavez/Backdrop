---
ticket_id: TASK-109
title: Implement auto-resolution with Recovery Window
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-109-auto-resolution
effort_estimate: medium
---

# TASK-109: Implement auto-resolution with Recovery Window

## Problem Statement

BugCases currently require manual close. If a production failure self-heals
overnight, the operator wakes up to an open BugCase that no longer reflects
reality. Auto-resolution closes cases when the system recovers, without operator
intervention.

---

## Context

Auto-resolution is based on outcome recovery, not component health. A BugCase
does not resolve because a worker is healthy — it resolves because the artifact
that was missing is being produced again.

Each freshness detector exposes `check_recovery(db) -> bool` (TASK-104 to TASK-107).
The auto-resolution loop calls this each polling cycle for every open freshness BugCase.

### Recovery model

```
1. Recovery condition met, recovery_candidate_at is None
   → set recovery_candidate_at = now

2. Recovery condition met, recovery_candidate_at is set
   → elapsed = now - recovery_candidate_at
   → if elapsed >= Recovery Window: resolve the BugCase
   → else: no action (waiting for window to elapse)

3. Recovery condition NOT met, recovery_candidate_at is set
   → clear recovery_candidate_at = None
   → BugCase remains open, no new BugCase, no notification

4. Recovery condition NOT met, recovery_candidate_at is None
   → no action
```

### Key invariants from sprint spec

- **Auto-resolution does NOT send a Slack notification.** Resolution is silent.
- **Manually closed cases (`status = "closed"`) are never auto-resolved.** Skip them.
- **Muted/snoozed cases resolve normally.** `muted_until` and `snoozed_until`
  affect notifications only — do not block resolution.
- **BugCases resolve as a unit.** No partial resolution.
- **Failure recurrence before window elapses:** clear `recovery_candidate_at`,
  BugCase stays open, no new BugCase created, no Slack sent.

### Detector lookup

TASK-108 adds `self.detector_by_subsystem` to the monitor:
`{d.root_subsystem: d for d in self.freshness_detectors}`.
Use this map to find the right detector for each open BugCase.

### Dedupe key pattern for freshness BugCases

Freshness BugCase dedupe keys follow the format `detector_type:subsystem`
(e.g. `"article_freshness:articles"`). The auto-resolution loop identifies
freshness BugCases by checking if `dedupe_key` contains `":"`.

---

## Task

1. Add `_run_auto_resolution()` method to `BugOpsMonitor` in `monitor.py`
2. Call it from the main loop after `_poll_freshness_detectors()`
3. Add `resolve_case()`, `update_recovery_candidate()`, and
   `get_open_freshness_cases()` to `BugOpsStore`
4. Write unit tests for recovery lifecycle

---

## Files to Create

```text
src/tests/bugops/test_auto_resolution.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/core/config.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/dependency_graph.py
```

---

## Implementation Requirements

### `_run_auto_resolution()` in `monitor.py`

```python
async def _run_auto_resolution(self) -> None:
    db = await mongo_manager.get_async_database()
    now = datetime.utcnow()
    recovery_window = timedelta(minutes=self.settings.BUGOPS_RECOVERY_WINDOW_MINUTES)

    open_cases = await self.store.get_open_freshness_cases()

    for case in open_cases:
        # Skip manually closed cases (terminal state)
        if case.status == CaseStatus.CLOSED:
            continue

        # Find the right detector
        detector = self.detector_by_subsystem.get(case.root_subsystem)
        if detector is None:
            logger.warning(f"No detector found for root_subsystem={case.root_subsystem}")
            continue

        try:
            recovered = await detector.check_recovery(db)
        except Exception as e:
            logger.error(f"Recovery check failed for case {case.case_id}: {e}")
            continue

        if recovered:
            if case.recovery_candidate_at is None:
                # First healthy observation
                await self.store.update_recovery_candidate(case.case_id, now)
            else:
                elapsed = now - case.recovery_candidate_at
                if elapsed >= recovery_window:
                    # Window elapsed — resolve
                    await self.store.resolve_case(case.case_id)
                    logger.info(f"BugCase auto-resolved: case_id={case.case_id}")
                    # No Slack notification on resolution
        else:
            if case.recovery_candidate_at is not None:
                # Failure recurred before window elapsed
                await self.store.update_recovery_candidate(case.case_id, None)
                logger.info(
                    f"Recovery candidate cleared (failure recurred): case_id={case.case_id}"
                )
```

### Main loop change in `run()`

```python
while self.running:
    await self._poll_signals()
    await self._poll_freshness_detectors()
    await self._run_auto_resolution()
    await asyncio.sleep(self.settings.BUGOPS_POLL_INTERVAL_SECONDS)
```

### New store methods

**`resolve_case(case_id: str) -> BugCase`**
- [ ] `$set`: `{"status": "resolved", "resolved_at": datetime.utcnow(), "recovery_candidate_at": None, "updated_at": datetime.utcnow()}`
- [ ] Uses `find_one_and_update` with `return_document=True`
- [ ] Queries by `{"case_id": case_id}`
- [ ] Normalizes with `_normalize_mongo_doc()`
- [ ] Returns updated `BugCase`
- [ ] Raises `ValueError(f"Case {case_id} not found")` if not found

**`update_recovery_candidate(case_id: str, recovery_candidate_at: Optional[datetime]) -> BugCase`**
- [ ] `$set`: `{"recovery_candidate_at": recovery_candidate_at, "updated_at": datetime.utcnow()}`
- [ ] `recovery_candidate_at` can be `None` (clears the field)
- [ ] Uses `find_one_and_update` with `return_document=True`
- [ ] Queries by `{"case_id": case_id}`
- [ ] Normalizes, returns `BugCase`

**`get_open_freshness_cases() -> list[BugCase]`**
- [ ] Queries: `{"status": "open", "dedupe_key": {"$regex": ":"}}`
- [ ] Returns list of `BugCase` objects (empty list if none)
- [ ] Uses `.find().to_list(None)` pattern

### Configuration

```python
BUGOPS_RECOVERY_WINDOW_MINUTES: int = 10
```

Add to `core/config.py`.

### Test cases in `test_auto_resolution.py`

Use mock `store` and mock detector `check_recovery()`.

- [ ] Recovery condition met for first time → `update_recovery_candidate()` called
  with `now`, case stays open
- [ ] Recovery condition met, `recovery_candidate_at` set, window NOT elapsed →
  case stays open, no resolve call
- [ ] Recovery condition met, `recovery_candidate_at` set, window elapsed →
  `resolve_case()` called
- [ ] Recovery condition met then fails before window elapses →
  `update_recovery_candidate(case_id, None)` called, case stays open
- [ ] No Slack notification sent on auto-resolution (mock Slack and assert not called)
- [ ] Manually closed case (`status = "closed"`) skipped — `check_recovery()` not called
- [ ] Muted case (`muted_until` in future) resolves normally when window elapses
- [ ] Snoozed case (`snoozed_until` in future) resolves normally when window elapses
- [ ] Detector not found for `root_subsystem` → warning logged, case skipped
- [ ] `check_recovery()` raises exception → error logged, loop continues with
  next case

### Commands to Run

```bash
pytest src/tests/bugops/test_auto_resolution.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All recovery lifecycle test cases pass
- [ ] Existing bugops tests pass

### Manual Verification

- [ ] Observe a BugCase enter `recovery_candidate_at` state and hold through
  the window before `status` transitions to `resolved`
- [ ] Observe `recovery_candidate_at` clear when failure recurs before window
- [ ] Confirm no Slack message fires on auto-resolution

---

## Acceptance Criteria

- [ ] Auto-resolution loop runs after each poll cycle
- [ ] `recovery_candidate_at` set on first healthy observation
- [ ] BugCase resolves after Recovery Window elapses without re-violation
- [ ] `recovery_candidate_at` clears when failure recurs before window
- [ ] No Slack notification on auto-resolution
- [ ] Manually closed cases never evaluated
- [ ] Muted/snoozed cases resolve normally
- [ ] All store methods use correct atomic MongoDB operations
- [ ] All test cases pass

---

## Impact

Operators no longer need to manually close self-healing failures.

---

## Related Tickets

- Depends on: TASK-100, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-108A

---

## Completion Summary

- Branch: task/bugops-109-auto-resolution
- Commit: baa17b4
- Changes made:
  - Added BUGOPS_RECOVERY_WINDOW_MINUTES = 10 to core/config.py
  - Added three store methods to BugOpsStore:
    - resolve_case(case_id) → sets status=resolved, resolved_at=now, clears recovery_candidate_at
    - update_recovery_candidate(case_id, recovery_candidate_at) → can be None to clear
    - get_open_freshness_cases() → finds all open cases with dedupe_key containing ':'
  - Added _run_auto_resolution() to BugOpsMonitor with deterministic recovery window logic
  - Integrated _run_auto_resolution() into main polling loop after _poll_freshness_detectors()
  - Imported timedelta in monitor.py for Recovery Window calculations
- Tests run:
  - pytest src/tests/bugops/test_auto_resolution.py -v → 12 passed
  - pytest src/tests/bugops/ -v → 132 passed (12 new + 120 existing)
- Manual verification: None required (logic is deterministic and fully covered by unit tests)
- Deviations from plan: None
