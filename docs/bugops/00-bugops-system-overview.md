# BugOps System Overview

**Date:** 2026-06-16  
**Version:** Sprint 020 (Outcome Freshness & Failure Visibility)  
**Status:** Production-ready failure detection and Slack escalation

---

## What is BugOps?

BugOps is a deterministic runtime reliability harness that detects production failures and escalates them to on-call operators for manual investigation and remediation. **Sprint 020 adds outcome freshness monitoring** — detecting when articles, signals, narratives, and briefings stop being produced at the expected rate. When production stops outputting these artifacts, BugOps automatically creates a BugCase and notifies operators via Slack.

---

## Current Scope (Sprint 020)

Sprint 020 adds comprehensive outcome freshness monitoring:

1. **Four outcome freshness detectors** (ArticleFreshness, SignalFreshness, NarrativeFreshness, BriefingFreshness)
2. **Cascade suppression** — upstream-wins deterministic processing order prevents duplicate cases for downstream failures
3. **Startup detection** — BugCases created for active failures when BugOps starts, even if production was already broken
4. **Auto-resolution with Recovery Window** — cases auto-resolve after 10 minutes of healthy operation (1 minute in dev/test)
5. **Failure recurrence handling** — if failure recurs during Recovery Window, the case stays open and countdown resets
6. **Slack notifications** — Critical and High severity cases notify immediately; Medium cases queued for digest (stubbed)
7. **Global deploy suppression** — mute all notifications during deployments with `BUGOPS_SUPPRESSED_UNTIL` timestamp
8. **Notification persistence** — all notification attempts (sent/failed/suppressed) recorded for audit trail
9. **Suppression expiry summary** — single summary message sent when suppression expires with unresolved Critical/High cases

---

## What BugOps v1 Does **Not** Do

### Autonomous Prevention
**BugOps detects and escalates; it does not autonomously prevent failures.** There is no remediation automation, shutdown triggers, or database writes to production app collections. Cases are manual-only lifecycle: an operator reads the Slack notification and takes action.

### Evidence & Investigation
**Evidence collection and LLM-driven investigation is deferred to Sprint 021.** Sprint 020 produces BugCases with raw outcome data. Sprint 021 will add automatic Railway log collection, evidence packs, and structured investigation analysis.

### Ticket Drafting
**Automatic ticket generation is deferred to Sprint 022.** Future work will support investigation-to-ticket conversion and human approval workflows.

### Interactive Slack
**Slack is outbound webhook only, not interactive UI.** One-way notifications are sent when a case is created or reopened. There are no slash commands, buttons, modals, acknowledgement, or resolution actions. Interactive Slack is a future feature.

### Runtime Exception Monitoring
**Railway log ingestion and runtime exception monitoring are deferred.** Sprint 020 focuses on outcome freshness; runtime errors (RuntimeError, WorkerFailure, SchedulerFailure) are separate signal sources for future implementation.

### Dedicated Flapping Detection
**Recovery Window handles failure oscillation.** Sprint 020 does not implement dedicated flapping detection; the Recovery Window mechanism prevents repeated open/resolve cycles naturally.

---

## Outcome Freshness Detection & Cascade Suppression

**Dependency Graph (v1.0):**
```
scheduler → ingestion → articles → signals → narratives → briefings
```

When a freshness detector observes a failure:

1. **Upstream check** — Is there already an open case at any upstream node?
   - YES → attach this observation to upstream case, no new notification
   - NO → proceed to next check

2. **Dedupe check** — Is there an open case with the same dedupe_key?
   - YES → attach observation to existing case, no new notification
   - NO → proceed to next check

3. **Create new case** — Create BugCase with the failure details
   - Set `detection_type` = "startup" (first poll) or "runtime" (subsequent polls)
   - Populate `blast_radius` (downstream subsystems) from DependencyGraph
   - Set `observation_count` = 1, `first_seen_at`, `last_seen_at`
   - Send Slack notification if Critical or High severity
   - Enter Recovery Window countdown

**Recovery Window:**
When a detector observes its recovery condition is met:
- Set `recovery_candidate_at` to current timestamp
- If subsystem remains healthy for full Recovery Window (10 min production, 1 min dev), auto-resolve
- If failure recurs during window, clear `recovery_candidate_at` and reset countdown
- Auto-resolution does not send Slack notification

---

## Key Data Models

### BugCase (Sprint 020 Extended)
Container for related observations, grouped by outcome freshness detector.

**Subsystem tracking:**
- `root_subsystem`: string (canonical enum: scheduler, ingestion, articles, signals, narratives, briefings, worker, database)
- `affected_subsystems`: list[str] (canonical subsystem values affected downstream)
- `blast_radius`: list[str] (all reachable subsystems from root via DependencyGraph)

**Observation tracking:**
- `observation_count`: integer, default 1 (incremented on repeated observations)
- `first_seen_at`: timestamp (when case created)
- `last_seen_at`: timestamp (when last observation attached)

**Recovery and lifecycle:**
- `recovery_candidate_at`: timestamp | null (set when recovery condition met, cleared if failure recurs)
- `detection_type`: enum: "startup" (detected on first poll) | "runtime" (detected on subsequent polls)
- `reopen_count`: integer, default 0 (incremented each time case reopens)
- `status`: enum (`open`, `resolved`, `closed`)
- `created_at`: timestamp

**Operator tooling:**
- `muted_until`: timestamp | null (suppresses notifications, does not block auto-resolution)
- `snoozed_until`: timestamp | null (suppresses notifications, does not block auto-resolution)

**Detection metadata:**
- `dedupe_key`: string (detector-specific: `article_freshness:articles`, `signal_freshness:signals`, etc.)
- `suggested_manual_check`: string (operator guidance specific to detector type)
- `severity`: enum (`high`, `critical`) — deterministically assigned by detector type in Sprint 020

### NotificationAttempt
Audit trail of every notification delivery attempt.

**Fields:**
- `notification_id`: string (unique UUID)
- `bugcase_id`: ObjectId (reference to BugCase)
- `event_type`: enum (bugcase_created, bugcase_reopened, severity_escalated, suppression_summary)
- `channel`: string ("slack")
- `status`: enum (sent, failed, suppressed, skipped)
- `attempted_at`: timestamp
- `error_type`: string | null (exception class name if failed)
- `error_message`: string | null (exception message if failed)
- `suppressed_reason`: string | null ("deploy_suppression", "muted", "snoozed")

---

## Canonical Subsystem Enum

All BugOps components use canonical subsystem names:

```
scheduler    — Scheduled task runner (Celery Beat)
ingestion    — RSS article ingestion layer
articles     — Article production (inserts to articles collection)
signals      — Signal generation worker (signal_scores collection)
narratives   — Narrative refresh job (narratives collection)
briefings    — Daily briefing generation (daily_briefings collection)
worker       — Reserved for future worker failure detection
database     — Reserved for future database failure detection
```

---

## Signal Sources in Sprint 020

### ArticleFreshness
Detects when articles stop being inserted at the expected rate.

- **Failure condition:** No article with `created_at` within 60-min window + 60-sec tolerance, AND RSS fetch activity observed recently, AND historical time-of-day analysis shows articles were typically produced during this time window
- **Recovery condition:** Fresh article inserted within freshness window
- **Dedupe key:** `article_freshness:articles`
- **Severity:** High
- **Root subsystem:** articles

### SignalFreshness
Detects when signals stop being generated from fresh articles.

- **Failure condition:** Fresh articles exist (created within 60 min) but no fresh signals (last_updated within 90 min)
- **Recovery condition:** Fresh signal generated within freshness window
- **Dedupe key:** `signal_freshness:signals`
- **Severity:** High
- **Root subsystem:** signals

### NarrativeFreshness
Detects when narrative summaries stop being generated from fresh signals.

- **Failure condition:** Fresh signals exist (last_updated within 120 min) but no fresh narrative update (last_summary_generated_at within 120 min)
- **Recovery condition:** Fresh narrative summary generated within freshness window
- **Dedupe key:** `narrative_freshness:narratives`
- **Severity:** High
- **Root subsystem:** narratives

### BriefingFreshness
Detects when daily briefings fail to generate on schedule.

- **Failure condition:** Briefing generation window has elapsed (8 AM/8 PM EST ±30 min grace period) but no briefing inserted, AND fresh narratives exist as input
- **Recovery condition:** New briefing inserted within expected window
- **Dedupe key:** `briefing_freshness:briefings`
- **Severity:** High
- **Root subsystem:** briefings

### LLMTraceCostSignalSource (Pre-existing)
Detects cost-runaway thresholds in LLM traces:
- **Critical:** Last 5-minute spend ≥ $0.25
- **Warning:** Projected hourly spend ≥ $1.00
- **Dedupe key:** `llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}`

---

## Monitor Process

BugOps runs as a separate `bugops` process in `Procfile`, independent of FastAPI, Celery worker, or Celery Beat.

**Polling loop (Sprint 020):**
1. Poll all freshness detectors (first poll: `detection_type="startup"`, subsequent: `detection_type="runtime"`)
2. For each detector failure observed:
   a. Check for open upstream BugCase (DependencyGraph)
   b. If found → attach observation to upstream case, stop
   c. Check for open BugCase with same dedupe_key
   d. If found → attach observation to existing case, stop
   e. Create new BugCase, send Slack notification if Critical/High
3. Run auto-resolution checks for all open freshness cases
   - If recovery condition met and Recovery Window elapsed → resolve case
   - If failure recurs during window → clear recovery_candidate_at, stay open
4. Check for suppression expiry and send summary if needed
5. Sleep and repeat

**Configuration:**
- `BUGOPS_ENABLED` — enable/disable monitor
- `BUGOPS_POLL_INTERVAL_SECONDS` — polling cycle interval (default: 60)
- `BUGOPS_SLACK_ENABLED` — enable Slack notifications
- `BUGOPS_SLACK_WEBHOOK_URL` — Slack incoming webhook
- `BUGOPS_SUPPRESSED_UNTIL` — ISO-8601 timestamp for global deployment suppression (empty = no suppression)
- `BUGOPS_RECOVERY_WINDOW_MINUTES` — time required for healthy operation before auto-resolution (default: 10 prod, 1 dev/test)
- `BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES` — ArticleFreshness window (default: 60)
- `BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES` — SignalFreshness window (default: 90)
- `BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES` — NarrativeFreshness window (default: 120)
- `BUGOPS_COST_5MIN_THRESHOLD_USD`, `BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD` — cost thresholds

---

## Related Documents

- `10-bugops-runtime-model.md` — Monitor process, polling loop, cascade suppression
- `20-bugops-data-model.md` — BugCase and NotificationAttempt schemas
- `30-bugops-observability.md` — Logging and structured observability
- `80-bugops-use-cases.md` — Example workflows and scenarios
- `90-bugops-critiques-and-open-questions.md` — Known limitations and future work
- `../../sprints/sprint-020/sprint-020-bugops-outcome-freshness.md` — Detailed Sprint 020 specification
