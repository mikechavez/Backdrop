# BUG-098 — BugOps monitor crashes on undefined `send_case_notification`

## Status

Draft / Ready for implementation

## Context

During Sprint 018 Railway production rollout validation, BUG-097 was deployed to fix Mongo `ObjectId` hydration failures in BugOps.

After that fix, BugOps progressed farther through the production alert path:

```text
llm_traces signal detected
→ alert event processed
→ case path reached
→ Slack notification branch reached
```

The previous `_id` validation error is no longer the blocking issue. The monitor now fails when it reaches the Slack notification call.

Railway startup logs show the monitor successfully starting:

```text
BugOps monitor starting
Database validation passed: Using 'crypto_news'
MongoDB connection initialized
Motor client connected to MongoDB successfully
BugOps monitor running with poll interval: 300s
```

Then polling fails with:

```text
Error collecting signals from llm_traces: name 'send_case_notification' is not defined
Traceback (most recent call last):
  File "/app/src/crypto_news_aggregator/bugops/monitor.py", line 86, in _poll_signals
    await send_case_notification(case)
          ^^^^^^^^^^^^^^^^^^^^^^
NameError: name 'send_case_notification' is not defined
```

## Problem

`src/crypto_news_aggregator/bugops/monitor.py` references `send_case_notification(case)` inside `_poll_signals()`, but `send_case_notification` is not defined in module scope.

This causes the monitor to log an error every time the signal path reaches the Slack notification branch.

## Root Cause

Likely causes:

1. `send_case_notification` is not imported in `monitor.py`.
2. The Slack notification call is not correctly gated behind `BUGOPS_SLACK_ENABLED`.
3. Existing tests cover store/helper behavior but do not exercise the full monitor runtime path:

```text
signal source
→ monitor._poll_signals()
→ store.process_alert_event()
→ case returned
→ Slack branch evaluated
```

This is a runtime wiring bug, not a threshold or signal-source bug.

## Impact

BugOps cannot complete Railway production rollout validation.

Specifically, this blocks validation of:

1. Signal-to-alert processing.
2. Alert-to-case creation.
3. Dedupe behavior for repeated alerts.
4. Slack-disabled behavior.
5. Slack notification behavior after enabling Slack.

The issue also shows that the current test suite does not adequately cover the end-to-end monitor polling path.

## Expected Behavior

### When `BUGOPS_SLACK_ENABLED=false`

BugOps should:

```text
create/attach alert events and cases
not call send_case_notification()
not require Slack notification logic to execute
continue polling normally
```

### When `BUGOPS_SLACK_ENABLED=true` and `is_new=True`

BugOps should:

```text
call send_case_notification(case) exactly once for the new case
log Slack send failures
not crash the monitor if Slack send fails
```

### When `BUGOPS_SLACK_ENABLED=true` and `is_new=False`

BugOps should:

```text
attach the alert to the existing open case
not send a duplicate Slack notification
continue polling normally
```

## Required Fix

Update:

```text
src/crypto_news_aggregator/bugops/monitor.py
```

Ensure `send_case_notification` is imported if used:

```python
from crypto_news_aggregator.bugops.slack import send_case_notification
```

Ensure the Slack notification call is gated behind both:

```text
is_new == True
BUGOPS_SLACK_ENABLED == true
```

Expected shape:

```python
case, is_new = await self.store.process_alert_event(event)

if is_new and self.config.slack_enabled:
    await send_case_notification(case)
```

Use the actual config object and field names from the codebase.

If Slack send returns `False`, log it but do not crash.

If Slack send raises unexpectedly, catch/log the exception and do not crash the monitor.

Example defensive shape:

```python
case, is_new = await self.store.process_alert_event(event)

if is_new and self.config.slack_enabled:
    try:
        sent = await send_case_notification(case)
        if not sent:
            logger.warning("BugOps Slack notification was not sent for case_id=%s", case.case_id)
    except Exception:
        logger.exception("BugOps Slack notification failed for case_id=%s", case.case_id)
```

Do not call or reference Slack notification logic when Slack is disabled.

## Required Tests

Add monitor-level tests that exercise the actual `_poll_signals()` runtime path.

These tests should use a fake signal source and fake store, or mocks, but they must validate the monitor wiring rather than only the individual helper functions.

### Test 1: Slack disabled, new case

Given:

```text
BUGOPS_SLACK_ENABLED=false
signal source returns one alert event
store returns (case, is_new=True)
```

Assert:

```text
_poll_signals() does not raise NameError
send_case_notification is not called
case processing completes
```

### Test 2: Slack enabled, new case

Given:

```text
BUGOPS_SLACK_ENABLED=true
signal source returns one alert event
store returns (case, is_new=True)
```

Assert:

```text
send_case_notification(case) is called exactly once
_poll_signals() completes without crashing
```

### Test 3: Slack enabled, existing case

Given:

```text
BUGOPS_SLACK_ENABLED=true
signal source returns one alert event
store returns (case, is_new=False)
```

Assert:

```text
send_case_notification(case) is not called
_poll_signals() completes without crashing
```

### Test 4: Slack failure does not crash monitor

Given:

```text
BUGOPS_SLACK_ENABLED=true
signal source returns one alert event
store returns (case, is_new=True)
send_case_notification raises an exception or returns False
```

Assert:

```text
monitor logs the failure
_poll_signals() does not crash
polling can continue
```

## Acceptance Criteria

- BugOps monitor no longer raises:

```text
NameError: name 'send_case_notification' is not defined
```

- With `BUGOPS_SLACK_ENABLED=false`, BugOps creates or attaches cases and sends no Slack notification.
- With `BUGOPS_SLACK_ENABLED=true`, BugOps sends Slack notification only for new cases.
- Existing cases do not trigger duplicate Slack messages.
- Slack notification failure is logged but does not crash the monitor.
- Monitor-level tests cover the signal → case → Slack branch.
- Existing BugOps tests pass.
- No LLM calls are introduced.
- No Slack UI, acknowledgement, or remediation behavior is introduced.
- No Railway log ingestion or correlation engine work is introduced.

## Production Verification Steps

After deploying the fix to Railway, first validate with Slack disabled:

```text
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=false
BUGOPS_COST_5MIN_THRESHOLD_USD=0.001
BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD=0.005
BUGOPS_POLL_INTERVAL_SECONDS=300
```

Wait one poll cycle.

Expected:

```text
No NameError
No Slack message
bug_alert_events receives a new alert event
bug_cases receives or reuses an open case
```

Verify alert events:

```javascript
db.bug_alert_events.find(
  {},
  {
    _id: 1,
    alert_id: 1,
    source_type: 1,
    alert_type: 1,
    severity: 1,
    dedupe_key: 1,
    metric: 1,
    created_at: 1
  }
)
.sort({ created_at: -1 })
.limit(10)
.pretty()
```

Verify cases:

```javascript
db.bug_cases.find(
  {},
  {
    _id: 1,
    case_id: 1,
    status: 1,
    severity: 1,
    dedupe_key: 1,
    created_at: 1,
    updated_at: 1,
    alert_ids: 1
  }
)
.sort({ created_at: -1 })
.limit(10)
.pretty()
```

Then validate Slack-enabled behavior separately:

```text
BUGOPS_SLACK_ENABLED=true
BUGOPS_SLACK_WEBHOOK_URL=<Railway secret value>
```

Trigger a new hourly dedupe window or temporarily lower thresholds again.

Expected:

```text
Exactly one Slack message for a new case
No duplicate Slack message for repeated alerts with the same open-case dedupe key
```

## Testing Gap Identified

This bug indicates that BugOps needs at least one thin vertical monitor test for production rollout safety.

Required testing principle going forward:

```text
Every production BugOps bug should add a regression test at the monitor/runtime wiring level, not only at the helper or store level.
```

Minimum vertical path to preserve:

```text
fake llm_traces signal
→ monitor._poll_signals()
→ store.process_alert_event()
→ new case returned
→ Slack disabled: no send
→ no exception
```

## Notes

The recurring Redis connection log still appears during enabled-mode startup:

```text
Failed to connect to Redis: Error 111 connecting to localhost:6379. Connection refused.
```

That is likely an import-time side effect from shared app dependencies. It is not the blocking issue for this ticket unless it becomes repeated log spam or causes the monitor to exit.
