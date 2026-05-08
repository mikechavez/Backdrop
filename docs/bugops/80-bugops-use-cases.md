# BugOps Use Cases

**Date:** 2026-05-08  
**Version:** Sprint 018  
**Audience:** On-call operators, product team

---

## Use Case 1: LLM Cost Runaway Detection

**Scenario:** Narrative detection pipeline begins consuming LLM tokens at an unexpectedly high rate, potentially due to:
- Increased article volume
- Longer article text requiring more tokens
- Inefficient prompt design
- Accidental loop calling the same narration API

**What Happens:**

1. BugOps monitor polls `llm_traces` every 60 seconds
2. Detects 5-minute spending spike ≥ $0.25
3. Creates `bug_alert_event` with:
   - `severity: critical`
   - `dedupe_key: llm_traces:cost_runaway:2026-05-08:14`
   - `metrics`: last_5_min, last_60_min, projected_hourly, top operations, top models
4. Creates `bug_case` (first time in this hour)
5. Sends Slack notification with case details
6. Generates deterministic report with observed metrics

**Operator Response (Manual):**

- Reviews Slack notification
- Opens deterministic report (or future dashboard)
- Inspects `top_operations` and `top_models` in metrics
- Takes action:
  - Check narrative_detection job status
  - Review recent article ingestion spike
  - Temporarily pause non-critical enrichment
  - Investigate prompt changes
  - Investigate for infinite loops or duplicate API calls

**Expected Timeline:**

- 14:05 — Alert fired, case created, Slack notification sent
- 14:08 — Operator notified, reads message
- 14:15 — Operator identifies root cause
- 14:20 — Operator mitigates (pauses, fixes config, etc.)

---

## Use Case 2: Repeated Cost Runaway in Same Hour

**Scenario:** Cost-runaway alert fires multiple times in the same hour (e.g., at 14:05 and 14:45).

**What Happens:**

1. First alert (14:05) creates case with `dedupe_key: llm_traces:cost_runaway:2026-05-08:14`
2. Second alert (14:45) finds existing open case with same dedupe_key
3. Alert is attached to existing case (no new Slack notification)
4. Case `updated_at` is refreshed, metrics aggregated

**Operator Experience:**

- Only one Slack notification (at 14:05)
- Case metrics update over time as operator reads the report
- Operator knows the issue persisted across the hour

**Why hourly bucketing?** Prevents one perpetual "cost runaway" case that never closes. After an hour, a fresh incident creates a new case (and new Slack notification), so operators get periodic re-alerting even if the issue is ongoing.

---

## Use Case 3: Cost Runaway Resolved, Then Recurs Next Hour

**Scenario:** Operator mitigates the issue by pausing narrative detection. Cost returns to normal. An hour later, the issue recurs (perhaps detection was resumed or a new batch job started).

**What Happens:**

1. 14:05 — Alert creates case #A with `dedupe_key: llm_traces:cost_runaway:2026-05-08:14`
2. Operator pauses detection; cost normalizes
3. 15:05 — Alert fires again; queries for open case with dedupe_key `llm_traces:cost_runaway:2026-05-08:15`
4. No case found (dedupe_key changed; new hour)
5. **New case #B is created**
6. **New Slack notification is sent** (operator re-alerted)

**Operator Experience:**

- Two Slack notifications (one per hour of recurring issue)
- Two separate cases in database
- Operator can see the pattern: issue recurred after mitigation

---

## Use Case 4: Railway Log Monitoring (Future)

**Note:** This is out of scope for Sprint 018. The following is a preview of future functionality.

**Scenario:** In Sprint 019+, BugOps will ingest Railway logs to detect infrastructure issues.

**Example Alert:** MongoDB connection drops

```
Timestamp: 2026-05-08 20:45:00
Message: pymongo.errors.AutoReconnect: <MONGO_HOST>:27017: connection closed
Severity: high
```

**What Would Happen:**

1. `RailwayLogSignalSource.collect()` parses log lines
2. Detects `AutoReconnect` pattern
3. Creates alert with:
   - `source_type: railway_logs`
   - `source_id: railway_logs:mongo_autoreconnect`
   - `alert_type: db_connection_error`
   - `severity: high`
   - `dedupe_key: railway_logs:mongo_autoreconnect:2026-05-08:20`
4. Creates case (or reuses if open)
5. Sends Slack notification

**Operator Response:**

- Checks Atlas cluster status
- Checks Network policy / VPC peering
- May trigger failover or manual intervention

**Why Not In Sprint 018?**

Railway log ingestion is more complex:
- Requires Railway API token (not CLI)
- Multiline stack traces need reconstruction
- Multiple log formats and bare platform messages
- High duplicate suppression burden

Sprint 018 validates the `SignalSource` interface against real log samples. Implementation is deferred.

---

## Use Case 5: BUG-055/056/057 Walkthrough (Counterfactual)

**Note:** The BUG-055/056/057 walkthrough is a counterfactual/current-system replay, not literal historical telemetry.

In future documentation or training materials, we may walk through how BugOps would detect and handle the cost issues described in BUG-055, BUG-056, and BUG-057, using realistic but hypothetical log samples.

**Example:** "If this cost spike had occurred on 2026-04-28, BugOps would have:
1. Detected it at 14:05 UTC (5-minute window)
2. Created a critical case
3. Sent Slack notification
4. Generated a report showing the top operations (narrative_detection) and models (gpt-4)
5. Operator would have seen the notification within minutes"

**Why Counterfactual?**

- Historical logs may not exist or be insufficient
- Counterfactual allows us to demonstrate the system's value without real incidents
- Supports training and onboarding for future on-call teams

---

## Operator Workflow Summary

**Discovery:**
1. Operator receives Slack notification from BugOps
2. Reads case details (severity, alert_type, source, dedupe_key)
3. Reviews deterministic report with metrics

**Investigation:**
1. Checks top operations and models in metrics
2. Reviews relevant logs (e.g., narrative_detection worker logs)
3. Checks system metrics (CPU, memory, database connection pool)

**Mitigation:**
1. Temporarily disable non-critical operations (pause narrative_detection)
2. Investigate root cause (prompt change, data volume spike, loop)
3. Apply permanent fix or rollback

**Resolution (Manual):**
1. Once confident issue is fixed, operator marks case as `resolved` (future dashboard)
2. Later marks as `closed` when ready to archive
3. No automatic closure; always manual

---

## Limitations (Sprint 018)

- **One signal source:** Only LLM cost spikes detected. Infrastructure issues are not monitored.
- **No correlation:** Can't group related incidents from multiple sources (e.g., cost spike + worker crash).
- **No synthesis:** Reports are deterministic summaries, not LLM-generated analysis.
- **No autonomy:** No automatic mitigations, only operator notification.
- **No dashboard:** No real-time visualization. Operator reads Slack and MongoDB directly.
- **No Slack UI:** No buttons, commands, or interactive acknowledgement.

---

## Related Documents

- `00-bugops-system-overview.md` — System design and scope
- `10-bugops-runtime-model.md` — Runtime behavior
- `20-bugops-data-model.md` — Data schema
- `30-bugops-observability.md` — Logging and debugging
- `90-bugops-critiques-and-open-questions.md` — Known limitations and future work
