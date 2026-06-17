# BugOps Runtime Model

**Date:** 2026-06-16  
**Version:** Sprint 020  
**Audience:** Developers, on-call operators

---

## Monitor Process Architecture

BugOps runs as a separate background process (`bugops` in `Procfile`), independent of:
- FastAPI web server
- Celery worker
- Celery Beat scheduler

This isolation ensures BugOps does not depend on the scheduler it may later monitor.

---

## Polling Loop (Sprint 020)

The monitor runs an async polling loop that continuously:

```python
while True:
    # Poll freshness detectors with cascade suppression
    _poll_freshness_detectors()
    
    # Run auto-resolution checks
    _run_auto_resolution()
    
    # Check for suppression expiry and send summary
    _check_suppression_expiry()
    
    sleep(BUGOPS_POLL_INTERVAL_SECONDS)
```

**Freshness detector polling:**
```python
def _poll_freshness_detectors():
    for detector in [article, signal, narrative, briefing]:
        try:
            if detector.check_failure():
                # Step 1: Check upstream for open case
                upstream = graph.get_upstream_nodes(detector.root_subsystem)
                for node in upstream:
                    if open_case := find_open_case_by_root_subsystem(node):
                        attach_observation_to_case(open_case)
                        return
                
                # Step 2: Check for dedupe_key match
                if open_case := find_open_case_by_dedupe_key(detector.dedupe_key):
                    attach_observation_to_case(open_case)
                    return
                
                # Step 3: Create new case
                case = create_case_direct(
                    root_subsystem=detector.root_subsystem,
                    blast_radius=graph.get_downstream_nodes(detector.root_subsystem),
                    detection_type="startup" if is_first_poll else "runtime",
                    dedupe_key=detector.dedupe_key,
                    severity=detector.severity
                )
                if case.severity in ["critical", "high"]:
                    send_slack_notification(case)
        except Exception as e:
            log.error(f"Detector {detector} failed", exc_info=e)
    
    is_first_poll = False
```

**Key invariants:**
1. Cascade suppression is deterministic: upstream check → dedupe check → create (order never varies)
2. Slack notifications only on case creation, case reopen, or severity escalation
3. Each detector runs in isolation; a detector error does not halt polling
4. Startup detection creates BugCases for active failures (no healthy baseline required)
5. Repeated observations attach to existing cases via dedupe_key or upstream match

---

## Freshness Detector Interface

Freshness detectors implement the detector protocol:

```python
class FreshnessDetector(Protocol):
    root_subsystem: str (canonical subsystem enum value)
    dedupe_key: str
    severity: AlertSeverity
    suggested_manual_check: str
    
    def check_failure(self) -> bool:
        """Return True if failure condition is currently met."""
    
    def check_recovery(self) -> bool:
        """Return True if recovery condition is currently met."""
```

Each detector is responsible for:
- Querying its data source (e.g., `articles` collection via `created_at` field)
- Computing freshness windows and timestamps
- Distinguishing legitimate idle from broken via the five-part definition
- Returning boolean failure/recovery conditions

**Detectors do not:**
- Write to `bug_*` collections (monitor/store handles this)
- Make assumptions about other detectors (cascade suppression is monitor's responsibility)
- Produce BugCases directly (monitor creates them with proper metadata)

---

## Cascade Suppression (Sprint 020)

When a freshness detector observes its failure condition:

```
1. Check for open upstream BugCase
   - Walk DependencyGraph toward root (scheduler)
   - Return first open case found at any upstream node
   - If found: attach observation to upstream case, stop (no new notification)

2. Check for open BugCase with same dedupe_key
   - Query by dedupe_key (e.g., "signal_freshness:signals")
   - If found: attach observation to existing case, stop (no new notification)

3. Create new BugCase
   - Set root_subsystem, blast_radius (downstream subsystems)
   - Set detection_type = "startup" (first poll) or "runtime" (subsequent)
   - Set dedupe_key, severity, first_seen_at, last_seen_at
   - Send Slack notification if severity is Critical or High
```

**Upstream-wins is unconditional.** If articles are broken, signal, narrative, and briefing detectors all report failures, but only the ArticleFreshness case is created. Signal/Narrative/Briefing observations attach to the ArticleFreshness case, which shows `affected_subsystems: [signals, narratives, briefings]`.

**Idempotency:** Repeated observations of the same open failure condition attach to the existing case via dedupe_key match (or upstream match), preventing duplicate cases and duplicate notifications.

---

## Case Lifecycle (Sprint 020)

Cases have four statuses:

| Status | Meaning | Transition |
|--------|---------|-----------|
| `open` | Active incident, failure condition observed | Created by detector or observation attached |
| `resolved` | Detector's recovery condition met for Recovery Window duration | Auto-resolved by monitor after healthy countdown |
| `closed` | Operator manually archived case | Manual action via operator tooling (future) |
| `reopened` | Case that resolved then failed again | Auto-set by monitor when failure recurs after resolution |

**Auto-resolution (new in Sprint 020):**
1. When detector observes recovery condition is met, set `recovery_candidate_at` = now
2. If subsystem remains healthy (recovery condition stays true) for Recovery Window duration → auto-resolve
3. If failure recurs during window → clear `recovery_candidate_at`, stay open, reset countdown
4. Manually closed cases do not auto-resolve

**Mute/Snooze:** Operators can set `muted_until` or `snoozed_until` timestamps to suppress notifications without blocking auto-resolution.

---

## Slack Notification Contract (Sprint 020)

**Notify on:**
- New Critical or High BugCase created
- Critical or High BugCase reopened
- Severity escalation
- Suppression expiry summary (if unresolved Critical/High cases existed during suppression)

**Do not notify on:**
- Repeated observations attached to open case
- Cascade-suppressed downstream observations
- Observation count increase, last_seen_at updates
- recovery_candidate_at set or cleared
- Auto-resolution
- Manual close
- Low or Medium severity BugCase creation

**Deduplication:**
- `bugcase_created`: at most once per case (checks notification_count)
- `bugcase_reopened`: always immediate (no throttle)
- `severity_escalated`: always immediate (no throttle)
- `suppression_summary`: at most once per suppression window

**Throttle:** Max 1 notification per case per hour (except reopen/escalation which are immediate)

**Message fields (all notifications):**
- Case ID, severity, status, root_subsystem, affected_subsystems
- Dedupe key, detection type, first_seen_at, last_seen_at, observation_count
- Suggested manual check, suppression status

**Slack send failure:** Log error, record attempt with status=failed, continue monitoring (do not crash)

---

## Configuration (Sprint 020)

| Environment Variable | Default | Purpose |
|---|---|---|
| `BUGOPS_ENABLED` | `false` | Enable/disable monitor at startup |
| `BUGOPS_POLL_INTERVAL_SECONDS` | `60` | Seconds between polling cycles |
| `BUGOPS_SLACK_ENABLED` | `false` | Enable/disable Slack notifications |
| `BUGOPS_SLACK_WEBHOOK_URL` | (required if enabled) | Slack incoming webhook URL |
| `BUGOPS_SUPPRESSED_UNTIL` | (empty) | ISO-8601 timestamp; if current time < this, suppress notifications |
| `BUGOPS_RECOVERY_WINDOW_MINUTES` | `10` (prod), `1` (dev/test) | Minutes of healthy operation before auto-resolve |
| `BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES` | `60` | ArticleFreshness window |
| `BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES` | `90` | SignalFreshness window |
| `BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES` | `120` | NarrativeFreshness window |
| `BUGOPS_BRIEFING_MORNING_HOUR_EST` | `8` | Hour (EST) for morning briefing generation |
| `BUGOPS_BRIEFING_EVENING_HOUR_EST` | `20` | Hour (EST) for evening briefing generation |
| `BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES` | `30` | Grace period after scheduled hour |
| `BUGOPS_COST_5MIN_THRESHOLD_USD` | `0.25` | LLMTraceCost critical threshold |
| `BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD` | `1.00` | LLMTraceCost warning threshold |

---

## Error Handling

The monitor is designed to be fault-tolerant:

- **Signal source error:** Log error, skip that source, continue with next source
- **Store error:** Log error, do not create notification, continue polling
- **Slack error:** Log error, case still created, monitor continues
- **Unhandled error:** Log traceback, continue polling after sleep

**No crash on transient failures.** The monitor exits only on startup config errors (missing required env vars, invalid settings).

---

## Observability (Sprint 020)

BugOps logs to the standard application logger with module path `crypto_news_aggregator.bugops.*`:

**Structured logging patterns:**
- `bugops:monitor:startup` — Monitor started with freshness detectors enabled
- `bugops:detector:run` — Detector poll started/completed (detector_name, success, observation_attached)
- `bugops:cascade:upstream_match` — Observation attached to upstream case (upstream_subsystem)
- `bugops:cascade:dedupe_match` — Observation attached to existing case (dedupe_key)
- `bugops:cascade:new_case` — New BugCase created (root_subsystem, detection_type, severity)
- `bugops:recovery:candidate_set` — recovery_candidate_at set for case
- `bugops:recovery:candidate_cleared` — recovery_candidate_at cleared (failure recurred)
- `bugops:recovery:resolved` — Case auto-resolved after Recovery Window
- `bugops:slack:sent` — Notification sent successfully (event_type, severity)
- `bugops:slack:failed` — Notification failed (error_type, retry status)
- `bugops:slack:suppressed` — Notification suppressed (suppression_reason)
- `bugops:suppression:expiry` — Suppression window expired, summary sent/skipped
- `bugops:detector:error` — Detector exception caught and isolated (detector_name, error_type)

**Error handling:** Detector errors are isolated (try/catch), logged, and do not halt the monitor.

---

## Related Documents

- `00-bugops-system-overview.md` — System design and scope
- `20-bugops-data-model.md` — BugAlertEvent, BugCase schema
- `30-bugops-observability.md` — Logging and metrics
- `80-bugops-use-cases.md` — Example workflows
- `90-bugops-critiques-and-open-questions.md` — Known limitations
