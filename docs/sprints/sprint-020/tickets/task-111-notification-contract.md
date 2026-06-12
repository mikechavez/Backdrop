---
ticket_id: TASK-111
title: Implement Slack notification contract for BugCase state changes
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-111-notification-contract
effort_estimate: medium
---

# TASK-111: Implement Slack notification contract for BugCase state changes

## Problem Statement

The existing `send_case_notification()` in `slack.py` sends a Slack message for
any BugCase passed to it. Sprint 020 requires structured routing: only Critical
and High BugCases notify immediately; Medium logs digest intent; Low is silent.
Repeated observations on an open BugCase do not re-notify. Muted/snoozed BugCases
suppress delivery. This ticket replaces the current unconditional send with a
routing-aware notification function.

---

## Context

### Current `slack.py`

`send_case_notification(case: BugCase) -> bool` — sends a Slack message using
`httpx.AsyncClient`, reads webhook URL and enable flag from settings, returns
`True`/`False`. `_build_slack_message(case: BugCase) -> dict` — builds the
payload.

Both functions exist and work. This ticket modifies `slack.py` to add routing
logic and a new message format, and modifies `monitor.py` to call the new
routing-aware function instead of calling `send_case_notification()` directly.

### What triggers a notification

```
✅ New Critical BugCase created
✅ New High BugCase created
✅ Critical or High BugCase reopened (status: resolved → open)
✅ Severity escalation on existing BugCase
❌ Repeated observation attached to existing BugCase
❌ observation_count increase
❌ last_seen_at update
❌ recovery_candidate_at set or cleared
❌ Auto-resolution (status → resolved)
❌ Manual close
❌ Medium BugCase creation (log digest intent only)
❌ Low BugCase creation (log only)
```

### Notification event types

```
bugcase_created
bugcase_reopened
severity_escalated
suppression_summary   (TASK-112A)
```

### Deduplication

A BugCase creation notification is sent at most once per BugCase. Check
`notification_count > 0` on the existing BugCase before sending — if already
notified, skip unless it's an escalation or reopen.

### Throttle

Max 1 notification per BugCase per `BUGOPS_NOTIFICATION_THROTTLE_MINUTES`. Compare
`now - last_notified_at`. Escalation and reopen bypass throttle.

### Mute/snooze check

If `muted_until > now` or `snoozed_until > now`: suppress delivery, still update
`last_notified_at` (so throttle window resets), record attempt as `suppressed`.

### Slack message schema (all notification types)

The `_build_slack_message()` function must produce a payload including:

```
event_type
severity
title
bugcase_id        (was: case_id)
status
root_subsystem
affected_subsystems
summary
first_seen_at
last_seen_at
observation_count
dedupe_key
detection_type
suggested_manual_check
suppression_status    (sent | suppressed | not_applicable)
```

### Message format — BugCase created (High/Critical)

```
🚨 HIGH — Article Freshness Failure

Case:           bc_articles_1234567890
Detection:      startup
Root subsystem: articles
Affected:       signals, narratives, briefings
Summary:        No articles inserted for 42 minutes while article activity was expected.
First seen:     2026-06-11 19:21 UTC
Last seen:      2026-06-11 19:21 UTC
Observations:   1
Suggested check: Check RSS ingestion health and recent fetch attempts.
```

### Message format — Case reopened

```
🔄 CASE REOPENED

Case:         bc_articles_1234567890
Severity:     High
Root:         articles
Summary:      Article freshness recovered but failed again.
Reopen count: 1
```

### What must NOT appear in messages

- Raw logs, stack traces, large JSON payloads
- Full database records
- LLM-generated analysis
- Evidence Pack or Investigation contents

---

## Task

1. Add `route_and_send_notification()` to `slack.py` — routing-aware wrapper
2. Update `_build_slack_message()` to include the full Sprint 020 schema
3. Add `update_notification_state()` store method to `store.py`
4. Update `monitor.py` to call `route_and_send_notification()` instead of
   `send_case_notification()` directly
5. Write unit tests for routing decisions

---

## Files to Create

```text
src/tests/bugops/test_notification_routing.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/slack.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
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

### New `route_and_send_notification()` in `slack.py`

```python
async def route_and_send_notification(
    case: BugCase,
    event_type: str,
    store,   # BugOpsStore — passed in to avoid circular import
) -> str:
    """
    Route and send notification based on BugCase severity and event type.
    Returns: "sent" | "suppressed" | "skipped" | "failed"
    """
```

Routing logic:
- [ ] If `case.severity` is `AlertSeverity.CRITICAL` or `AlertSeverity.HIGH`:
  proceed to mute/snooze check
- [ ] If `case.severity` is `AlertSeverity.WARNING` (Medium): log digest intent,
  update `last_notified_at`, return `"skipped"`
- [ ] If `case.severity` is `AlertSeverity.INFO` (Low): log only, return `"skipped"`

Deduplication check (for `event_type == "bugcase_created"` only):
- [ ] If `case.notification_count > 0` and `event_type == "bugcase_created"`:
  return `"skipped"` — already notified for this case creation

Throttle check (skip for `bugcase_reopened` and `severity_escalated`):
- [ ] If `case.last_notified_at` is not None:
  `elapsed = now - case.last_notified_at`
  If `elapsed < timedelta(minutes=BUGOPS_NOTIFICATION_THROTTLE_MINUTES)` and
  `event_type not in ("bugcase_reopened", "severity_escalated")`: return `"skipped"`

Mute/snooze check:
- [ ] If `case.muted_until and case.muted_until > now`: send suppressed, update
  `last_notified_at`, return `"suppressed"`
- [ ] If `case.snoozed_until and case.snoozed_until > now`: same

Send:
- [ ] Call `send_case_notification(case)` (existing function)
- [ ] If successful: call `store.update_notification_state(case.case_id, now)`,
  return `"sent"`
- [ ] If failed: return `"failed"` (TASK-111A handles attempt persistence)

Medium digest stub:
```python
logger.info(
    f"[DIGEST-PENDING] BugCase {case.case_id} queued for digest "
    f"(severity=medium, event_type={event_type})"
)
```

### Update `_build_slack_message()` in `slack.py`

Update to include all Sprint 020 fields:
- [ ] `event_type` field
- [ ] `root_subsystem` field (from `case.root_subsystem`)
- [ ] `affected_subsystems` field (from `case.affected_subsystems`, comma-joined)
- [ ] `first_seen_at` field
- [ ] `last_seen_at` field
- [ ] `observation_count` field
- [ ] `dedupe_key` field
- [ ] `detection_type` field
- [ ] `suppression_status` field
- [ ] Match the message format examples in the Context section above
- [ ] Keep `case_id` field for backward compatibility AND add `bugcase_id` alias
- [ ] Do not add raw logs, stack traces, or JSON payloads

### New store method: `update_notification_state(case_id: str, last_notified_at: datetime) -> BugCase`

- [ ] `$set`: `{"last_notified_at": last_notified_at, "updated_at": datetime.utcnow()}`
- [ ] `$inc`: `{"notification_count": 1}`
- [ ] Uses `find_one_and_update` with `return_document=True`
- [ ] Queries by `{"case_id": case_id}`
- [ ] Returns updated `BugCase`

### Monitor change

In `_poll_freshness_detectors()`, replace:
```python
if self.settings.BUGOPS_SLACK_ENABLED:
    from .slack import send_case_notification
    await send_case_notification(new_case)
```
With:
```python
if self.settings.BUGOPS_SLACK_ENABLED:
    from .slack import route_and_send_notification
    await route_and_send_notification(new_case, "bugcase_created", self.store)
```

### Configuration

```python
BUGOPS_NOTIFICATION_THROTTLE_MINUTES: int = 60
```

### Test cases in `test_notification_routing.py`

- [ ] Critical BugCase + `bugcase_created` → `send_case_notification()` called
- [ ] High BugCase + `bugcase_created` → `send_case_notification()` called
- [ ] Medium BugCase → no `send_case_notification()`, digest intent logged
- [ ] Low BugCase → no `send_case_notification()`, log only
- [ ] High BugCase, `notification_count > 0`, `event_type="bugcase_created"` →
  `"skipped"` (already notified)
- [ ] Same BugCase within throttle window, `event_type="bugcase_created"` →
  `"skipped"`
- [ ] Same BugCase after throttle window → `send_case_notification()` called
- [ ] `event_type="bugcase_reopened"` → bypasses throttle, notification sent
- [ ] `event_type="severity_escalated"` → bypasses throttle, notification sent
- [ ] Muted BugCase (`muted_until` in future) → `"suppressed"`, `update_notification_state()` called
- [ ] Snoozed BugCase → same as muted
- [ ] Auto-resolution does NOT call `route_and_send_notification()` (test
  `_run_auto_resolution()` does not trigger notification)

### Commands to Run

```bash
pytest src/tests/bugops/test_notification_routing.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All routing test cases pass
- [ ] Existing cost-runaway detector notification tests pass unchanged
- [ ] Existing `test_slack_notification.py` tests still pass (backward compat)

### Manual Verification

- [ ] Trigger a High freshness BugCase — confirm exactly one Slack message
- [ ] Trigger repeated observations on same open BugCase — confirm no additional
  Slack messages
- [ ] Confirm no Slack fires on auto-resolution

---

## Acceptance Criteria

- [ ] Critical and High BugCases send Slack on creation (`bugcase_created`)
- [ ] Medium logs digest intent, Low logs only — no Slack for either
- [ ] `bugcase_created` notifications deduplicate on `notification_count`
- [ ] Throttle prevents re-notification within window
- [ ] Reopen and severity escalation bypass throttle
- [ ] Muted/snoozed suppress delivery but update `last_notified_at`
- [ ] Auto-resolution does not send Slack
- [ ] `update_notification_state()` added to store
- [ ] All test cases pass

---

## Related Tickets

- Depends on: TASK-100, TASK-100A, TASK-100B, TASK-100C
- Blocks: TASK-111A, TASK-112A

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
