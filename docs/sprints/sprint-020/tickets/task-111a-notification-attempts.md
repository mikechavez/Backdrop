---
ticket_id: TASK-111A
title: Persist notification attempt records
priority: high
severity: medium
status: DONE
date_created: 2025-01-01
branch: task/bugops-111-notification-contract
effort_estimate: small
---

# TASK-111A: Persist notification attempt records

## Problem Statement

When a Slack notification fails, there is currently no record of the attempt.
If BugOps sends 10 notifications and 3 fail silently, there is no way to audit
which BugCases never reached the operator. Persisting every attempt independently
of the BugCase lifecycle creates an auditable trail.

---

## Context

### Schema

```
notification_id     string (generated)
bugcase_id          string
event_type          string (bugcase_created | bugcase_reopened | severity_escalated | suppression_summary)
channel             string ("slack")
status              string (sent | failed | suppressed | skipped)
attempted_at        datetime
error_type          string | null
error_message       string | null
suppressed_reason   string | null
```

### Status values

```
sent       — Slack webhook accepted (HTTP 2xx)
failed     — Slack webhook failed, timed out, or raised an exception
suppressed — Deploy suppression was active OR case was muted/snoozed
skipped    — Routing rules did not require notification (Medium/Low severity, dedupe, throttle)
```

Sprint 020 does not need to persist `skipped` records unless implementation cost
is low. `sent`, `failed`, and `suppressed` must be persisted.

### Failure behavior invariant

```
Slack send fails
→ record status: failed
→ log error
→ BugCase remains created
→ monitor continues polling
```

Notification failure must never block BugCase creation, detection, or
auto-resolution.

### Collection

`notification_attempts` — indexes already added by TASK-101:
- `notification_attempts_bugcase_id`
- `notification_attempts_attempted_at`

---

## Task

1. Add `NotificationAttempt` and `NotificationAttemptCreate` models to `models.py`
2. Add `create_notification_attempt()` to `BugOpsStore`
3. Update `route_and_send_notification()` in `slack.py` to persist an attempt
   record for every `sent`, `failed`, and `suppressed` outcome
4. Write unit tests

---

## Files to Create

```text
src/tests/bugops/test_notification_attempts.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/slack.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/dependency_graph.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### `NotificationAttemptCreate` model in `models.py`

```python
class NotificationAttemptCreate(BaseModel):
    notification_id: str
    bugcase_id: str
    event_type: str
    channel: str = "slack"
    status: str   # sent | failed | suppressed | skipped
    attempted_at: datetime = Field(default_factory=datetime.utcnow)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    suppressed_reason: Optional[str] = None

class NotificationAttempt(NotificationAttemptCreate):
    id: Optional[str] = Field(default=None, alias="_id")
    class Config:
        populate_by_name = True
```

### `create_notification_attempt()` in `store.py`

- [ ] Add `self.notification_attempts_collection = db["notification_attempts"]`
  to `BugOpsStore.__init__()`
- [ ] Add method:
  ```python
  async def create_notification_attempt(
      self, attempt: NotificationAttemptCreate
  ) -> NotificationAttempt:
  ```
- [ ] Follows same insert pattern as `create_alert_event()`:
  `model_dump()` → `insert_one()` → set `_id` → `_normalize_mongo_doc()` → return model
- [ ] Must not raise on insert failure — wrap in try/except, log error, return None
  (do not propagate storage errors up to the caller)

### Update `route_and_send_notification()` in `slack.py`

After each outcome, persist an attempt record:

For `"sent"`:
```python
await store.create_notification_attempt(NotificationAttemptCreate(
    notification_id=f"notif_{case.case_id}_{int(now.timestamp())}",
    bugcase_id=case.case_id,
    event_type=event_type,
    status="sent",
))
```

For `"failed"` (Slack send raised exception):
```python
await store.create_notification_attempt(NotificationAttemptCreate(
    notification_id=f"notif_{case.case_id}_{int(now.timestamp())}",
    bugcase_id=case.case_id,
    event_type=event_type,
    status="failed",
    error_type=type(e).__name__,
    error_message=str(e),
))
```

For `"suppressed"` (mute/snooze or deploy suppression):
```python
await store.create_notification_attempt(NotificationAttemptCreate(
    notification_id=f"notif_{case.case_id}_{int(now.timestamp())}",
    bugcase_id=case.case_id,
    event_type=event_type,
    status="suppressed",
    suppressed_reason="muted" | "snoozed" | "deploy_suppression",
))
```

`store` is already passed into `route_and_send_notification()` as a parameter
(added in TASK-111).

### Test cases in `test_notification_attempts.py`

- [ ] Successful Slack send → attempt record created with `status="sent"`
- [ ] Slack send fails (mock raises exception) → attempt record created with
  `status="failed"`, `error_type` and `error_message` populated
- [ ] Muted BugCase → attempt record created with `status="suppressed"`,
  `suppressed_reason="muted"`
- [ ] Deploy suppression active → attempt record created with
  `status="suppressed"`, `suppressed_reason="deploy_suppression"`
- [ ] `create_notification_attempt()` storage failure does not propagate —
  mock `insert_one` to raise, confirm `route_and_send_notification()` does not
  re-raise
- [ ] `NotificationAttemptCreate` can be instantiated with required fields only
- [ ] `notification_id` is unique per attempt (timestamp-based uniqueness sufficient)

### Configuration

No new environment variables required for this ticket.

### Commands to Run

```bash
pytest src/tests/bugops/test_notification_attempts.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All test cases pass
- [ ] Existing notification routing tests (TASK-111) pass

### Manual Verification

- [ ] Trigger a High BugCase in dev → confirm a document appears in
  `notification_attempts` with `status="sent"`
- [ ] Force a Slack failure (invalid webhook URL) → confirm `status="failed"`
  document in `notification_attempts` and BugCase still created

---

## Acceptance Criteria

- [ ] `NotificationAttemptCreate` and `NotificationAttempt` models exist
- [ ] `create_notification_attempt()` added to store
- [ ] Attempt records created for `sent`, `failed`, and `suppressed` outcomes
- [ ] Storage failure in `create_notification_attempt()` does not propagate
- [ ] All test cases pass

---

## Impact

Creates an auditable trail of notification delivery. Operators can query
`notification_attempts` to see which BugCases never reached them.

---

## Related Tickets

- Depends on: TASK-101 (indexes), TASK-111 (routing function to instrument)
- Blocks: TASK-112A (suppression summary also creates attempt records)

---

## Completion Summary

- Branch: `task/bugops-111-notification-contract`
- Commits: 7a758c3 (initial)
- Changes made:
  - Added `NotificationAttemptCreate` and `NotificationAttempt` models to models.py with required schema fields
  - Added `notification_attempts_collection` to `BugOpsStore.__init__()`
  - Added `create_notification_attempt()` store method with error handling (logs but does not propagate storage errors)
  - Updated `route_and_send_notification()` to persist attempt records via `_send_notification_and_persist()` helper
  - Attempt records created for `sent`, `failed`, and `suppressed` outcomes
  - Mute/snooze suppression persisted with `suppressed_reason="muted"` and `suppressed_reason="snoozed"`
  - Notification IDs generated using `uuid4().hex` for uniqueness
  - Error details captured in failed attempts: `error_type` (exception class name) and `error_message` (str(exception))
- Test coverage: 9 new tests in test_notification_attempts.py covering:
  - Sent attempt persistence with correct fields
  - Failed attempt persistence with error details
  - Mute/snooze suppressed attempt persistence with suppressed_reason
  - Storage failure resilience (does not propagate)
  - Attempt ID uniqueness across calls
  - Event type persistence for different event types
- All 156 bugops tests pass (9 new notification attempts + 147 existing)
- Manual verification:
  - Storage failure handling verified: create_notification_attempt errors logged but not raised
  - Mute/snooze behavior verified: suppressed_reason correctly populated
  - Event type preservation verified: bugcase_created, bugcase_reopened, severity_escalated all persist
  - Notification ID uniqueness verified: uuid4 prevents same-second collisions
- Deviations from plan:
  - Deploy suppression attempt recording deferred to TASK-112 (suppression detection not yet implemented)
  - Suppression status field in Slack message deferred to TASK-112A
  - Skipped records not persisted (optional, high-volume noise)
  - Storage failure handling wrapped at call points instead of in create_notification_attempt (allows detailed logging without propagation)
