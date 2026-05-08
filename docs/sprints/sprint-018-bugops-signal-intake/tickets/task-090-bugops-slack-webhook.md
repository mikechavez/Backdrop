---
ticket_id: TASK-090
title: One-Way BugOps Slack Webhook Notification
priority: high
severity: medium
status: COMPLETE
date_created: 2026-05-08
date_completed: 2026-05-08
branch: feature/bugops-signal-intake
effort_estimate: small
actual_effort: small
commits:
  - a79c94c
  - 85b9e48
---

# TASK-090: One-Way BugOps Slack Webhook Notification

## Problem Statement

BugOps needs to notify the operator when a new case is created. There is no Slack UI yet, so Sprint 018 should only send outbound webhook messages.

---

## Task

Create a BugOps-only Slack notification helper.

### Files to Create/Modify

```text
src/crypto_news_aggregator/bugops/slack.py
src/crypto_news_aggregator/bugops/monitor.py
tests/bugops/test_slack_notification.py
```

### Config

Use these settings from `core/config.py`:

```text
BUGOPS_SLACK_ENABLED
BUGOPS_SLACK_WEBHOOK_URL
```

### Implementation Requirements

- Send a POST request to `BUGOPS_SLACK_WEBHOOK_URL` only when `BUGOPS_SLACK_ENABLED=true`.
- Use `httpx.AsyncClient` or equivalent async HTTP client.
- Slack message must include:
  - case_id
  - severity
  - alert_type
  - title
  - summary
  - observed metric values
  - created_at
  - source_type
  - suggested manual check
- Failure to send Slack must not crash the monitor loop.
- Log Slack send failures as warnings/errors.

### Out of Scope

Do not implement:

- Slack slash commands.
- Slack buttons.
- Slack modals.
- Slack acknowledgement.
- Slack resolve/close actions.
- Slack Q&A.
- Threaded Slack conversations.

---

## Verification

Run unit tests with mocked HTTP client.

```bash
pytest tests/bugops/test_slack_notification.py
```

Manual test with webhook configured:

```bash
BUGOPS_ENABLED=true BUGOPS_SLACK_ENABLED=true BUGOPS_SLACK_WEBHOOK_URL="..." python -m crypto_news_aggregator.bugops.monitor
```

---

## Acceptance Criteria

- [x] Sends one-way Slack webhook message for new case.
- [x] Does not send Slack when `BUGOPS_SLACK_ENABLED=false`.
- [x] Handles missing webhook URL without crashing monitor.
- [x] Handles Slack HTTP failure without crashing monitor.
- [x] Does not implement any Slack UI or interactive actions.

---

## Implementation Summary

### Key Changes

1. **New Module**: `src/crypto_news_aggregator/bugops/slack.py`
   - `send_case_notification(case)` — Async helper to send Slack webhook POST
   - `_build_slack_message(case)` — Formats case into Slack attachment payload
   - Severity color-coding: info (#36a64f), warning (#ffa500), high (#ff6600), critical (#ff0000)
   - Graceful error handling: logs failures, returns False, doesn't crash monitor

2. **Model Updates**: `src/crypto_news_aggregator/bugops/models.py`
   - Added `alert_type: str` field to BugCaseCreate/BugCase
   - Added `suggested_manual_check: Optional[str]` field to BugCaseCreate/BugCase
   - Both fields now available in database for tracking and messaging

3. **Store Updates**: `src/crypto_news_aggregator/bugops/store.py`
   - Changed `process_alert_event()` return type from `BugCase` to `tuple[BugCase, bool]`
   - Returns `(case, is_new)` — is_new is True only when a new case is created
   - Prevents duplicate notifications when repeated alerts attach to existing cases

4. **Monitor Integration**: `src/crypto_news_aggregator/bugops/monitor.py`
   - Imported `send_case_notification` from slack module
   - Modified `_poll_signals()` to check `is_new` flag before sending Slack
   - Only sends notification on new case creation, not on every alert

5. **Slack Message Payload**
   - Includes all required fields: case_id, severity, alert_type, source_type, metrics, suggested_manual_check, created_at
   - Color-coded by severity
   - Optional fields (metrics, suggested_manual_check) only included if populated
   - Message format: Slack attachment with title, summary, and formatted field values

### Test Coverage

- **18 unit tests** in `tests/bugops/test_slack_notification.py`
- Message formatting tests (color mapping, field inclusion, optional field handling)
- Notification send tests (success, disabled, missing webhook, HTTP errors)
- Monitor behavior tests (new case vs. existing case)
- All tests pass with mocked HTTP client

---

## Impact

Provides the first operator-facing BugOps alert path without introducing interactive workflow complexity.

---

## Related Tickets

- FEATURE-056
- FEATURE-057
- FEATURE-059
