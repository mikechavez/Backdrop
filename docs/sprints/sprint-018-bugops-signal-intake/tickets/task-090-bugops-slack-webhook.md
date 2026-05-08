---
ticket_id: TASK-090
title: One-Way BugOps Slack Webhook Notification
priority: high
severity: medium
status: OPEN
date_created: 2026-05-08
branch: feature/bugops-signal-intake
effort_estimate: small
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

- [ ] Sends one-way Slack webhook message for new case.
- [ ] Does not send Slack when `BUGOPS_SLACK_ENABLED=false`.
- [ ] Handles missing webhook URL without crashing monitor.
- [ ] Handles Slack HTTP failure without crashing monitor.
- [ ] Does not implement any Slack UI or interactive actions.

---

## Impact

Provides the first operator-facing BugOps alert path without introducing interactive workflow complexity.

---

## Related Tickets

- FEATURE-056
- FEATURE-057
- FEATURE-059
