# BugOps Runtime Model

**Date:** 2026-05-08  
**Version:** Sprint 018  
**Audience:** Developers, on-call operators

---

## Monitor Process Architecture

BugOps runs as a separate background process (`bugops` in `Procfile`), independent of:
- FastAPI web server
- Celery worker
- Celery Beat scheduler

This isolation ensures BugOps does not depend on the scheduler it may later monitor.

---

## Polling Loop

The monitor runs an async polling loop that continuously:

```python
while True:
    for signal_source in enabled_sources:
        alerts = await signal_source.collect()
        for alert in alerts:
            case, is_new = await store.process_alert_event(alert)
            if is_new:
                await slack.send_case_notification(case)
                report = generate_case_report(case, ...)
                await store.save_case_report(case.id, report)
    sleep(BUGOPS_POLL_INTERVAL_SECONDS)
```

**Key invariants:**
1. Alerts are processed idempotently by `dedupe_key`
2. Slack notification only on new case creation (`is_new == True`)
3. Deterministic report generated and persisted on new case creation
4. Repeated alerts in the same hourly window reuse the existing case

---

## Signal Collection

Signal sources implement the `SignalSource` protocol:

```python
class SignalSource(Protocol):
    source_type: str
    
    async def collect(self) -> list[BugAlertEvent]:
        """Return list of alerts detected since last call."""
```

Each source is responsible for:
- Querying its data source (e.g., `llm_traces` collection)
- Computing metrics and thresholds
- Constructing a `BugAlertEvent` with `dedupe_key`
- Returning the list of new alerts

**Sources do not:**
- Write to `bug_*` collections (store handles this)
- Send Slack notifications (monitor handles this)
- Make assumptions about other sources

---

## Alert-to-Case Passthrough

The store processes each alert through `process_alert_event(alert)`:

```
1. Create BugAlertEvent in bug_alert_events collection
2. Extract dedupe_key from alert
3. Query bug_cases collection:
   - If open case with same dedupe_key exists → attach alert to case (no new notification)
   - If no open case exists → create new BugCase (triggers notification + report)
   - If prior case was resolved/closed → create new BugCase (new incident)
4. Return tuple (case, is_new)
```

**Critical point:** Matching is by exact `dedupe_key` only. No fuzzy matching, time-window grouping, or multi-source correlation. Future work may add these.

---

## Case Lifecycle (Manual-Only)

Cases have three statuses:

| Status | Meaning | Transition |
|--------|---------|-----------|
| `open` | Active incident, alerts being collected | Created on new dedupe_key; operator marks resolved |
| `resolved` | Operator believes incident is fixed | Manual action via future dashboard/API |
| `closed` | Incident archived | Manual action via future dashboard/API |

**No automatic transitions.** The monitor only creates cases. Operators manually resolve or close via future tooling.

---

## Slack Notification Flow

When `is_new == True` (new case created):

1. Call `slack.send_case_notification(case)`
2. Build Slack message with case metadata (severity, alert_type, metrics, etc.)
3. POST to `BUGOPS_SLACK_WEBHOOK_URL` (async, 10-second timeout)
4. On success: log notification sent
5. On failure: log error, do not crash monitor

**One-way only:** No Slack UI, commands, buttons, or acknowledgements. The notification is informational; operators manually take action.

---

## Deterministic Report Generation

When `is_new == True` (new case created):

1. Fetch all `BugAlertEvent`s attached to the new case
2. Generate Markdown report:
   - Case ID, title, status, severity, dedupe_key
   - Timestamps (created_at, latest alert)
   - Source types and alert types
   - Observed metrics from case aggregation
   - Known facts from alert metrics
   - All attached alert events with details
   - Suggested manual checks (if populated)
3. Persist report to `bug_cases.deterministic_report`

**No LLM calls.** Report is 100% deterministic, reproducible, and audit-able.

---

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `BUGOPS_ENABLED` | `false` | Enable/disable monitor at startup |
| `BUGOPS_POLL_INTERVAL_SECONDS` | `60` | Seconds between polling cycles |
| `BUGOPS_SLACK_ENABLED` | `false` | Enable/disable Slack notifications |
| `BUGOPS_SLACK_WEBHOOK_URL` | (required if enabled) | Slack incoming webhook URL |

---

## Error Handling

The monitor is designed to be fault-tolerant:

- **Signal source error:** Log error, skip that source, continue with next source
- **Store error:** Log error, do not create notification, continue polling
- **Slack error:** Log error, case still created, monitor continues
- **Unhandled error:** Log traceback, continue polling after sleep

**No crash on transient failures.** The monitor exits only on startup config errors (missing required env vars, invalid settings).

---

## Observability

BugOps logs to the standard application logger with module path `crypto_news_aggregator.bugops.*`:

**Logging patterns:**
- `bugops:monitor:startup` — Monitor started with X signal sources
- `bugops:signal_source:collect` — Source collected Y alerts
- `bugops:alert:process` — Alert created, case=NEW/EXISTING
- `bugops:case:created` — New case created with dedupe_key
- `bugops:case:attached` — Alert attached to existing case
- `bugops:slack:sent` — Notification sent successfully
- `bugops:slack:error` — Notification failed (non-critical)
- `bugops:report:generated` — Deterministic report generated and persisted

---

## Related Documents

- `00-bugops-system-overview.md` — System design and scope
- `20-bugops-data-model.md` — BugAlertEvent, BugCase schema
- `30-bugops-observability.md` — Logging and metrics
- `80-bugops-use-cases.md` — Example workflows
- `90-bugops-critiques-and-open-questions.md` — Known limitations
