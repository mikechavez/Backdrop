---
ticket_id: TASK-111
title: Update notification routing for Sprint 020
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-111-notification-routing
effort_estimate: medium
---

# TASK-111: Update notification routing for Sprint 020

## Problem Statement

Sprint 018's notification logic sends a Slack message for every new BugAlertEvent. Sprint 020 requires a more structured routing model: deduplication prevents repeated alerts for the same open BugCase, throttling prevents notification storms, and routing varies by severity. Without this, the four freshness detectors will produce noisy alerts on every polling cycle.

---

## Context

Notification routing in Sprint 020 is driven by BugCase state changes, not raw detector observations. The routing decision happens in `monitor.py` or a dedicated notification module, using the `last_notified_at` and `notification_count` fields added to BugCase in TASK-100.

**Medium (Digest) and Low (Stored only) are stubbed in this sprint.** Implement the routing decision and log the intent; actual digest batching and aggregation are deferred.

`muted_until` and `snoozed_until` on BugCase suppress notifications but do not block BugCase creation or auto-resolution.

The existing `slack.py` module is modified, not replaced.

---

## Task

1. Implement severity-based routing logic (Critical/High → immediate Slack, Medium → log digest intent, Low → log only)
2. Implement deduplication: no re-notification for repeated observations unless escalation conditions met
3. Implement throttle: at most one notification per BugCase per throttle window (except escalation)
4. Implement mute/snooze check before sending any notification
5. Implement reopen notification (ignores throttle)
6. Write unit tests for routing decisions

---

## Files to Create

```text
src/tests/bugops/test_notification_routing.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/slack.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/dependency_graph.py
```

---

## Implementation Requirements

### Routing table

| Severity | Trigger | Action |
|---|---|---|
| Critical | BugCase created | Immediate Slack |
| Critical | Severity escalation | Immediate Slack (bypass throttle) |
| High | BugCase created | Immediate Slack |
| High | Severity escalation | Immediate Slack (bypass throttle) |
| Medium | BugCase created | Log digest intent (stub) |
| Low | BugCase created | Log only, no notification |

### Deduplication rules — do NOT re-notify if

- [ ] An open BugCase with the same `dedupe_key` already exists (i.e. this is an observation attachment, not a new case)
- [ ] UNLESS any of these escalation conditions are true:
  - Severity increased on the existing BugCase
  - A new subsystem was added to `affected_subsystems`
  - The BugCase reopened after resolution

### Throttle

- [ ] At most one notification per BugCase per `BUGOPS_NOTIFICATION_THROTTLE_MINUTES` window
- [ ] Compare `now - last_notified_at` before sending; if within window, skip
- [ ] Escalation events (severity increase, new subsystem, reopen) bypass the throttle
- [ ] Flapping notification (TASK-110) bypasses the throttle

### Mute/snooze check

- [ ] Before sending any notification, check `muted_until` and `snoozed_until`
- [ ] If `muted_until > now` or `snoozed_until > now`: log suppressed notification, do not send
- [ ] Still update `last_notified_at` even when suppressed, so throttle window resets correctly — this prevents a burst of notifications when mute expires

### Reopen notification

- [ ] When a resolved BugCase reopens (status transitions from `resolved` to `open`): send notification regardless of throttle state
- [ ] Use current BugCase severity for the reopen message

### Notification sent — update BugCase

- [ ] After sending (or deciding to send) a notification: update `last_notified_at = now` and increment `notification_count` via a store method

### New store method: `update_notification_state(case_id, last_notified_at) -> BugCase`

- [ ] Sets `last_notified_at` to provided value
- [ ] Uses `$inc` to increment `notification_count` by 1
- [ ] Returns updated BugCase

### Slack message content (for new BugCase notifications)

- [ ] `case_id`
- [ ] `severity`
- [ ] `root_subsystem`
- [ ] `blast_radius` (list of affected downstream subsystems)
- [ ] `first_seen_at`
- [ ] One-line summary (e.g. "Article ingestion stalled — no articles in last 60 minutes")

### Medium digest stub

- [ ] When severity is Medium: log `"[DIGEST-PENDING] BugCase {case_id} would be included in digest"` at INFO level
- [ ] Do not send Slack
- [ ] Still update `last_notified_at`

### Configuration

```text
BUGOPS_NOTIFICATION_THROTTLE_MINUTES=60
```

Add to `src/crypto_news_aggregator/core/config.py`.

### Test cases required

- [ ] Critical BugCase created → Slack sent
- [ ] High BugCase created → Slack sent
- [ ] Medium BugCase created → no Slack, digest intent logged
- [ ] Low BugCase created → no Slack, log only
- [ ] Same dedupe_key observation on open case → no notification
- [ ] Same dedupe_key observation but severity increased → notification sent (throttle bypassed)
- [ ] Same BugCase within throttle window → no notification
- [ ] Same BugCase after throttle window → notification sent
- [ ] Muted BugCase → notification suppressed, `last_notified_at` still updated
- [ ] Snoozed BugCase → notification suppressed, `last_notified_at` still updated
- [ ] Reopen notification sent regardless of throttle state

### Commands to Run

```bash
pytest src/tests/bugops/test_notification_routing.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All routing test cases pass
- [ ] Existing cost-runaway detector notification behavior is unchanged

### Manual Verification

- [ ] Trigger a High freshness BugCase — confirm exactly one Slack message
- [ ] Trigger repeated observations on the same open BugCase — confirm no additional Slack messages
- [ ] Mute a BugCase and trigger a new observation — confirm no Slack

---

## Acceptance Criteria

- [ ] Critical and High BugCases send immediate Slack on creation
- [ ] Medium logs digest intent, Low logs only — no Slack for either
- [ ] Repeated observations on an open BugCase do not re-notify
- [ ] Escalation events (severity increase, new subsystem, reopen) bypass deduplication and throttle
- [ ] Throttle prevents more than one notification per BugCase per throttle window
- [ ] Muted/snoozed BugCases suppress notification but still update `last_notified_at`
- [ ] `notification_count` increments correctly
- [ ] All test cases pass

---

## Impact

Transforms alert behavior from noisy (one Slack per detector observation) to signal-rich (one Slack per new failure, silence for repeated observations of the same open issue).

---

## Related Tickets

- Depends on: TASK-100
- Can run in parallel with TASK-103 through TASK-107

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
