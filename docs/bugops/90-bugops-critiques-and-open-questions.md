# BugOps Critiques and Open Questions

**Date:** 2026-05-08  
**Version:** Sprint 018  
**Audience:** Product team, future developers

---

## Known Limitations (Sprint 018)

### 1. One Signal Source Only

**Limitation:** BugOps v1 only monitors LLM cost spikes. Infrastructure, performance, and application errors are not detected.

**Why Not Fixed Now:**
- Sprint 018 is validation of the smallest end-to-end path
- Adding Railway logs would require signal source implementation, not just interface validation
- Better to prove one source works perfectly than build two sources half-baked

**Future Work:**
- Sprint 019: Railway log ingestion (db errors, rate limits, budget warnings)
- Sprint 020: Sentry integration (application errors, performance anomalies)
- Sprint 021: Custom metrics (queue depth, inference latency, cache hit rates)

---

### 2. No Correlation Across Sources

**Limitation:** BugOps creates separate cases for each source. If a cost spike correlates with a database error, they appear as two unrelated incidents.

**Example:**
- 14:05 — Cost spike detected → Case A
- 14:06 — MongoDB AutoReconnect detected → Case B
- Operator must manually connect the dots

**Why Not Fixed Now:**
- With one source, correlation is meaningless
- Correlation logic requires domain knowledge (e.g., cost spike + db error = "likely inference retry loop")
- Better to validate single-source flow first

**Future Work:**
- Sprint 023: Multi-source correlation engine
  - Temporal grouping (incidents within 5 minutes)
  - Causal inference (cost spike probably caused by performance degradation)
  - Named correlation patterns (e.g., "cost spike + db error" → "inference retry storm")

---

### 3. No Synthesis or Analysis

**Limitation:** Deterministic reports only summarize observed metrics. No LLM analysis, root-cause hypotheses, or suggested remediation.

**Example Report:**
```
# Case: Cost Runaway

Severity: Critical
Detected: 2026-05-08 14:05 UTC

## Metrics
- Last 5 min: $0.27
- Projected hourly: $1.86
- Top operation: narrative_detection ($0.15)

## Known Facts
(no facts; only observed metrics)
```

**Why Not Fixed Now:**
- LLM synthesis is optional; deterministic reports are useful on their own
- Adding LLM calls means BugOps depends on LLM gateway, introduces LLM cost, and complicates testing
- Operator can already infer patterns from metrics + deterministic report

**Future Work:**
- Sprint 024: LLM-driven analysis
  - "Why might narrative_detection cost $0.27 in 5 minutes?"
  - "Has this happened before? How did we fix it?"
  - "What should the operator check first?"

---

### 4. Manual-Only Case Lifecycle

**Limitation:** No automatic closure, state transitions, or SLA tracking. Operators manually mark cases as resolved/closed.

**Pain Point:**
- Cases may linger in "open" status indefinitely
- No audit trail of who resolved what or when
- No dashboard to manage case workflow

**Why Not Fixed Now:**
- Sprint 018 is "humans read Slack and take action"
- Automated closure requires defining SLOs, escalation paths, and auto-close rules
- Better to have operators manually track cases first, then automate based on observed patterns

**Future Work:**
- Sprint 025: Case dashboard and workflow
  - Manual resolution UI
  - Suggested auto-close rules (e.g., "close if no alerts in 24 hours")
  - SLA tracking and alerting

---

### 5. No Slack UI or Commands

**Limitation:** BugOps sends one-way Slack notifications. No buttons, commands, or interactive acknowledgement.

**Operator Workflow:**
1. Receive notification
2. Open MongoDB/dashboard manually
3. Mark case as resolved manually
4. (No Slack ack or resolution via Slack)

**Why Not Fixed Now:**
- One-way webhooks are sufficient to prove the value
- Interactive Slack requires building a Slack bot, handling rate limits, and managing OAuth
- Better to validate notification flow first

**Future Work:**
- Sprint 026: Slack interactive UI
  - "Acknowledge" button (marks case as acknowledged in Slack)
  - "Resolve" button (marks case as resolved)
  - Slash command: `/bugops case <id>` (fetch case details in Slack)

---

### 6. No Autonomous Remediation

**Limitation:** BugOps only alerts. It never pauses jobs, changes env vars, rolls back deploys, or writes to production app collections.

**Why Not Fixed Now:**
- Autonomous action requires extreme confidence in detection accuracy
- Risk of cascading failure (e.g., auto-pause narrative_detection → service degradation → customer impact)
- Better to have humans decide mitigation first

**Future Work:**
- Sprint 027: Autonomous mitigations (with human approval)
  - Pause non-critical operations
  - Adjust rate limiting
  - Trigger cached data refresh
  - Escalate to on-call engineer

---

## Open Questions

### 1. What defines "cost runaway"?

**Current thresholds:**
- Critical: Last 5-minute spend ≥ $0.25
- Warning: Projected hourly spend ≥ $1.00

**Open questions:**
- Should thresholds be dynamic (e.g., based on time of day or day of week)?
- Should we track spend anomalies relative to recent history (e.g., 3x spike)?
- Should different operations have different thresholds?

**Decision needed by:** Sprint 019 (when adding more signal sources)

---

### 2. Should BugOps monitor internal services (Celery workers, background jobs)?

**Current answer:** No. BugOps monitors production behavior via `llm_traces` only.

**Open questions:**
- Should BugOps detect Celery worker crashes?
- Should BugOps detect retry storms in workers?
- Should BugOps detect scheduler (Celery Beat) failures?

**Risk:** If BugOps depends on Celery for monitoring, it can't alert about Celery itself.

**Decision needed by:** Sprint 020 (when planning infrastructure monitoring)

---

### 3. How should BugOps handle cascading alerts?

**Scenario:** One root cause (database down) triggers 10 alerts (each API call fails).

**Current behavior:**
- First alert creates case
- Next 9 alerts attach to case
- Case shows 10 alerts in report

**Open questions:**
- Should we deduplicate or suppress alerts from the same root cause?
- Should correlation logic identify "cascading" patterns?
- Should aggregation show "1 root cause, 10 symptoms" instead of "10 separate events"?

**Decision needed by:** Sprint 023 (correlation engine)

---

### 4. What is the right dedupe_key granularity?

**Current:** Hourly bucketing for cost-runaway (`llm_traces:cost_runaway:2026-05-08:14`)

**Open questions:**
- Is hourly too coarse? (miss rapid incidents)
- Is hourly too fine? (too many cases for same issue)
- Should it be adaptive (e.g., per-operation, per-model)?

**Examples:**
- `llm_traces:cost_runaway:gpt-4:2026-05-08:14` (per-model)
- `llm_traces:cost_runaway:narrative_detection:2026-05-08:14` (per-operation)
- `llm_traces:cost_runaway:2026-05-08:14:00` (10-minute window)

**Decision needed by:** Sprint 019 (based on observed alert patterns)

---

### 5. Should BugOps alert during expected maintenance windows?

**Scenario:** Scheduled database migration 2026-05-15 2:00 AM. BugOps will detect connection errors and alert.

**Open questions:**
- Should operators pre-create "silence windows" in BugOps?
- Should alerts during maintenance windows be tagged differently (e.g., "expected")?
- Should we suppress notifications but still create cases?

**Decision needed by:** Sprint 022 (when on-call team runs first maintenance with BugOps live)

---

### 6. How should BugOps track false positives?

**Scenario:** Alert fires, but operator determines it was a transient spike or misconfiguration.

**Open questions:**
- Should operators mark cases as "false_positive"?
- Should we track false positive rate per alert type?
- Should we use false positive feedback to adjust thresholds?

**Decision needed by:** Sprint 025 (when we have enough historical data)

---

### 7. Should Railway log ingestion be reactive or proactive?

**Reactive:** Log streaming via Railway API (requires Railway service token)

**Proactive:** Periodic `railway logs` polling (current spike approach)

**Open questions:**
- Which is more reliable (API vs. CLI)?
- Which is more cost-effective?
- Should we implement both and compare?

**Decision needed by:** Sprint 019 (when implementing Railway log source)

---

### 8. What is the acceptable alert latency?

**Current:** 60-second polling interval = up to 60 seconds before alert is detected

**Open questions:**
- Is 60 seconds acceptable? Or should we poll more frequently?
- Is the tradeoff worth it (cost of API calls vs. detection speed)?
- Should different alert types have different latencies (e.g., cost alerts every 60s, but db errors every 10s)?

**Decision needed by:** Sprint 019 (based on observed incident response times)

---

### 9. How should BugOps behave during monitoring outages?

**Scenario:** MongoDB is down. BugOps can't create cases or fetch alerts.

**Current behavior:** Errors are logged, monitor continues polling

**Open questions:**
- Should BugOps alert about its own failures?
- Should we implement a "BugOps health" metric?
- Should BugOps exit gracefully if DB is unreachable for > N minutes?

**Decision needed by:** Sprint 021 (when planning operational readiness)

---

### 10. Should BugOps integrate with incident management (PagerDuty, OpsGenie)?

**Current:** Only Slack notifications

**Open questions:**
- Should critical alerts trigger PagerDuty incidents?
- Should high severity auto-escalate to on-call engineer?
- Should on-call acknowledgement close the BugOps case?

**Decision needed by:** Sprint 026 (when scaling on-call operations)

---

## Resolved Questions

### ✅ Should BugOps write to existing production app collections?

**Answer:** No. BugOps only writes to new `bug_*` collections.

**Rationale:** Minimize blast radius. If BugOps has a bug, it doesn't corrupt `articles`, `narratives`, or `api_costs`.

---

### ✅ Should BugOps be deterministic or use LLM reasoning?

**Answer:** Deterministic in Sprint 018. LLM synthesis is future work.

**Rationale:** v1 must be auditable and reproducible. LLM calls add latency and cost.

---

### ✅ Should BugOps run in Celery Beat or separately?

**Answer:** Separate `bugops` process in Procfile.

**Rationale:** BugOps may later monitor Celery Beat. It can't depend on the thing it monitors.

---

## Related Documents

- `00-bugops-system-overview.md` — System design and scope
- `10-bugops-runtime-model.md` — Runtime behavior
- `20-bugops-data-model.md` — Data schema
- `30-bugops-observability.md` — Logging and debugging
- `80-bugops-use-cases.md` — Example workflows
