---
ticket_id: TASK-065
title: Add observability to update_one call in narrative backfill loop
priority: medium
severity: medium
status: OPEN
date_created: 2026-04-14
branch: task/task-065-narrative-backfill-observability
effort_estimate: S (< 1 hour)
---

# TASK-065: Add observability to `update_one` call in narrative backfill loop

## Problem Statement
The `update_one` call in the narrative backfill loop (~line 1187 of `briefing_agent.py`) has no logging before execution, no check of `matched_count` or `modified_count`, and no exception handling. If the write fails silently, there is no way to detect it. This was identified during the BUG-074 investigation and is not the root cause of the pipeline stall, but leaves a blind spot in write path observability.

---

## Task
In the narrative backfill loop in `briefing_agent.py` (~line 1187):

1. Add a `logger.debug()` call before `update_one` executes, logging the narrative ID and the fields being written
2. Capture the result of `update_one` and check `result.modified_count` — log a warning if `modified_count == 0` (document not found or no change made)
3. Wrap the `update_one` call in a `try/except` block with `logger.error()` on failure

---

## Verification
1. Trigger a pipeline run that exercises the backfill loop
2. Confirm debug logs appear in output showing narrative IDs being written
3. Simulate a failed write (e.g., temporarily pass a bad document ID) and confirm the warning/error is logged correctly

---

## Acceptance Criteria
- [ ] `logger.debug()` fires before each `update_one` call with narrative ID and fields
- [ ] `result.modified_count` is checked; a warning is logged if `== 0`
- [ ] `update_one` is wrapped in `try/except` with `logger.error()` on exception
- [ ] No change to existing write behavior — observability only

---

## Impact
Closes a silent failure mode in the narrative write path. If a future bug causes backfill writes to fail, it will now be detectable in logs rather than requiring direct MongoDB inspection.

---

## Related Tickets
- BUG-074 (discovered during investigation)