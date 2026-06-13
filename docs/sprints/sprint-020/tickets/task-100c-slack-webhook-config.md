---
ticket_id: TASK-100C
title: Configure Slack webhook in Railway for BugOps
priority: high
severity: medium
status: ✅ DONE
date_created: 2025-01-01
completed: 2026-06-12
branch: (none — deploy config only, no code changes)
effort_estimate: xs
---

# TASK-100C: Configure Slack webhook in Railway for BugOps

## Problem Statement

`slack.py` is fully implemented and `send_case_notification()` works correctly,
but the Slack webhook URL and enable flags have never been set in Railway. BugOps
has also never been enabled in production (`BUGOPS_ENABLED` defaults to `false`).
Sprint 020 depends on Slack delivery working when the first freshness BugCase fires.
This ticket configures the missing environment variables before Sprint 020 goes live.

---

## Context

From code inspection:
- `slack.py` exists at `src/crypto_news_aggregator/bugops/slack.py`
- `send_case_notification()` is fully implemented — uses `httpx` to POST to a
  webhook URL, has error handling, formats Slack-compatible JSON attachments
- Three environment variables gate delivery:
  - `BUGOPS_ENABLED` — defaults to `false`; the monitor exits immediately if false
  - `BUGOPS_SLACK_ENABLED` — defaults to `false`; `send_case_notification()` returns
    early if false
  - `BUGOPS_SLACK_WEBHOOK_URL` — defaults to `""`; `send_case_notification()` logs
    a warning and returns False if empty
- The existing cost-runaway detector has never sent a Slack message in production
  because all three variables have been at their defaults

This is deploy config work only. No code changes required.

---

## Task

1. Create an incoming webhook in Slack
2. Set the three environment variables in Railway
3. Verify delivery with a manual test

---

## Files to Create

```text
(none)
```

---

## Files to Modify

```text
(none — Railway environment variables only)
```

---

## Do Not Modify

```text
(anything)
```

---

## Implementation Requirements

### Step 1 — Create Slack incoming webhook

- [ ] Go to https://api.slack.com/apps → select or create a Slack app for Backdrop
- [ ] Enable Incoming Webhooks
- [ ] Add a new webhook to the desired channel (e.g. `#backdrop-alerts` or
  `#bugops`)
- [ ] Copy the webhook URL (format: `https://hooks.slack.com/services/...`)

### Step 2 — Set Railway environment variables

In the Railway project for Backdrop, set:

- [ ] `BUGOPS_SLACK_WEBHOOK_URL` = `<webhook URL from Step 1>`
- [ ] `BUGOPS_SLACK_ENABLED` = `true`
- [ ] `BUGOPS_ENABLED` = `true`

Note: Setting `BUGOPS_ENABLED=true` activates the full BugOps monitor including
the existing cost-runaway detector. Verify the cost-runaway thresholds are
acceptable before flipping this on in production:
- `BUGOPS_COST_5MIN_THRESHOLD_USD` defaults to `0.25`
- `BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD` defaults to `1.00`

At $0.54/day production spend these thresholds are safe, but confirm before deploy.

### Step 3 — Verify delivery

- [ ] After deploying with the new env vars, check Railway logs for:
  `"BugOps monitor running with poll interval: 300s"` — confirms monitor started
- [ ] Trigger a test notification by temporarily lowering
  `BUGOPS_COST_5MIN_THRESHOLD_USD` to `0.001` for one poll cycle, then restore it
  — OR — confirm the log line `"Slack notification sent for case"` appears when
  a real threshold is hit
- [ ] Confirm the Slack message arrives in the configured channel

### Configuration

Environment variables set in Railway (not in codebase):

```
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=true
BUGOPS_SLACK_WEBHOOK_URL=<webhook URL>
```

---

## Verification

### Automated Verification

None — this is deploy config only.

### Manual Verification

- [ ] Railway logs show `"BugOps monitor running"` after deploy
- [ ] At least one Slack message received in the configured channel
- [ ] Railway logs do not show `"BUGOPS_SLACK_WEBHOOK_URL not configured"`

---

## Acceptance Criteria

- [ ] Slack incoming webhook created and URL recorded
- [ ] All three env vars set in Railway
- [ ] At least one successful Slack delivery confirmed
- [ ] Railway logs confirm monitor is running

---

## Impact

Unblocks Sprint 020 end-to-end Slack delivery. Without this ticket, all
notification logic in TASK-111 is implemented but never delivers. Do this
ticket before or alongside Sprint 020 code work — do not wait until the end.

---

## Related Tickets

- Blocks: TASK-111 (Slack contract depends on delivery working)
- No code dependencies — can be done independently of all other tickets

---

## Completion Summary

- Webhook channel: `#backdrop-bugops`
- Railway deploy timestamp: 2026-06-12
- Test message confirmed: Yes — threshold reduction test triggered real BugCase and Slack delivery
- Deviations from plan: None

### Configuration Applied

Environment variables set in Railway:
```env
BUGOPS_ENABLED=true
BUGOPS_SLACK_ENABLED=true
BUGOPS_SLACK_WEBHOOK_URL=<configured>
```

### Slack Configuration

- Existing Slack app reused (no new app creation required)
- Existing webhook reused and verified operational
- Channel: `#backdrop-bugops` (renamed from `#all-backdrop`)
- Webhook delivery: functional

### Deployment Verification

Railway logs confirmed:
```text
BugOps monitor running with poll interval: 300s
```

### End-to-End Test

Temporary cost threshold reduction triggered a real BugOps alert:
- ✅ BugCase created successfully
- ✅ Slack formatting correct
- ✅ Webhook delivery successful
- ✅ Channel routing verified

All acceptance criteria met.
