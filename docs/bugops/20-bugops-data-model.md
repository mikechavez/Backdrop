# BugOps Data Model

**Date:** 2026-05-08  
**Version:** Sprint 018  
**Audience:** Developers, schema reviewers

---

## Collections

BugOps uses four MongoDB collections:

```
bug_alert_events  — Normalized alerts from signal sources
bug_cases         — Case containers, grouped by dedupe_key
bug_case_events   — Audit trail of case state changes
bug_tool_calls    — Future: Tool invocations and results
```

---

## BugAlertEvent

Normalized alert from any signal source.

### Required Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `_id` | ObjectId | (auto) | MongoDB primary key |
| `source_type` | str | `"llm_traces"` | Which signal source |
| `source_id` | str | `"llm_traces:cost_runaway"` | Pattern identifier within source |
| `alert_type` | str | `"cost_runaway"` | Human-readable alert category |
| `severity` | enum | `"critical"` | **Required field.** One of: `info`, `warning`, `high`, `critical` |
| `dedupe_key` | str | `"llm_traces:cost_runaway:2026-05-08:14"` | Case grouping key (exact match) |
| `metrics` | dict | `{"last_5_min": 0.27, ...}` | Source-specific metrics |
| `created_at` | datetime | (ISO 8601) | Alert detection time |

### Optional Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `correlation_keys` | list[str] | `["op:narrative_detection", "model:gpt-4"]` | Future multi-source correlation |
| `raw_sample_ref` | str | Log line or trace reference | Original source data reference |

### Example: Cost-Runaway Alert

```json
{
  "_id": ObjectId("..."),
  "source_type": "llm_traces",
  "source_id": "llm_traces:cost_runaway",
  "alert_type": "cost_runaway",
  "severity": "critical",
  "dedupe_key": "llm_traces:cost_runaway:2026-05-08:14",
  "metrics": {
    "last_5_min_usd": 0.27,
    "last_60_min_usd": 1.45,
    "projected_hourly_usd": 1.86,
    "threshold_critical_usd": 0.25,
    "threshold_warning_usd": 1.00,
    "window_start_utc": "2026-05-08T14:00:00Z",
    "window_end_utc": "2026-05-08T14:05:00Z",
    "top_operations": [
      {"operation": "narrative_detection", "cost_usd": 0.15},
      {"operation": "entity_enrichment", "cost_usd": 0.08}
    ],
    "top_models": [
      {"model": "gpt-4", "cost_usd": 0.20},
      {"model": "gpt-3.5-turbo", "cost_usd": 0.03}
    ]
  },
  "created_at": "2026-05-08T14:05:32Z"
}
```

---

## BugCase

Container for related alerts, grouped by `dedupe_key`.

### Required Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `_id` | ObjectId | (auto) | MongoDB primary key |
| `dedupe_key` | str | `"llm_traces:cost_runaway:2026-05-08:14"` | Exact match key from alerts |
| `source_type` | str | `"llm_traces"` | From the alert that created this case |
| `source_id` | str | `"llm_traces:cost_runaway"` | From the alert |
| `alert_type` | str | `"cost_runaway"` | From the alert |
| `severity` | enum | `"critical"` | Current severity (may aggregate multiple alerts) |
| `status` | enum | `"open"` | One of: `open`, `resolved`, `closed` |
| `created_at` | datetime | (ISO 8601) | Case creation time (first alert) |

### Optional Fields

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `metrics` | dict | `{"last_5_min": 0.27, ...}` | Aggregated metrics from case alerts |
| `suggested_manual_check` | str | `"Check narrative_detection queue depth"` | Operator guidance |
| `deterministic_report` | str | (Markdown) | Generated on case creation |
| `updated_at` | datetime | (ISO 8601) | Latest alert or state change |
| `alert_ids` | list[ObjectId] | `[ObjectId(...), ...]` | IDs of attached alerts |
| `resolved_at` | datetime | (ISO 8601) | When operator marked resolved |
| `closed_at` | datetime | (ISO 8601) | When operator marked closed |

### Example: Cost-Runaway Case

```json
{
  "_id": ObjectId("..."),
  "dedupe_key": "llm_traces:cost_runaway:2026-05-08:14",
  "source_type": "llm_traces",
  "source_id": "llm_traces:cost_runaway",
  "alert_type": "cost_runaway",
  "severity": "critical",
  "status": "open",
  "created_at": "2026-05-08T14:05:32Z",
  "updated_at": "2026-05-08T14:10:15Z",
  "metrics": {
    "alert_count": 2,
    "last_5_min_usd": 0.31,
    "last_60_min_usd": 1.52,
    "projected_hourly_usd": 2.04
  },
  "suggested_manual_check": "Check narrative_detection queue; consider pausing non-critical enrichment",
  "deterministic_report": "# Case ID: ...\n\n...",
  "alert_ids": [ObjectId("..."), ObjectId("...")]
}
```

---

## Cost-Runaway Dedupe Key Format

Hourly bucketing to prevent one perpetual case while grouping repeated checks in the same incident window:

```
llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}
```

**Examples:**
- `llm_traces:cost_runaway:2026-05-08:14` — May 8, 2-3pm UTC
- `llm_traces:cost_runaway:2026-05-08:23` — May 8, 11pm-midnight UTC

**One case per hour.** If a cost-runaway alert fires at 14:05 and again at 14:45, both attach to the same case. If the next alert fires at 15:02, a new case is created.

---

## BugCaseEvent (Audit Trail)

Records of case state transitions and events.

### Fields

| Field | Type | Purpose |
|-------|------|---------|
| `_id` | ObjectId | MongoDB primary key |
| `case_id` | ObjectId | Reference to BugCase |
| `event_type` | str | One of: `created`, `alert_attached`, `status_changed`, `report_generated` |
| `event_at` | datetime | When the event occurred |
| `metadata` | dict | Event-specific data (e.g., old_status, new_status) |

**Purpose:** Audit trail for future investigation. Not queried by the monitor; used for analysis and debugging.

---

## BugToolCall (Placeholder)

Reserved for future use when BugOps takes autonomous actions.

**Not used in Sprint 018.** Cases are manual-only; no tool invocations occur.

---

## Indexing Strategy

For Sprint 018, recommended indexes:

```javascript
// bug_alert_events
db.bug_alert_events.createIndex({ "dedupe_key": 1, "created_at": -1 })
db.bug_alert_events.createIndex({ "source_type": 1, "created_at": -1 })

// bug_cases
db.bug_cases.createIndex({ "dedupe_key": 1 })
db.bug_cases.createIndex({ "status": 1, "created_at": -1 })
db.bug_cases.createIndex({ "source_type": 1 })

// bug_case_events
db.bug_case_events.createIndex({ "case_id": 1, "event_at": -1 })
```

---

## Schema Evolution

As new signal sources are added (Railway logs, Sentry, etc.), new alert types will be added:

| Source | Alert Type | Dedupe Key Format |
|--------|-----------|-------------------|
| llm_traces | cost_runaway | `llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}` |
| railway_logs | db_connection_error | `railway_logs:mongo_autoreconnect:{YYYY-MM-DD}:{HH}` |
| railway_logs | budget_soft_limit | `railway_logs:budget_soft_limit:{YYYY-MM-DD}:{HH}` |
| railway_logs | platform_warning | `railway_logs:platform_log_rate_limit:{YYYY-MM-DD}:{HH}` |

The schema is designed to be extensible: new fields in `metrics` and `correlation_keys` require no schema migration.

---

## Related Documents

- `00-bugops-system-overview.md` — System design and scope
- `10-bugops-runtime-model.md` — Runtime behavior
- `30-bugops-observability.md` — Logging and monitoring
- `80-bugops-use-cases.md` — Example workflows
- `90-bugops-critiques-and-open-questions.md` — Known limitations
