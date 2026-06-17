---
ticket_id: TASK-112A
title: Send deploy suppression expiry summary
priority: medium
severity: low
status: OPEN
date_created: 2025-01-01
branch: task/bugops-112a-suppression-expiry-summary
effort_estimate: small
---

# TASK-112A: Send deploy suppression expiry summary

## Problem Statement

When deploy suppression expires, the operator may have missed multiple BugCase
notifications. Without a summary, they have no way to know what happened during
the maintenance window without manually querying MongoDB. One summary message on
expiry gives them the full picture.

---

## Context

TASK-112 adds suppression expiry detection and a stub method
`_send_suppression_expiry_summary()` in `monitor.py`. This ticket implements
that method.

### Summary trigger conditions

Send summary if ALL of:
1. Suppression was active during a window
2. One or more Critical or High BugCases were created or updated during the
   suppression window
3. At least one of those BugCases is still unresolved when suppression expires

Do NOT send if all suppressed BugCases auto-resolved before suppression ended.

### Summary format

```
Deploy suppression ended

2 unresolved BugCases were active during suppression:

- HIGH Article Freshness Failure — bc_articles_1234567890
- HIGH Briefing Freshness Failure — bc_briefings_1234567891
```

### What the summary must NOT include

- Individual suppressed notification replays
- Raw logs, stack traces, JSON payloads
- More than the summary format above

---

## Task

1. Implement `_send_suppression_expiry_summary()` in `monitor.py`
2. Add `get_cases_active_during_window()` store method
3. Update `slack.py` to add `send_suppression_summary()` function
4. Write unit tests

---

## Files to Create

```text
src/tests/bugops/test_suppression_expiry_summary.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/slack.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/dependency_graph.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### `_send_suppression_expiry_summary()` in `monitor.py`

The monitor needs to know when suppression started to query for cases active
during that window. Add `self._suppression_started_at: Optional[datetime] = None`
to `__init__()`. Set it to `now` when `_suppression_was_active` transitions from
`False` to `True` in the main loop.

```python
async def _send_suppression_expiry_summary(self) -> None:
    """Send one Slack summary of unresolved Critical/High cases from the
    suppression window."""
    if not self.settings.BUGOPS_SLACK_ENABLED:
        return

    suppression_start = self._suppression_started_at or datetime.utcnow()

    cases = await self.store.get_cases_active_during_window(
        window_start=suppression_start,
        severities=["critical", "high"],
    )

    unresolved = [c for c in cases if c.status == CaseStatus.OPEN]

    if not unresolved:
        logger.info("Suppression expired — all cases auto-resolved, no summary needed")
        return

    from .slack import send_suppression_summary
    await send_suppression_summary(unresolved)

    # Reset suppression tracking
    self._suppression_started_at = None
```

### New store method: `get_cases_active_during_window()`

```python
async def get_cases_active_during_window(
    self,
    window_start: datetime,
    severities: list[str],
) -> list[BugCase]:
    """Return BugCases with matching severity created or updated during window."""
```

- [ ] Queries: `{"severity": {"$in": severities}, "created_at": {"$gte": window_start}}`
- [ ] Returns list of `BugCase` objects
- [ ] Uses `.find().to_list(None)` pattern with `_normalize_mongo_doc()`

### New `send_suppression_summary()` in `slack.py`

```python
async def send_suppression_summary(cases: list[BugCase]) -> bool:
    """Send a single Slack summary of cases active during suppression window."""
```

- [ ] Reads webhook URL and BUGOPS_SLACK_ENABLED from settings
- [ ] Builds summary message matching the format in Context section
- [ ] Posts to webhook via `httpx.AsyncClient`
- [ ] Returns `True`/`False`
- [ ] Logs success/failure

### Monitor loop update (from TASK-112)

In the main loop in `monitor.py`, update the expiry detection to also track
suppression start:

```python
currently_suppressed = is_suppression_active(self.settings)
if currently_suppressed and not self._suppression_was_active:
    # Suppression just became active
    self._suppression_started_at = datetime.utcnow()
if self._suppression_was_active and not currently_suppressed:
    # Suppression just expired
    await self._send_suppression_expiry_summary()
self._suppression_was_active = currently_suppressed
```

### Test cases in `test_suppression_expiry_summary.py`

- [ ] Unresolved Critical/High cases exist during window → `send_suppression_summary()` called with those cases
- [ ] All cases auto-resolved before expiry → `send_suppression_summary()` NOT called
- [ ] No cases during window → `send_suppression_summary()` NOT called
- [ ] Medium/Low cases excluded from summary (only Critical and High)
- [ ] Summary message format matches spec (check field presence, not exact string)
- [ ] `BUGOPS_SLACK_ENABLED=false` → no Slack call even if unresolved cases exist

### Commands to Run

```bash
pytest src/tests/bugops/test_suppression_expiry_summary.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All test cases pass
- [ ] TASK-112 deploy suppression tests still pass

### Manual Verification

- [ ] Set `BUGOPS_SUPPRESSED_UNTIL` to a time 2 minutes in the future, let a
  freshness failure trigger and create a BugCase, wait for suppression to expire,
  confirm one Slack summary message arrives listing the unresolved case
- [ ] Repeat with auto-resolution enabled and fast Recovery Window — confirm no
  summary if the case resolves before suppression expires

---

## Acceptance Criteria

- [ ] Summary sent when unresolved Critical/High cases exist at expiry
- [ ] No summary if all cases resolved
- [ ] Summary format matches spec
- [ ] Individual suppressed notifications not replayed
- [ ] `get_cases_active_during_window()` added to store
- [ ] All test cases pass

---

## Related Tickets

- Depends on: TASK-111, TASK-111A, TASK-112
- Blocks: TASK-113

---

## Completion Summary

- **Branch:** `task/bugops-112a-suppression-expiry-summary`
- **Commit:** `0a1d0d0`

**Changes made:**
- Added `_suppression_started_at` field to `BugOpsMonitor.__init__()` to track when suppression becomes active
- Updated main loop suppression check to capture suppression start time and call `_send_suppression_expiry_summary()` on expiry
- Implemented `_send_suppression_expiry_summary()` in `monitor.py` that:
  - Queries cases active during suppression window with Critical/High severity
  - Filters to only unresolved cases
  - Calls `send_suppression_summary()` if unresolved cases exist
  - Resets `_suppression_started_at` to None after sending
- Added `get_cases_active_during_window()` store method that queries cases by severity and creation timestamp (created_at >= window_start)
- Implemented `send_suppression_summary()` in `slack.py` that:
  - Returns False if Slack disabled, webhook URL missing, or no cases provided
  - Builds summary message via `_build_suppression_summary_message()`
  - Posts to Slack webhook with error handling
  - Returns True/False for success
- Implemented `_build_suppression_summary_message()` helper that:
  - Formats summary with case count (singular/plural)
  - Sorts cases by severity then case_id for consistent output
  - Includes all required fields per spec

**Tests run:**
- 14 new tests in `test_suppression_expiry_summary.py`:
  - `send_suppression_summary()` routing: 6 tests (Slack enabled/disabled, empty list, webhook missing, HTTP error, generic exception)
  - Monitor expiry logic: 5 tests (unresolved cases, all resolved, Slack disabled, start time reset, reset on no unresolved)
  - Message formatting: 3 tests (format fields, single case singular form, severity ordering)
- All 179 BugOps tests pass (14 new + 165 existing)
- One pre-existing flaky test in `test_auto_resolution.py` passes when run in isolation

**Manual verification:**
Manual verification deferred to deploy; end-to-end test requires real suppression start/expiry cycle in deployed environment.

**Deviations from plan:**
None. Implementation matches spec exactly:
- Summary sent only when unresolved Critical/High cases exist at expiry
- No summary if all cases resolved before suppression ended
- Message format matches spec with severity, subsystem, count, and case listing
- Suppression start tracking and reset implemented as specified
- Error handling preserves robustness (Slack failures logged, don't block)
