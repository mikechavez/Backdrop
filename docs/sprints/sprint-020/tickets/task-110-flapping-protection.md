---
ticket_id: TASK-110
title: Implement flapping protection
priority: medium
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-110-flapping-protection
effort_estimate: small
---

# TASK-110: Implement flapping protection

## Problem Statement

A BugCase that oscillates rapidly between healthy and failed states will produce a stream of `recovery_candidate_at` set/clear cycles. Without flapping protection this generates noise and prevents auto-resolution from ever stabilizing. Flapping protection detects this pattern, suspends auto-resolution, and escalates to the operator.

---

## Context

TASK-109 already increments `flap_count` and clears `recovery_candidate_at` when a failure recurs before the Recovery Window elapses. This ticket adds the threshold check on top of that: when `flap_count` exceeds the configurable threshold within the flap window, the BugCase is marked as flapping, auto-resolution is suspended, and a single Slack notification is sent.

The `flap_count` and `flapping` fields are already on the BugCase model (added in TASK-100).

Only an operator action can clear the `flapping` flag. Auto-resolution does not run while `flapping = True`.

---

## Task

1. Add flapping threshold check to the auto-resolution loop in `monitor.py`
2. Add `mark_case_flapping()` store method
3. Send a single Slack notification when flapping is detected
4. Block auto-resolution for BugCases with `flapping = True`
5. Write unit tests for flapping detection and escalation

---

## Files to Create

```text
src/tests/bugops/test_flapping.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
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

### Flapping threshold check (in auto-resolution loop, after `increment_flap_count()`)

- [ ] After incrementing `flap_count`, retrieve the updated BugCase
- [ ] If `flap_count >= BUGOPS_FLAP_COUNT_THRESHOLD` AND `flapping` is currently `False`: call `store.mark_case_flapping(case_id)` and send flapping notification
- [ ] If `flapping` is already `True`: skip the threshold check (already escalated)

### Flap window enforcement

- [ ] `flap_count` tracks total oscillations — for Sprint 020, no time-window decay is implemented. The threshold is evaluated against the cumulative count.
- [ ] Time-window decay (resetting `flap_count` after `BUGOPS_FLAP_WINDOW_MINUTES` of stability) is deferred. Record this as a known limitation in the completion summary.

### Auto-resolution block

- [ ] In the auto-resolution loop, skip any BugCase where `flapping = True`
- [ ] Log a structured message when a flapping case is skipped: `"Skipping auto-resolution: case is flapping"`

### New store method: `mark_case_flapping(case_id: str) -> BugCase`

- [ ] Sets `flapping = True`
- [ ] Sets `updated_at = datetime.utcnow()`
- [ ] Does not change `status`
- [ ] Returns updated BugCase

### Flapping notification

- [ ] Send a Slack notification with message indicating the BugCase requires manual review due to flapping
- [ ] Include: `case_id`, `root_subsystem`, `flap_count`, current `severity`
- [ ] Send only once (the `mark_case_flapping()` call is the gate — it only fires when transitioning from `False` to `True`)

### Configuration

```text
BUGOPS_FLAP_COUNT_THRESHOLD=3
BUGOPS_FLAP_WINDOW_MINUTES=30
```

Add to `src/crypto_news_aggregator/core/config.py`. Note: `BUGOPS_FLAP_WINDOW_MINUTES` is defined for future use — it is not enforced in Sprint 020.

### Test cases required

- [ ] `flap_count` reaches threshold → `flapping` set to `True`, notification sent
- [ ] `flapping = True` → auto-resolution loop skips the case
- [ ] Flapping notification is sent exactly once (not re-sent on subsequent cycles)
- [ ] `flap_count` below threshold → no flapping, auto-resolution continues normally

### Commands to Run

```bash
pytest src/tests/bugops/test_flapping.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All test cases pass
- [ ] Existing auto-resolution tests from TASK-109 still pass

### Manual Verification

- [ ] Force `flap_count` to threshold via repeated oscillation in dev — confirm `flapping` is set and Slack notification fires once
- [ ] Confirm auto-resolution loop skips the flapping case on subsequent cycles

---

## Acceptance Criteria

- [ ] Flapping is detected when `flap_count >= BUGOPS_FLAP_COUNT_THRESHOLD`
- [ ] `flapping = True` blocks auto-resolution
- [ ] Flapping Slack notification sent exactly once per flapping transition
- [ ] `mark_case_flapping()` is idempotent (calling it on an already-flapping case is safe)
- [ ] All test cases pass

---

## Impact

Prevents auto-resolution noise loops and escalates unstable BugCases to operator attention.

---

## Related Tickets

- Depends on: TASK-109

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
