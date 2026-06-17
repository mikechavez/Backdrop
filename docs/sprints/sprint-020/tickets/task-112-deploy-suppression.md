---
ticket_id: TASK-112
title: Implement global deploy suppression
priority: medium
severity: low
status: OPEN
date_created: 2025-01-01
branch: task/bugops-112-deploy-suppression
effort_estimate: small
---

# TASK-112: Implement global deploy suppression

## Problem Statement

During planned deploys, BugOps will correctly detect transient failures as the
system restarts. Without suppression, every deploy generates a stream of BugCase
notifications. Operators need a way to suppress notifications for a known
maintenance window without losing case visibility or auto-resolution.

---

## Context

### Suppression mechanism

A single environment variable:

```
BUGOPS_SUPPRESSED_UNTIL=<ISO-8601 timestamp>
```

If current time is before `BUGOPS_SUPPRESSED_UNTIL`, suppression is active.
If the variable is empty, invalid, or in the past, suppression is inactive.
No separate `BUGOPS_SUPPRESSION_ACTIVE` boolean. The timestamp IS the gate.

This replaces the two-variable design (`BUGOPS_SUPPRESSION_ACTIVE` + 
`BUGOPS_SUPPRESSION_EXPIRES_AT`) from the original ticket.

### Suppression invariant

```
BugCases are created normally ✅
BugCases are updated normally ✅
Slack notifications are not sent ✅
notification_attempts recorded as suppressed ✅ (TASK-111A)
auto-resolution runs normally ✅
reopen logic runs normally ✅
```

### Individual BugCase mute/snooze

`muted_until` and `snoozed_until` on BugCase are already checked in
`route_and_send_notification()` (TASK-111). This ticket adds the global
suppression check that runs before the per-case check.

The `mute_case()` and `snooze_case()` store methods are implemented here for
use by future operator tooling (CLI or UI). No API endpoints. No Slack UI.

### Suppression expiry summary

When suppression expires, send one Slack summary for unresolved Critical and High
BugCases active during the window. This is TASK-112A — not implemented here.
This ticket only detects expiry and hands off to TASK-112A.

---

## Task

1. Add `BUGOPS_SUPPRESSED_UNTIL` to `core/config.py`
2. Add suppression check to `route_and_send_notification()` in `slack.py`
3. Add suppression state tracking to `BugOpsMonitor` — detect when suppression
   transitions from active to inactive
4. Add `mute_case()` and `snooze_case()` store methods
5. Write unit tests

---

## Files to Create

```text
src/tests/bugops/test_deploy_suppression.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/slack.py
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

### Configuration

```python
BUGOPS_SUPPRESSED_UNTIL: str = ""
# ISO-8601 timestamp. If current time is before this value, notifications
# are suppressed. Empty string = suppression inactive.
```

### Suppression check helper in `slack.py` or `monitor.py`

```python
def is_suppression_active(settings) -> bool:
    """Return True if global deploy suppression is currently active."""
    raw = settings.BUGOPS_SUPPRESSED_UNTIL
    if not raw:
        return False
    try:
        from datetime import datetime, timezone
        suppressed_until = datetime.fromisoformat(raw)
        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if suppressed_until.tzinfo is None:
            suppressed_until = suppressed_until.replace(tzinfo=timezone.utc)
        return now < suppressed_until
    except (ValueError, TypeError):
        return False  # Invalid timestamp = suppression inactive
```

### Update `route_and_send_notification()` in `slack.py`

Add global suppression check as the FIRST check, before mute/snooze:

```python
if is_suppression_active(settings):
    logger.info(
        f"[SUPPRESSED] Notification suppressed during maintenance window: "
        f"case_id={case.case_id}"
    )
    # Still update last_notified_at so throttle resets correctly
    await store.update_notification_state(case.case_id, now)
    # Persist attempt record (TASK-111A)
    await store.create_notification_attempt(NotificationAttemptCreate(
        notification_id=f"notif_{case.case_id}_{int(now.timestamp())}",
        bugcase_id=case.case_id,
        event_type=event_type,
        status="suppressed",
        suppressed_reason="deploy_suppression",
    ))
    return "suppressed"
```

### Suppression expiry tracking in `monitor.py`

Add `self._suppression_was_active: bool = False` to `__init__()`.

In the main loop, check each cycle:
```python
currently_suppressed = is_suppression_active(self.settings)
if self._suppression_was_active and not currently_suppressed:
    # Suppression just expired — trigger TASK-112A summary
    await self._send_suppression_expiry_summary()
self._suppression_was_active = currently_suppressed
```

`_send_suppression_expiry_summary()` is a stub returning immediately until TASK-112A.

### New store methods

**`mute_case(case_id: str, muted_until: datetime) -> BugCase`**
- [ ] `$set`: `{"muted_until": muted_until, "updated_at": datetime.utcnow()}`
- [ ] `find_one_and_update` with `return_document=True`, query by `{"case_id": case_id}`
- [ ] Returns `BugCase`

**`snooze_case(case_id: str, snoozed_until: datetime) -> BugCase`**
- [ ] `$set`: `{"snoozed_until": snoozed_until, "updated_at": datetime.utcnow()}`
- [ ] Same pattern as `mute_case()`
- [ ] Returns `BugCase`

No API endpoints. These are called by operator tooling only.

### Test cases in `test_deploy_suppression.py`

- [ ] `BUGOPS_SUPPRESSED_UNTIL` set to future timestamp → `is_suppression_active()` returns `True`
- [ ] `BUGOPS_SUPPRESSED_UNTIL` set to past timestamp → returns `False`
- [ ] `BUGOPS_SUPPRESSED_UNTIL` empty string → returns `False`
- [ ] `BUGOPS_SUPPRESSED_UNTIL` invalid string → returns `False` (no exception)
- [ ] Suppression active → notification suppressed, BugCase still created
- [ ] Suppression active → auto-resolution still runs (mock `_run_auto_resolution()`
  and confirm it's called even when suppressed)
- [ ] Suppression expires (was active, now inactive) → `_send_suppression_expiry_summary()` called
- [ ] `mute_case()` sets `muted_until` correctly
- [ ] `snooze_case()` sets `snoozed_until` correctly

### Commands to Run

```bash
pytest src/tests/bugops/test_deploy_suppression.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All test cases pass
- [ ] Existing notification routing tests (TASK-111) pass

### Manual Verification

- [ ] Set `BUGOPS_SUPPRESSED_UNTIL` to a timestamp 5 minutes in the future in Railway,
  trigger a detection condition — confirm BugCase created but no Slack fires
- [ ] Let the timestamp expire — confirm suppression deactivates on next cycle

---

## Acceptance Criteria

- [ ] `BUGOPS_SUPPRESSED_UNTIL` is the single suppression control (no boolean flag)
- [ ] Global suppression suppresses notifications without blocking BugCase creation
  or auto-resolution
- [ ] Invalid or empty `BUGOPS_SUPPRESSED_UNTIL` → suppression inactive (no crash)
- [ ] Expiry detection triggers `_send_suppression_expiry_summary()` stub
- [ ] `mute_case()` and `snooze_case()` store methods exist
- [ ] All test cases pass

---

## Impact

Eliminates notification noise during planned deploys without losing case visibility.

---

## Related Tickets

- Depends on: TASK-100, TASK-111, TASK-111A
- Blocks: TASK-112A

---

## Completion Summary

- Branch: task/bugops-111-notification-contract
- Commit: 231c445
- Changes made:
  - Added BUGOPS_SUPPRESSED_UNTIL to core/config.py (empty string default)
  - Implemented is_suppression_active() helper in slack.py with timezone-aware comparison
  - Added global suppression check as FIRST check in route_and_send_notification() before mute/snooze
  - Suppressed notifications update last_notified_at, persist attempt record with status=suppressed and suppressed_reason=deploy_suppression
  - Added _suppression_was_active flag to BugOpsMonitor.__init__()
  - Integrated suppression expiry detection in main polling loop
  - Added _send_suppression_expiry_summary() stub method (deferred to TASK-112A)
  - Added mute_case(case_id, muted_until) and snooze_case(case_id, snoozed_until) to BugOpsStore
- Tests run: poetry run pytest src/tests/bugops/ -v → 166 passed (10 new + 156 existing)
- Test coverage:
  - Suppression check logic: future/past/empty/invalid/None timestamps
  - Notification routing: suppression active suppresses with status=suppressed, persists attempt
  - Suppression expiry detection: transition from active→inactive triggers summary stub
  - Mute/snooze operations: both store methods set fields correctly
  - Auto-resolution proceeds normally during suppression (mocked verification)
- Manual verification: Deferred to Railway deploy; suppression timestamp can be set in BUGOPS_SUPPRESSED_UNTIL env var
- Deviations from plan: None
