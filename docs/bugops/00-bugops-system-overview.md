# BugOps System Overview

**Date:** 2026-05-08  
**Version:** Sprint 018 (Foundation)  
**Status:** Early-stage foundation, not production monitoring

---

## What is BugOps?

BugOps is a deterministic runtime reliability harness that detects cost and performance anomalies in production and escalates them to on-call operators for manual investigation and remediation.

**Sprint 018 is not trying to solve BugOps. It is trying to prove the smallest end-to-end signal path while preserving the seam for additional signal sources.**

---

## Sprint 018 Scope

Sprint 018 builds the first working BugOps signal pipeline:

1. **Read one structured source** (`llm_traces`)
2. **Normalize a cost-runaway signal** into `bug_alert_events`
3. **Create a thin `bug_cases` record** with exact `dedupe_key` passthrough (not a correlation engine)
4. **Send a one-way Slack webhook notification** to alert operators
5. **Generate a minimal deterministic case report** from stored data only
6. **Validate the `SignalSource` interface** against real Railway log output (spike, not implementation)

---

## What BugOps v1 Does **Not** Do

### Autonomous Prevention
**BugOps v1 detects and escalates; it does not autonomously prevent cost cascades.** There is no remediation automation, shutdown triggers, or database writes to production app collections. Cases are manual-only lifecycle: an operator reads the Slack notification and takes action.

### LLM Synthesis
**LLM synthesis is deferred.** Sprint 018 generates deterministic reports from stored alert metrics. Future sprints may add LLM-driven Q&A, ticket drafting, or root-cause analysis.

### Interactive Slack
**Slack in Sprint 018 is outbound webhook only, not Slack UI.** One-way notifications are sent when a new case is created. There are no slash commands, buttons, modals, acknowledgement, or resolution actions. Slack UI is a future feature.

### Multi-Source Correlation
**Alert-to-case flow is exact `dedupe_key` passthrough, not a correlation engine.** Each signal source produces alerts with a dedupe key. Cases are created or reused by exact key match only. Future correlation logic (fuzzy matching, time-window grouping, multi-source reasoning) is out of scope for v1.

### Case Lifecycle
**Case lifecycle is manual-only.** No automatic closure, state transition workflows, or SLA tracking. Operators manually mark cases as resolved or closed. Future automation may add scheduled monitors, retry-storm detection, or design-review escalation.

---

## Signal Flow

```
┌─────────────────────────┐
│  Signal Sources         │
│  (LLMTraces, Railway…)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  BugAlertEvent          │
│  (normalized alert)     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  BugCase                │
│  (dedupe_key → case)    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Slack Notification +   │
│  Deterministic Report   │
└─────────────────────────┘
```

---

## Key Data Models

### BugAlertEvent
Normalized alert from any signal source.

**Required fields:**
- `source_type`: string (e.g., `llm_traces`, `railway_logs`)
- `source_id`: string (e.g., `llm_traces:cost_runaway`, `railway_logs:mongo_autoreconnect`)
- `alert_type`: string (e.g., `cost_runaway`, `db_connection_error`)
- `severity`: enum (`info`, `warning`, `high`, `critical`)
- `dedupe_key`: string (e.g., `llm_traces:cost_runaway:2026-05-08:14`)
- `metrics`: dict (source-specific metrics, e.g., spend rates, duration)
- `created_at`: timestamp

**Optional fields:**
- `correlation_keys`: list (future multi-source correlation)
- `raw_sample_ref`: string (reference to original log/trace)

### BugCase
Container for related alerts. One case per unique `dedupe_key` per status.

**Required fields:**
- `dedupe_key`: string (matches alert dedupe_key)
- `source_type`: string
- `alert_type`: string
- `severity`: enum
- `status`: enum (`open`, `resolved`, `closed`)
- `created_at`: timestamp

**Optional fields:**
- `metrics`: dict (aggregated from attached alerts)
- `suggested_manual_check`: string (operator guidance)
- `deterministic_report`: string (Markdown report)

---

## Cost-Runaway Dedupe Key Format

Hourly bucketing prevents one perpetual case while grouping repeated checks in the same incident window:

```
llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}
```

Example: `llm_traces:cost_runaway:2026-05-08:14`

---

## Signal Sources in Sprint 018

### LLMTraceCostSignalSource (Implemented)
Reads `llm_traces` collection. Detects cost-runaway thresholds:
- **Critical:** Last 5-minute spend ≥ $0.25
- **Warning:** Projected hourly spend ≥ $1.00

Dedupe key: `llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}`

### RailwayLogSignalSource (Data-Shape Spike Only)
**Railway log intake is not implemented yet.** Sprint 018 only captures real sample output and validates the `SignalSource` interface. Full ingestion is deferred.

Why a spike? Railway log streaming requires:
- Railway API token (not CLI) for non-interactive use
- Multiline stack trace reconstruction
- Duplicate suppression (same error floods 4× per minute)
- Multiple timestamp formats and bare platform messages

See `docs/bugops/railway-log-data-shape.md` for findings.

---

## Monitor Process

BugOps runs as a separate `bugops` process in `Procfile`, independent of FastAPI, Celery worker, or Celery Beat.

**Polling loop:**
1. Iterate over enabled signal sources
2. Call `collect()` async; receive list of alerts
3. For each alert, call `process_alert_event()` in the store
4. If new case created, send Slack notification and generate deterministic report
5. Sleep and repeat

**Configuration:** `BUGOPS_ENABLED`, `BUGOPS_POLL_INTERVAL_SECONDS`, `BUGOPS_SLACK_ENABLED`, `BUGOPS_SLACK_WEBHOOK_URL`

---

## Related Documents

- `10-bugops-runtime-model.md` — Monitor process and polling loop
- `20-bugops-data-model.md` — BugAlertEvent, BugCase, and related schemas
- `30-bugops-observability.md` — Logging and error handling
- `80-bugops-use-cases.md` — Example workflows
- `90-bugops-critiques-and-open-questions.md` — Known limitations and future work
