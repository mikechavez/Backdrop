# BUG-055/056/057 Cost Cascade Incident Walkthrough

## Important Note: Counterfactual Replay

This walkthrough is not a literal reconstruction of what observability existed during BUG-055/056/057.

At the time of the original incident, the system did not yet have the current LLM Gateway, structured `llm_traces`, spend-cap enforcement, or circuit-breaker behavior. Some signals shown here are counterfactual: they represent what BugOps could detect if a similar cascade happened today after the gateway/tracing/budget infrastructure exists.

The walkthrough has two purposes:

1. Reconstruct the historical cascade using the best available understanding.
2. Test whether the proposed BugOps architecture would detect and correlate an equivalent future cascade.

---

## Executive Summary

On Sprint 12, three related bugs compounded into a **$10 budget burn in 2 hours**. This document walks through how BugOps would detect, correlate, and surface this cascade to humans as a **single incident case** rather than four disconnected alerts.

The core design challenge: **When multiple monitors fire within a time window and share domain (cost, service, model), how do we merge them into one parent case and present a deterministic incident timeline before involving the LLM?**

---

## 1. Historical Incident Summary

**Timeline:**
- **14:32 UTC** — RSS pipeline processes backlog; 100+ articles queued for enrichment
- **14:33 UTC** — Briefing generation triggered (SMOKE_BRIEFINGS=1 still on from testing)
- **14:34 UTC** — Cost tracking logs first spike: `cost_tracked: $0.08 in 2 minutes`
- **14:36 UTC** — Validation failures begin (deterministic, not transient)
- **14:37 UTC** — Retry loop triggered: Each failed article retried 4 times (BUG-057)
- **14:40 UTC** — Cost now $0.32; no spend cap exists (BUG-056), requests continue
- **14:45 UTC** — Cost spike accelerates: $0.08/min → $0.12/min
- **14:50 UTC** — Cost reaches $0.80; human notices on dashboard
- **14:52 UTC** — Cost hits $1.20; still climbing
- **14:55 UTC** — **CRITICAL**: Cost exceeds $10 monthly budget entirely
- **15:00 UTC** — Soft-limit retry loop triggered (BUG-062); requests fail with 429
- **15:05 UTC** — On-call human intervenes; disables SMOKE_BRIEFINGS, stops pipeline

**Compounding factors:**
1. **BUG-055**: SMOKE_BRIEFINGS=1 left on → unnecessary briefings consume 40% of budget
2. **BUG-056**: No spend cap → requests continue past budget threshold
3. **BUG-057**: Validation failures retried 4× → cost multiplier (4x on each failed article)
4. **BUG-054** (upstream): RSS pipeline restart with backlog → triggered all three

**Result:** $10 budget in 33 minutes vs. normal $0.30/day = **33x cost spike**.

---

## 2. What Signals Would BugOps Detect?

BugOps monitors four independent signals that should fire in sequence:

### 2.1 Cost Runaway Monitor
```
Trigger: Daily cost > $2 in any 5-minute window
Severity: CRITICAL
Example metric:
  - Window: 14:30-14:35 UTC
  - Baseline: $0.01/5min
  - Observed: $0.32/5min
  - Multiplier: 32x baseline
```

### 2.2 Retry Storm Monitor
```
Trigger: Retry rate > 30% in 5-minute window
Severity: HIGH
Example metric:
  - Operation: entity_enrichment
  - Window: 14:35-14:40 UTC
  - Success: 60 requests
  - Retried: 180 requests (3 retries each)
  - Retry rate: 75%
```

### 2.3 Smoke/Debug Environment Signal
```
Trigger: SMOKE_BRIEFINGS=1 detected in production env
Severity: CRITICAL
Example:
  - Env var: SMOKE_BRIEFINGS
  - Value: "1"
  - Detected: First briefing request at 14:33 UTC
  - Expected: Should be "0" or unset in production
```

### 2.4 Circuit-Breaker Monitor (Soft Limit)
```
Trigger: Soft-limit retry loop fires (429 responses)
Severity: HIGH
Example metric:
  - Operation: narrative_enrichment
  - Window: 15:00-15:05 UTC
  - 429 responses: 45 in 5 minutes (normal: 0-1)
  - Budget exhausted: $10.32 / $10.00 limit
```

---

## 3. Which Monitors Fire? (In Order)

| Time | Monitor | Signal | Severity | Context |
|------|---------|--------|----------|---------|
| **14:34:12** | Cost Runaway | Daily cost $0.08 in 2 min | CRITICAL | Briefing generation (smoke test) |
| **14:35:45** | Smoke/Debug Env | SMOKE_BRIEFINGS=1 detected | CRITICAL | Production environment |
| **14:37:20** | Retry Storm | Retry rate 75% on entity_enrichment | HIGH | Validation failures (deterministic) |
| **14:40:15** | Cost Runaway | Daily cost $0.32 in 6 min | CRITICAL | No spend cap; requests continue |
| **15:00:30** | Circuit-Breaker | Soft-limit 429 responses spike | HIGH | Budget exhausted ($10.32) |

**Key observation:** Monitors fire over ~26 minutes. Without correlation, this is 5 separate incident alerts. With correlation, it's **1 incident with 5 signals**.

---

## 4. Case Correlation Rules

### 4.1 Simple v1 Rule: Time + Domain Window

```
IF multiple alerts fire within [30 minutes]
AND share at least one of:
  - service (e.g., "enrichment")
  - operation (e.g., "entity_enrichment", "narrative_briefing")
  - cost domain (e.g., LLM spend, budget)
  - model (e.g., "claude-sonnet")
THEN attach all to single parent case
```

**Correlation in this cascade:**

1. **Cost Runaway** (14:34) + **Smoke Env** (14:35)
   - Shared domain: cost + production
   - Action: Create parent case `INC-001: Production Cost Spike`
   - Attach both alerts

2. **Retry Storm** (14:37)
   - Shared operation: entity_enrichment (part of enrichment service)
   - Action: Attach to INC-001 (cost spike caused retries)

3. **Cost Runaway** (14:40)
   - Same alert type as 14:34, same case
   - Action: Update INC-001 with escalation (cost rising)

4. **Circuit-Breaker** (15:00)
   - Shared domain: budget exhaustion
   - Action: Attach to INC-001 (downstream effect of cost spike)

**Result:** One case with 5 alert events, not 5 cases.

### 4.2 Anti-Correlation: When NOT to Merge

```
DON'T merge alerts if:
  - Time gap > 30 minutes (could be separate incidents)
  - NO shared domain/service (unrelated systems)
  - Alerts contradict (e.g., "high latency" + "low utilization")
```

Example: If a monitoring alert fired at 14:30 about "database connection pool saturated" and a separate alert at 15:15 fired about "Redis cache miss spike", these would NOT correlate (no shared domain, >30 min gap).

---

## 5. Case JSON

### 5.1 Case Creation (14:34:12)

```json
{
  "case_id": "INC-001",
  "status": "open",
  "severity": "critical",
  "title": "Production Cost Spike: $0.08 in 2 minutes",
  "created_at": "2026-05-03T14:34:12Z",
  "last_updated": "2026-05-03T15:00:30Z",
  "time_window": {
    "start": "2026-05-03T14:34:12Z",
    "end": "2026-05-03T15:00:30Z",
    "duration_minutes": 26
  },
  "alert_events": [
    {
      "sequence": 1,
      "time": "2026-05-03T14:34:12Z",
      "monitor": "cost_runaway",
      "metric": {
        "name": "daily_cost_5min",
        "baseline": 0.01,
        "observed": 0.32,
        "multiplier": 32
      },
      "action": "CREATE case INC-001"
    },
    {
      "sequence": 2,
      "time": "2026-05-03T14:35:45Z",
      "monitor": "smoke_env_check",
      "metric": {
        "var_name": "SMOKE_BRIEFINGS",
        "value": "1",
        "environment": "production",
        "first_use": "2026-05-03T14:33:00Z"
      },
      "action": "ATTACH to INC-001"
    },
    {
      "sequence": 3,
      "time": "2026-05-03T14:37:20Z",
      "monitor": "retry_storm",
      "metric": {
        "operation": "entity_enrichment",
        "success_count": 60,
        "retry_count": 180,
        "retry_rate": 0.75,
        "window_minutes": 5
      },
      "action": "ATTACH to INC-001"
    },
    {
      "sequence": 4,
      "time": "2026-05-03T14:40:15Z",
      "monitor": "cost_runaway",
      "metric": {
        "name": "daily_cost_6min",
        "observed": 0.32,
        "trajectory": "rising"
      },
      "action": "UPDATE INC-001 (escalation)"
    },
    {
      "sequence": 5,
      "time": "2026-05-03T15:00:30Z",
      "monitor": "circuit_breaker",
      "metric": {
        "operation": "narrative_enrichment",
        "http_429_5min": 45,
        "budget_exhausted": {
          "used": 10.32,
          "limit": 10.0
        }
      },
      "action": "ATTACH to INC-001 (terminal event)"
    }
  ],
  "correlation_rule": "multiple_alerts_30min_cost_domain",
  "deterministic_trace": {
    "root_cause": [
      "BUG-055: SMOKE_BRIEFINGS=1 left on production",
      "BUG-056: No spend cap enforcement",
      "BUG-057: Deterministic validation failures retried 4x"
    ],
    "trigger": "RSS pipeline backlog (100+ articles) + briefing generation",
    "escalation": [
      "Briefing cost (40% of budget) + retry multiplier (4x) + no cap = runaway"
    ]
  },
  "dashboard_timeline": [
    {
      "time": "14:34:12",
      "event": "Cost spike begins",
      "cost_rate": "$0.08 per 2 min"
    },
    {
      "time": "14:40:15",
      "event": "Cost rate accelerates",
      "cost_rate": "$0.32 per 5 min (32x baseline)"
    },
    {
      "time": "15:00:30",
      "event": "Budget exhausted; circuit-breaker fires",
      "total_cost": "$10.32",
      "action": "Human intervention required"
    }
  ]
}
```

### 5.2 Case Update (15:00:30, Terminal Event)

```json
{
  "case_id": "INC-001",
  "action": "update",
  "updated_fields": {
    "status": "requires_human_decision",
    "severity": "critical",
    "latest_alert": {
      "monitor": "circuit_breaker",
      "message": "Budget exhausted: $10.32 / $10.00 limit",
      "action_required": "Stop LLM requests; disable smoke test env vars"
    }
  }
}
```

---

## 6. Tool Calls in Exact Order

BugOps would invoke tools in this sequence:

### Phase 1: Alert Reception & Correlation (14:34:12 - 14:35:45)

```
[14:34:12] CostRunawayMonitor.fire()
  ├─ metric: {name: "daily_cost_5min", observed: 0.32, baseline: 0.01}
  ├─ lookup: active_cases.query("cost OR budget OR spend", time_window=30min)
  │  └─ result: [] (no matching cases)
  ├─ action: cases.create(
  │    title="Production Cost Spike: $0.08 in 2 minutes",
  │    severity="critical",
  │    alerts=[alert_1]
  │  )
  └─ output: case_id="INC-001"

[14:35:45] SmokeEnvMonitor.fire()
  ├─ metric: {var_name: "SMOKE_BRIEFINGS", value: "1", env: "production"}
  ├─ lookup: active_cases.query("cost OR smoke OR briefing OR debug", time_window=30min)
  │  └─ result: [INC-001] (cost spike within 30 min, shared domain "cost")
  ├─ action: cases.attach_alert(
  │    case_id="INC-001",
  │    alert=alert_2,
  │    reasoning="Smoke env var explains cost spike root cause"
  │  )
  └─ output: INC-001.alert_count=2
```

### Phase 2: Signal Cascade (14:37:20 - 14:40:15)

```
[14:37:20] RetryStormMonitor.fire()
  ├─ metric: {operation: "entity_enrichment", retry_rate: 0.75, window: 5min}
  ├─ lookup: active_cases.query("entity_enrichment OR enrichment OR retry", time_window=30min)
  │  └─ result: [INC-001] (cost spike, shared operation "enrichment")
  ├─ action: cases.attach_alert(
  │    case_id="INC-001",
  │    alert=alert_3,
  │    reasoning="Retry storm explains cost multiplier; likely validation failures"
  │  )
  └─ output: INC-001.alert_count=3

[14:40:15] CostRunawayMonitor.fire() [again]
  ├─ metric: {name: "daily_cost_6min", observed: 0.32, trajectory: "rising"}
  ├─ lookup: active_cases.query("cost OR budget", time_window=30min)
  │  └─ result: [INC-001] (cost spike, same alert type)
  ├─ action: cases.update_alert(
  │    case_id="INC-001",
  │    alert=alert_4,
  │    escalation=true,
  │    reasoning="Cost continuing to rise; escalation detected"
  │  )
  └─ output: INC-001.status="escalating", INC-001.severity="critical"
```

### Phase 3: Terminal Event & Decision Point (15:00:30)

```
[15:00:30] CircuitBreakerMonitor.fire()
  ├─ metric: {operation: "narrative_enrichment", http_429_5min: 45, budget_exhausted: true}
  ├─ lookup: active_cases.query("cost OR budget OR 429 OR circuit", time_window=30min)
  │  └─ result: [INC-001] (cost spike, shared domain "budget")
  ├─ action: cases.attach_alert(
  │    case_id="INC-001",
  │    alert=alert_5,
  │    terminal=true,
  │    reasoning="Budget exhausted; circuit-breaker fired; manual intervention required"
  │  )
  ├─ output: INC-001.status="requires_human_decision"
  ├─ deterministic_trace(case_id="INC-001")
  │  └─ output: [root causes, escalation path, timeline]
  └─ notify_human(INC-001)
     └─ channel: oncall_slack, method: mention, urgency: critical
```

---

## 7. Tool-Call Trace Examples

### 7.1 Alert Correlation Lookup

```python
# When RetryStormMonitor fires at 14:37:20
active_cases = cases.query({
    "query_terms": ["entity_enrichment", "enrichment", "retry", "cost"],
    "time_window_minutes": 30,
    "status": ["open", "escalating"]
})

# Pseudocode match logic:
for case in active_cases:
    for alert in case.alerts:
        if (alert.operation == "entity_enrichment" or
            alert.service == "enrichment" or
            case.domain == "cost"):
            return case  # Match found: INC-001

# Result: Found INC-001 (created 3 min ago, cost spike + smoke env)
```

### 7.2 Deterministic Trace Generation

Once all alerts are attached, before LLM synthesis:

```python
def generate_deterministic_trace(case_id: str) -> dict:
    """
    Extract facts from alert sequence without LLM inference.
    """
    case = cases.get(case_id)
    
    trace = {
        "case_id": case_id,
        "alert_timeline": [],
        "observed_metrics": {},
        "causal_chain": []
    }
    
    # 1. Extract timeline from alerts (deterministic)
    for alert in sorted(case.alerts, key=lambda a: a.time):
        trace["alert_timeline"].append({
            "time": alert.time,
            "monitor": alert.monitor_name,
            "metric_value": alert.metric_value,
            "context": alert.context
        })
    
    # 2. Extract observed metrics (deterministic)
    cost_alerts = [a for a in case.alerts if "cost" in a.monitor_name]
    retry_alerts = [a for a in case.alerts if "retry" in a.monitor_name]
    
    trace["observed_metrics"] = {
        "cost_spike": {
            "first_observed": cost_alerts[0].time,
            "multiplier": max(a.metric_value.multiplier for a in cost_alerts),
            "trajectory": "rising"
        },
        "retry_rate": {
            "max": max(a.metric_value.retry_rate for a in retry_alerts) if retry_alerts else 0,
            "affected_operation": "entity_enrichment"
        }
    }
    
    # 3. Build causal chain (deterministic facts only, no LLM)
    smoke_env_alert = next((a for a in case.alerts if "smoke" in a.monitor_name), None)
    if smoke_env_alert:
        trace["causal_chain"].append({
            "step": 1,
            "fact": f"SMOKE_BRIEFINGS=1 detected in production at {smoke_env_alert.time}",
            "evidence": smoke_env_alert.metric_value
        })
    
    if retry_alerts:
        trace["causal_chain"].append({
            "step": 2,
            "fact": f"Retry rate 75% on entity_enrichment starting at {retry_alerts[0].time}",
            "evidence": retry_alerts[0].metric_value
        })
    
    if cost_alerts:
        trace["causal_chain"].append({
            "step": 3,
            "fact": f"Cost spike multiplier {cost_alerts[-1].metric_value.multiplier}x baseline",
            "evidence": [a.metric_value for a in cost_alerts]
        })
    
    return trace
```

**Output:**
```json
{
  "case_id": "INC-001",
  "deterministic_trace": {
    "alert_timeline": [
      {
        "time": "2026-05-03T14:34:12Z",
        "monitor": "cost_runaway",
        "metric_value": {"multiplier": 32},
        "context": "daily_cost_5min"
      },
      {
        "time": "2026-05-03T14:35:45Z",
        "monitor": "smoke_env_check",
        "metric_value": {"var_name": "SMOKE_BRIEFINGS", "value": "1"},
        "context": "production"
      },
      ...
    ],
    "observed_metrics": {
      "cost_spike": {
        "first_observed": "2026-05-03T14:34:12Z",
        "multiplier": 32,
        "trajectory": "rising"
      },
      "retry_rate": {
        "max": 0.75,
        "affected_operation": "entity_enrichment"
      }
    },
    "causal_chain": [
      {
        "step": 1,
        "fact": "SMOKE_BRIEFINGS=1 detected in production at 2026-05-03T14:35:45Z",
        "evidence": {"var_name": "SMOKE_BRIEFINGS", "value": "1", "environment": "production"}
      },
      {
        "step": 2,
        "fact": "Retry rate 75% on entity_enrichment starting at 2026-05-03T14:37:20Z",
        "evidence": {"success_count": 60, "retry_count": 180, "retry_rate": 0.75}
      },
      {
        "step": 3,
        "fact": "Cost spike multiplier 32x baseline; trajectory rising",
        "evidence": [
          {"time": "2026-05-03T14:34:12Z", "multiplier": 32},
          {"time": "2026-05-03T14:40:15Z", "multiplier": 32}
        ]
      }
    ]
  }
}
```

---

## 8. Slack Alert Text

### 8.1 Initial Alert (14:34:12)

```
🔴 CRITICAL: Production Cost Spike

Service: Enrichment Pipeline
Time: 2026-05-03 14:34:12 UTC
Cost Rate: $0.08 per 2 minutes (32x baseline)
Baseline: $0.01 per 5 minutes

⚠️  Incident case created: INC-001
Next: Waiting for correlation signals...

Link: [View Case](http://dashboard/cases/INC-001)
```

### 8.2 Correlated Alert (14:35:45)

```
🔴 CRITICAL: INC-001 - Smoke Environment Detected

⬆️  CASE ESCALATION

Alert: SMOKE_BRIEFINGS=1 found in production environment
Detected: 2026-05-03 14:35:45 UTC
Expected: SMOKE_BRIEFINGS should be "0" or unset

Impact: Briefing generation consuming 40% of budget (unnecessary in production)

Case: INC-001 (Cost Spike)
Root Cause Signal: This explains the 32x cost multiplier starting 14:34:12

Link: [View Case](http://dashboard/cases/INC-001)
```

### 8.3 Cascade Alert (14:37:20)

```
🟠 HIGH: INC-001 - Retry Storm Detected

⬆️  CASE ESCALATION

Alert: Retry rate 75% on entity_enrichment service
Window: 2026-05-03 14:35-14:40 UTC
Operation: entity_enrichment (enrichment pipeline)
Success: 60, Retried: 180 (3 retries per article)

Likely Cause: Validation failures (deterministic, not transient)

Case: INC-001 (Cost Spike)
Impact: 4x cost multiplier on each failed article

Link: [View Case](http://dashboard/cases/INC-001)
```

### 8.4 Terminal Alert (15:00:30)

```
🔴 CRITICAL: INC-001 - Budget Exhausted

⬆️  CASE TERMINAL EVENT - HUMAN DECISION REQUIRED

Alert: Circuit-breaker fired; 45x 429 responses in 5 minutes
Budget Used: $10.32 / $10.00 limit
Operation: narrative_enrichment
Time: 2026-05-03 15:00:30 UTC

Case: INC-001 (Cost Spike)
Timeline:
  14:34:12 — Cost spike begins
  14:35:45 — SMOKE_BRIEFINGS=1 detected
  14:37:20 — Retry storm on entity_enrichment (75% retry rate)
  15:00:30 — Budget exhausted; circuit-breaker fired

Root Causes (Deterministic):
  • BUG-055: SMOKE_BRIEFINGS=1 left on production
  • BUG-056: No spend cap enforcement
  • BUG-057: Deterministic validation failures retried 4x

Action Required:
  1. [ ] Disable SMOKE_BRIEFINGS=1
  2. [ ] Stop enrichment pipeline
  3. [ ] Review validation logic
  4. [ ] Implement spend cap enforcement

Link: [View Case](http://dashboard/cases/INC-001)
Mention: @oncall
```

---

## 9. Dashboard Timeline

```
╔═══════════════════════════════════════════════════════════════════╗
║                      INCIDENT TIMELINE: INC-001                   ║
║                  Production Cost Spike (Critical)                  ║
╚═══════════════════════════════════════════════════════════════════╝

TIME          EVENT                       COST     STATUS
────────────────────────────────────────────────────────────────────
14:33:00      RSS pipeline backlog        $0.00    ▪ Normal
              starts processing

14:34:12  ✋   COST SPIKE ALERT            $0.08    🔴 Critical
              32x baseline detected
              [CASE CREATED: INC-001]

14:35:45  ✋   SMOKE ENV SIGNAL            $0.12    ⬆️  Escalating
              SMOKE_BRIEFINGS=1
              [ATTACHED TO INC-001]

14:37:20  ✋   RETRY STORM ALERT           $0.24    ⬆️  Escalating
              75% retry rate
              [ATTACHED TO INC-001]

14:40:15  ✋   COST RISING                 $0.32    ⬆️  Escalating
              Trajectory: UP
              [INC-001 UPDATED]

14:45:00      Cost acceleration           $0.56    🔴 Critical
              $0.08/min → $0.12/min

14:50:00      Cost trajectory             $1.20    🔴 Critical
              Still rising

15:00:30  ✋   CIRCUIT-BREAKER ALERT       $10.32   🔴 Terminal
              Budget exhausted
              429 responses firing
              [TERMINAL EVENT: INC-001]
              [HUMAN DECISION REQUIRED]

15:05:00      Human intervention          $10.32   ✅ Resolved
              (off-call disabled
              SMOKE_BRIEFINGS)
              [CASE CLOSED]

╔═══════════════════════════════════════════════════════════════════╗
║ Timeline: 14:33 → 15:05 (32 min) | Budget: $10 | Burned: $10.32  ║
║ Cost Rate: Rising from $0.01/5min to $0.32/5min (32x) at peak    ║
║ Root Causes: BUG-055 (smoke env) + BUG-056 (no cap) + BUG-057   ║
║              (retry on validation)                               ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

## 10. Deterministic Report Before LLM

This is what BugOps generates **before** calling the LLM synthesis. It's pure facts extracted from alert signals:

```markdown
# INC-001 Deterministic Report
**Generated:** 2026-05-03 15:00:30 UTC (Terminal Event)

## Timeline (Factual)

| Time | Alert | Metric | Source |
|------|-------|--------|--------|
| 14:34:12 | Cost Runaway | $0.08/2min (32x baseline) | cost_runaway_monitor |
| 14:35:45 | Smoke Env | SMOKE_BRIEFINGS=1 in production | smoke_env_monitor |
| 14:37:20 | Retry Storm | 75% retry rate on entity_enrichment | retry_storm_monitor |
| 14:40:15 | Cost Rising | $0.32/5min, trajectory UP | cost_runaway_monitor |
| 15:00:30 | Circuit-Breaker | Budget exhausted ($10.32/$10.00), 45x 429/5min | circuit_breaker_monitor |

## Observed Metrics (Factual)

**Cost Spike:**
- First spike: 14:34:12 UTC, $0.08 in 2 minutes
- Multiplier: 32x baseline
- Trajectory: Rising (confirmed at 14:40:15)
- Terminal: $10.32 total (budget $10.00 exceeded)

**Retry Storm:**
- Affected operation: entity_enrichment
- Success count: 60 requests
- Retry count: 180 requests (3x retry)
- Retry rate: 75%
- Window: 5 minutes (14:35-14:40)

**Budget Status:**
- Baseline daily spend: $0.30-0.40
- Observed spend in 32 minutes: $10.32
- Budget limit: $10.00/month
- Overage: $0.32 (3.2%)

## Environment Config (Factual)

| Variable | Value | Expected | Status |
|----------|-------|----------|--------|
| SMOKE_BRIEFINGS | 1 | 0 or unset | ❌ Wrong |
| SMOKE_NARRATIVES | 0 | 0 or unset | ✅ OK |
| ENV | production | production | ✅ OK |

**Finding:** SMOKE_BRIEFINGS=1 enabled in production environment. This enables unnecessary briefing generation (40% of baseline budget).

## Causal Chain (Deterministic Facts Only)

1. **Root Cause 1:** SMOKE_BRIEFINGS=1 left on production (BUG-055)
   - Evidence: smoke_env_monitor detected at 14:35:45
   - Impact: Briefing generation consuming $0.04/article (vs. expected $0.01)
   - Multiplier: 4x cost per briefing

2. **Root Cause 2:** No spend cap enforcement (BUG-056)
   - Evidence: Cost tracking exists but no gate/cut-off
   - Impact: Requests continued after $10 budget threshold
   - Decision: System only logged cost; did not block requests

3. **Root Cause 3:** Validation failures retried 4x (BUG-057)
   - Evidence: 75% retry rate on entity_enrichment, only 60 successes
   - Finding: Each failed article retried 3x deterministically
   - Impact: 4x cost multiplier on failed articles
   - Why retries failed: Validation failures are deterministic (not transient); retry cannot fix

4. **Trigger:** RSS pipeline backlog (100+ articles)
   - Evidence: Pipeline restart at ~14:30; articles queued
   - Effect: Triggered all three bugs simultaneously
   - Compounding: 4x (briefing) × 4x (retry) × no cap = 16x budget at scale

## Decision Points Before LLM

- [ ] **Stop Condition:** Budget exhausted; circuit-breaker firing 429s. Immediate action required.
- [ ] **Verify Root Causes:** Are BUG-055, BUG-056, BUG-057 confirmed?
- [ ] **Immediate Fixes:**
  1. Disable SMOKE_BRIEFINGS=1
  2. Stop enrichment pipeline
  3. Implement hard spend cap (block requests at $10 limit)
- [ ] **Post-Incident Review:** Why was SMOKE_BRIEFINGS left on? How to prevent?

---

## What LLM Synthesis Will Add

The deterministic report above is **sufficient for human decision** (stop the pipeline, disable smoke env). The LLM adds:

- Narrative explanation of why these bugs compounded
- Deeper root-cause analysis (e.g., "deterministic failures should not be retried")
- Recommendations for prevention (e.g., "add validation failure circuit-breaker")
- Risk assessment for similar cascades in other services
```

---

## 11. LLM Synthesis Report

**Prompt sent to Claude after deterministic report:**

```
You are an incident analyst. Below is a deterministic timeline of an incident 
(alerts, metrics, facts). Your job is to:

1. Synthesize the facts into a narrative explanation
2. Identify root causes and their interactions
3. Rank causality (which bug was most critical to prevent?)
4. Recommend prevention strategies
5. Assess risk in other systems

Do NOT invent new facts. Only synthesize and interpret the deterministic data.

[DETERMINISTIC REPORT INSERTED]

Analyze and provide:
- Incident Narrative (why did this happen?)
- Root Cause Analysis (which bugs caused this?)
- Interaction Analysis (how did they compound?)
- Prevention Recommendations
- Similar Patterns in Other Code
```

**LLM Output:**

```markdown
# INC-001 Incident Synthesis

## Incident Narrative

On 2026-05-03, three cost-related bugs compounded into a $10.32 budget burn 
in 32 minutes:

1. **SMOKE_BRIEFINGS=1 left on production** (BUG-055) caused unnecessary briefing 
   generation, consuming 40% of baseline budget.

2. **No spend cap enforcement** (BUG-056) meant that once costs spiked, the system 
   continued making LLM requests without any circuit-breaker. Cost tracking existed 
   (observability) but enforcement did not (no gate).

3. **Deterministic validation failures retried 4x** (BUG-057) applied a 4x cost 
   multiplier on failed articles. Each failure was deterministic (same input, same 
   validation error), yet the system retried as if transient.

**Compounding Effect:** When the RSS pipeline backlog hit enrichment at 14:33, 
all three bugs fired simultaneously:
- Briefing cost: 4x normal
- Retry cost: 4x on failures
- No cap: Requests continued
- Result: 16x budget multiplier at scale

This created a cascade: Initial spike (14:34) → Root cause detection (14:35) → 
Secondary spike (retry storm, 14:37) → Terminal event (circuit-breaker, 15:00).

## Root Cause Ranking (by Preventability)

1. **BUG-056 (No spend cap)** — Most critical preventable
   - Cost tracking without enforcement is a known anti-pattern
   - Should have been caught in architecture review
   - Even with BUG-055 and BUG-057, this bug alone would cause significant burn
   - **Prevention:** Mandatory gate design review for all budget-related code

2. **BUG-057 (Retry on deterministic failures)** — Second most preventable
   - LLM outputs are deterministic for same input
   - Retries only work on transient failures (429, timeout, etc.)
   - This pattern recurred in 3 separate bugs (BUG-056, BUG-057, BUG-062)
   - **Prevention:** LLM error handling design doc with clear retry criteria

3. **BUG-055 (Smoke env left on)** — Least catastrophic alone
   - Would cause 4x cost but not $10 budget burn
   - More of an operational oversight than design bug
   - **Prevention:** Pre-deploy checklist automation; TTL on test env vars

## Interaction Analysis

These bugs did not exist in isolation:

```
BUG-055 (4x cost)
       ↓
BUG-057 (4x on failures) ←─ BUG-056 (no gate)
       ↓                           ↓
     16x cost multiplier ←─── Requests continue
                                indefinitely
                                    ↓
                            Budget exhausted in 32 min
```

If **only BUG-055** existed: $0.16/day → manageable
If **only BUG-057** existed: $0.40/day (retry on some failures) → manageable
If **only BUG-056** existed: Other cost bugs still gated; impact limited

But **all three together** with a backlog trigger created a cascade that 
burned the entire month's budget in half an hour.

## Prevention Recommendations

### Short Term (Deploy to production immediately)
1. **Hard spend cap:** Block requests at $10 limit (currently soft-limit only)
2. **Disable SMOKE_BRIEFINGS globally** (should not be on production)
3. **Validate LLM failures:** Distinguish transient (429, timeout) from 
   deterministic (validation failure, hallucination)

### Medium Term (Design reviews)
1. **Budget architecture review:** Every budget-related feature must have a 
   gate (enforcement), not just observability
2. **LLM error handling design doc:** Outline retry criteria and fallback 
   behavior for each operation
3. **Pre-deploy checklist:** Automate check for SMOKE_* env vars

### Long Term (Patterns)
1. **Retry storm pattern:** Implement circuit-breaker for high-retry-rate 
   operations (>30% retry rate → stop, alert, manual review)
2. **Cost monitoring depth:** Monitor not just total cost but cost-per-operation 
   (e.g., cost per article, cost per briefing) to catch skew earlier
3. **Config management:** Centralize all test/smoke flags; apply TTL (auto-disable 
   after 24 hours if not explicitly renewed)

## Similar Patterns in Other Code

Searched for similar anti-patterns:

- **BUG-056 pattern (observability without enforcement):**
  - Narrative service has soft-limit retry loop (BUG-062) — same pattern
  - Recommendation: Apply hard spend cap to narrative service as well

- **BUG-057 pattern (retry on deterministic failures):**
  - Entity extraction validation (line 456) — checks entity validity; if fails, 
    no retry benefit
  - Signal scoring (line 389) — filters invalid signals; failures are deterministic
  - Recommendation: Audit all retry loops; remove retries where failure is deterministic

- **BUG-055 pattern (test env vars left on):**
  - SMOKE_NARRATIVES, SMOKE_SIGNALS not found (good)
  - But no systematic check; relying on manual cleanup
  - Recommendation: Add pre-deploy CI check for SMOKE_* pattern

## Confidence Levels

- **Incident timeline:** 100% (alert-sourced)
- **Root cause attribution:** 95% (SMOKE_BRIEFINGS confirmed, retry rate confirmed, 
  cost tracking confirmed as observability-only)
- **Bug interaction magnitude:** 85% (assumes linear cost multiplier; actual may be 
  slightly different)
- **Prevention effectiveness:** 80% (hard cap would prevent, but operational 
  discipline still needed)
```

---

## 12. Human Decision Point

**At 15:00:30 UTC, the on-call human receives INC-001 case with deterministic report + LLM synthesis.**

### What the Human Sees

1. **Case Summary:**
   - INC-001: Production Cost Spike (Critical)
   - Timeline: 14:34-15:00 (26 minutes)
   - Status: **REQUIRES HUMAN DECISION** (budget exhausted, circuit-breaker fired)

2. **Immediate Metrics:**
   - Budget used: $10.32 / $10.00 (overage: $0.32)
   - Cost rate at peak: $0.32 per 5 minutes (32x baseline)
   - Requests currently: 429 (circuit-breaker blocking)

3. **Root Causes (Deterministic):**
   - SMOKE_BRIEFINGS=1 in production ✓ (confirmed)
   - No spend cap enforcement ✓ (confirmed)
   - Retry storm on entity_enrichment (75% retry rate) ✓ (confirmed)

4. **LLM Synthesis:**
   - Why it happened (narrative)
   - Which bug was most critical (BUG-056: no spend cap)
   - What prevents recurrence

### Decision Tree

```
Human reads INC-001:

┌─ "Is budget exhausted and circuit-breaker firing?"
│  └─ YES → IMMEDIATE ACTION REQUIRED
│
├─ "Can I safely stop the pipeline?"
│  ├─ YES, it's backlog processing → STOP IT NOW
│  │  └─ [ ] Kill enrichment service
│  │  └─ [ ] Disable SMOKE_BRIEFINGS=1
│  │
│  └─ NO, it's production traffic → IMPLEMENT CAP FIRST
│     └─ [ ] Deploy hard spend cap ($10 limit)
│     └─ [ ] Then assess pipeline safety
│
├─ "After stopping, how to prevent?"
│  ├─ [ ] BUG-056: Implement hard spend cap (blocks at limit)
│  ├─ [ ] BUG-057: Fix retry logic (no retries on validation fail)
│  ├─ [ ] BUG-055: Remove SMOKE_BRIEFINGS from production
│  └─ [ ] Operational: Add pre-deploy checklist
│
└─ "Is this a new pattern or known bug?"
   ├─ NEW → File tickets, review with team
   └─ KNOWN (BUG-056/057) → Prioritize fixes, add to next sprint
```

### Actual Human Action (15:05 UTC)

1. **Immediate:** Stop enrichment pipeline
   ```bash
   # On-call kills background job
   celery control revoke enrichment.entity_extraction.*
   ```

2. **Disable smoke env:**
   ```bash
   # Edit config; disable SMOKE_BRIEFINGS
   # Restart app
   railway redeploy
   ```

3. **Verify:**
   - Cost rate drops from $0.32/5min to $0.01/5min ✓
   - Circuit-breaker no longer firing ✓
   - Budget stable at $10.32 (no further spending) ✓

4. **Case closed:** Human marks INC-001 as "Resolved (Manual Intervention)"

---

## 13. BUG Ticket Drafts

### BUG-055: SMOKE_BRIEFINGS=1 Left on Production

```markdown
# BUG-055: SMOKE_BRIEFINGS=1 Left on Production

**Severity:** Critical (Cost Impact)
**Status:** Confirmed
**Discovered:** 2026-05-03T14:35:45Z (INC-001)

## Problem

Configuration flag `SMOKE_BRIEFINGS=1` was left on in production environment, 
causing unnecessary briefing generation on every article enrichment cycle.

Impact: Briefing cost multiplier (4x normal), consuming 40% of baseline budget.

## Evidence

- Environment check at 14:35:45 UTC detected `SMOKE_BRIEFINGS=1`
- First briefing generated at 14:33 UTC (normal baseline: 0 per cycle)
- Cost attribution: Each briefing $0.04 (vs. expected $0.01 for articles alone)

## Root Cause

Configuration variable left on after testing. No deployment checklist to verify 
smoke flags were disabled before production deploy.

## Fix

**Immediate:**
```python
# In config.py
SMOKE_BRIEFINGS = os.getenv("SMOKE_BRIEFINGS", "0") == "1"

# In .env or secrets
SMOKE_BRIEFINGS=0  # Explicitly set to off
```

**Prevent recurrence:**
- [ ] Add pre-deploy checklist: "Are all SMOKE_* flags off?"
- [ ] Add CI check: `grep -r "SMOKE_" .env && exit 1` (fail if found)
- [ ] TTL on smoke flags: Auto-disable after 24 hours if not renewed

## Testing

- [ ] Verify SMOKE_BRIEFINGS=0 in production config
- [ ] Verify briefing generation rate drops to 0 per article
- [ ] Monitor cost rate for 24 hours (expect $0.30-0.40/day)

## Tickets Created

- INC-001 Incident Response (manual)
- BUG-056 (related: no spend cap)
- BUG-057 (related: retry on validation fail)
```

### BUG-056: No Spend Cap Enforcement

```markdown
# BUG-056: No Spend Cap Enforcement

**Severity:** Critical (Design Issue)
**Status:** Confirmed
**Discovered:** 2026-05-03T14:40:15Z (INC-001)

## Problem

System has cost **tracking** (observability: logs, metrics) but no cost **enforcement** 
(gate: circuit-breaker, request blocking).

When LLM spending exceeds budget threshold, system logs the overage but continues 
making requests.

Impact: BUG-055 + BUG-057 alone would cause sustained cost overages; lack of cap 
allows unbounded burn.

## Evidence

- Cost tracking exists: `cost_tracked: $X.XX` logged at every LLM call
- Circuit-breaker exists: Fires 429s when soft-limit exceeded
- **Gap:** No hard cap blocks requests at budget limit ($10.00/month)
- Result: At 15:00:30 UTC, requests continued until $10.32 spent

## Root Cause

Architecture assumption: "Cost tracking + monitoring = sufficient safety net"

This is a known anti-pattern. Cost observability ≠ cost enforcement.

## Fix

**Implement hard spend cap:**

```python
# In llm_gateway.py
class LLMGateway:
    def __init__(self, monthly_budget_cents: int = 1000):
        self.budget_cents = monthly_budget_cents
        self.soft_limit_cents = int(monthly_budget_cents * 0.80)  # 80% = soft limit
        self.hard_limit_cents = monthly_budget_cents  # 100% = hard limit
    
    async def call(self, prompt: str, model: str, **kwargs) -> str:
        # Check hard limit BEFORE making request
        current_spend = await metrics.get_daily_spend_cents()
        if current_spend >= self.hard_limit_cents:
            raise BudgetExhausted(
                f"Budget limit ${self.hard_limit_cents/100:.2f} exceeded. "
                f"Current spend: ${current_spend/100:.2f}. "
                f"Request blocked."
            )
        
        # Soft limit (earlier): Trigger retry loop circuit-breaker (existing)
        if current_spend >= self.soft_limit_cents:
            log.warning(f"soft_limit_80pct_reached: {current_spend/100:.2f}")
            # Existing logic: increase retry delay, alert oncall
        
        # Make request
        return await self._call_llm(prompt, model, **kwargs)
```

**Testing:**
- [ ] Unit test: Hard cap blocks requests at exact limit
- [ ] Integration test: Cost tracking + cap interaction
- [ ] Smoke test: Verify soft-limit still fires at 80%

## Tickets Created

- INC-001 Incident Response
- BUG-055 (smoke env)
- BUG-057 (retry logic)
```

### BUG-057: Deterministic Validation Failures Retried 4x

```markdown
# BUG-057: Deterministic Validation Failures Retried 4x

**Severity:** High (Cost Impact)
**Status:** Confirmed
**Discovered:** 2026-05-03T14:37:20Z (INC-001)

## Problem

Entity validation failures are **deterministic** (same input → same validation error), 
yet system retries them 4 times as if transient.

This applies a 4x cost multiplier on failed articles. Only the initial failure should 
be charged; retries waste budget on a problem retry cannot fix.

Impact: 4x cost on validation failures (estimated $0.40+ per failed article batch).

## Evidence

- Retry storm alert at 14:37:20: 75% retry rate on entity_enrichment
- Pattern: 60 successful enrichments, 180 retry attempts (3 retries per article)
- Analysis: Failures are validation-related (entity not in text), not network/transient

## Root Cause

Error handling treats all enrichment failures as transient:
```python
# Current pattern (WRONG)
for attempt in range(4):  # 4 attempts = initial + 3 retries
    try:
        entity = extract_entity(article)
        if not validate_entity(article.text):
            raise ValidationError(...)  # Deterministic
        break
    except Exception:
        if attempt < 3:
            continue  # Retry even on validation failures
        raise
```

Validation failures are deterministic. Retry helps only on transient failures:
- Transient: 429 (rate limit), timeout, connection error
- Deterministic: Validation failure (entity not in text), hallucination, format error

## Fix

```python
# In entity_extraction.py
from anthropic import RateLimitError, APIConnectionError, APITimeoutError

async def extract_entity(article):
    """Extract entity with proper transient/deterministic failure handling."""
    max_retries = 3
    
    for attempt in range(max_retries + 1):
        try:
            entity = await llm_gateway.call(prompt, model="sonnet")
            
            # Validate output (deterministic)
            if not validate_entity_in_text(entity, article.text):
                # Validation failure: No retry benefit
                log.warning(
                    f"entity_validation_failed: "
                    f"entity={entity}, article={article.id}"
                )
                return {"entity": entity, "confidence": 0.0}  # Degraded output
            
            return {"entity": entity, "confidence": 1.0}  # Success
            
        except (RateLimitError, APIConnectionError, APITimeoutError) as e:
            # Transient failures: Retry with backoff
            if attempt < max_retries:
                wait_sec = 2 ** attempt  # Exponential backoff
                log.info(f"entity_extraction_retry: attempt={attempt+1}, wait={wait_sec}s")
                await asyncio.sleep(wait_sec)
                continue
            
            # All retries exhausted; degrade
            log.error(f"entity_extraction_failed_all_retries: {e}")
            return {"entity": None, "confidence": 0.0}  # Degraded output
        
        except Exception as e:
            # Other errors (validation, logic, etc.): No retry benefit
            log.error(f"entity_extraction_error: {type(e).__name__}: {e}")
            return {"entity": None, "confidence": 0.0}  # Degraded output
```

**Testing:**
- [ ] Unit test: Validation failure returns degraded output on first attempt
- [ ] Unit test: 429 error retries with backoff
- [ ] Integration test: Retry rate on validation failures < 5%

## Tickets Created

- INC-001 Incident Response
- BUG-055 (smoke env)
- BUG-056 (no spend cap)
- Related: BUG-062 (soft-limit retry loop), BUG-064 (event loop lifecycle)
```

---

## 14. Verification Checks

### Verification Checklist for INC-001

```markdown
# INC-001 Verification Checklist

## Immediate (Within 1 hour)
- [x] Pipeline stopped (no more articles processing)
- [x] SMOKE_BRIEFINGS disabled in production
- [x] Cost rate dropped from 32x baseline to 1x
- [x] Circuit-breaker no longer firing 429s
- [x] Budget stable at $10.32 (no further spending)

## Short-term (Deploy fixes)
- [ ] BUG-056: Hard spend cap implemented and tested
- [ ] BUG-057: Validation failures no longer retried
- [ ] BUG-055: Pre-deploy checklist to verify smoke flags off
- [ ] Redeploy to production
- [ ] Monitor cost rate for 24 hours (verify $0.30-0.40/day baseline)

## Medium-term (Prevent recurrence)
- [ ] LLM error handling design doc written and reviewed
- [ ] CI check added for SMOKE_* env vars
- [ ] Architecture review completed for budget enforcement pattern
- [ ] Similar patterns audited in codebase (retry loops, cost gates)

## Incident Review
- [ ] Timeline validated with all stakeholders
- [ ] Root cause analysis agreed upon
- [ ] Prevention strategies prioritized
- [ ] Tickets assigned and scheduled for next sprint
```

### Test Execution (BUG-056 Hard Cap)

```python
# tests/test_llm_gateway_spend_cap.py
import pytest
from llm_gateway import LLMGateway, BudgetExhausted

@pytest.mark.asyncio
async def test_hard_cap_blocks_at_limit():
    """Hard cap blocks requests at exact budget limit."""
    gateway = LLMGateway(monthly_budget_cents=1000)  # $10
    
    # Simulate spending up to limit
    with patch("metrics.get_daily_spend_cents", return_value=1000):
        with pytest.raises(BudgetExhausted):
            await gateway.call("prompt", "sonnet")

@pytest.mark.asyncio
async def test_hard_cap_allows_below_limit():
    """Hard cap allows requests below limit."""
    gateway = LLMGateway(monthly_budget_cents=1000)
    
    with patch("metrics.get_daily_spend_cents", return_value=800):
        result = await gateway.call("prompt", "sonnet")
        assert result is not None  # Request succeeded

@pytest.mark.asyncio
async def test_soft_limit_alerts_at_80_percent():
    """Soft limit (80%) triggers alert without blocking."""
    gateway = LLMGateway(monthly_budget_cents=1000)
    
    with patch("metrics.get_daily_spend_cents", return_value=800):
        with patch("log.warning") as mock_warn:
            await gateway.call("prompt", "sonnet")
            mock_warn.assert_called_with("soft_limit_80pct_reached: 8.00")
```

---

## 15. What BugOps Changed vs. Current Workflow

### Current Workflow (Without BugOps)

```
[Alert fires]
  └─ Slack notification (raw metric, no context)
  
[Human reads alert]
  └─ Checks dashboard manually
  
[Human searches for root cause]
  ├─ Logs: grep for errors, timeline reconstruction
  ├─ Metrics: Check cost, latency, error rates
  ├─ Config: Manually verify env vars
  └─ Related alerts: Did other things fail at same time? (manual scan)

[Human synthesizes]
  └─ "This looks like a cost spike. Why? Let me check git history..."
  
[Human escalation]
  └─ Mentions team in Slack; manual incident discussion

[Resolution]
  └─ Manual stop of service; manual config fix; manual redeploy

[Post-incident]
  └─ Manual ticket writing; knowledge base update (if done)
```

**Time to human decision:** 15-30 minutes
**Cognitive load:** High (manual correlation, synthesis)
**Repeatability:** Low (each incident requires manual investigation)
**Deterministic data loss:** Likely (alerts not kept together; context scattered)

---

### BugOps Workflow (Automated Case Correlation)

```
[Alert 1 fires: Cost Runaway]
  ├─ Case created: INC-001
  └─ Correlation lookup: Any similar alerts in last 30 min?
     └─ Result: None (first alert)

[Alert 2 fires: Smoke Env]
  ├─ Correlation lookup: Any cases involving cost/budget/smoke in last 30 min?
  │  └─ Result: INC-001 found (cost spike alert 1 min ago)
  └─ Attach Alert 2 to INC-001 (with reasoning)

[Alert 3 fires: Retry Storm]
  ├─ Correlation lookup: Any cases involving entity_enrichment/cost in last 30 min?
  │  └─ Result: INC-001 found
  └─ Attach Alert 3 to INC-001

[Terminal Alert fires: Circuit-Breaker]
  ├─ Case status: ESCALATE to "requires_human_decision"
  ├─ Generate deterministic trace (timeline + facts)
  ├─ Call LLM synthesis (on completed trace)
  ├─ Send to human WITH full context:
  │  ├─ Timeline of all related alerts
  │  ├─ Deterministic facts (no inference needed)
  │  ├─ Correlation reasoning (why merged into one case)
  │  └─ LLM narrative + recommendations
  └─ Human decision point: Single case, not 5 alerts
```

**Time to human decision:** 2-3 minutes (automated correlation, deterministic trace, LLM synthesis)
**Cognitive load:** Low (case summary with full context provided)
**Repeatability:** High (same case structure, same trace generation, same LLM prompt)
**Deterministic data loss:** None (all alerts captured in one case)

---

### Key Improvements

| Aspect | Without BugOps | With BugOps |
|--------|---|---|
| **Alert Correlation** | Manual scan of Slack history | Automatic merge into case |
| **Timeline** | Human reconstructs from logs | Auto-generated from alert sequence |
| **Root Cause Clues** | Hidden in multiple alerts | Explicitly attached (SMOKE_BRIEFINGS) |
| **Deterministic Trace** | Not generated; LLM infers from scratch | Generated before LLM; LLM only synthesizes |
| **Decision Context** | Scattered across alerts | Single case with full context |
| **Time to Action** | 15-30 min | 2-3 min |
| **Prevent Recurrence** | Manual knowledge capture | Automated ticket templates |

---

## 16. Gaps Exposed by the Walkthrough

### 16.1 Case Correlation Gaps

**Gap 1: Time Window Tuning**
- Current rule: 30 minutes
- Problem: What if alerts space out (14:34, 14:50, 15:10)?
- Solution: Sliding window vs. fixed window; cost-domain alerts might need longer window
- **Action:** Monitor cascade timings; adjust window based on incident patterns

**Gap 2: Domain Classification**
- Current: "shared service, operation, model, budget domain"
- Problem: "budget domain" is vague; what counts as cost-related?
- Example: Is "high latency" cost-related? (No. Is "retry storm" cost-related? Yes.)
- **Action:** Build domain taxonomy; make correlation rules explicit and testable

**Gap 3: Alert Deduplication**
- Current: Attach each alert to case
- Problem: Same alert might fire multiple times (cost runaway fired twice)
- Solution: Detect same-alert-type firing again; update instead of duplicate
- **Action:** Implement alert deduplication (same monitor type, same window → update)

### 16.2 Deterministic Trace Gaps

**Gap 1: Cause Inference in Trace**
- Current: Trace extracts facts, but still infers causality
- Example: "Retry rate 75% started at 14:37, cost was rising at 14:34 → retry caused cost"
- Problem: Post-hoc ergo propter hoc (temporal correlation ≠ causation)
- **Action:** Separate "facts" from "inference"; mark all causality claims as hypotheses for human review

**Gap 2: Missing Context in Alerts**
- Current: Alerts have metric values, but not surrounding context
- Example: Retry rate 75% — but why are items failing?
- Problem: Cannot determine if retries are beneficial or harmful without failure reason
- **Action:** Enrich alerts with more context (error type, affected service, sample failures)

**Gap 3: Silent Failures Not Detected**
- Current: Monitors track explicit alerts (cost, retry, env var)
- Missing: Things that DON'T fire (e.g., "spending rate didn't alert oncall" = logging failure)
- Example: Cost tracking exists but alert rule is too loose; alert should have fired at 14:34:00 but fired at 14:34:12
- **Action:** Add "alert latency" metric; monitor alert firing speed

### 16.3 LLM Synthesis Gaps

**Gap 1: LLM Hallucination in Synthesis**
- Current: LLM given deterministic trace and asked to synthesize
- Risk: LLM invents plausible-sounding root causes not supported by alerts
- Example: LLM might say "MongoDB query timeout" when no timeout alert fired
- **Action:** Constrain LLM prompt to only synthesize facts already in trace; flag claims without evidence

**Gap 2: Precedent Blindness**
- Current: LLM analyzes single incident
- Gap: LLM doesn't know if this pattern recurred before (BUG-056, BUG-057, BUG-062 all retry-related)
- **Action:** Provide LLM with prior-incident summaries; ask if pattern matches

**Gap 3: Prevention Recommendations Not Verified**
- Current: LLM provides recommendations (e.g., "add hard spend cap")
- Gap: Recommendations might be infeasible (e.g., "hard cap breaks legitimate use cases")
- **Action:** Cluster recommendations across incidents; prioritize by feasibility + impact

### 16.4 Operational Gaps

**Gap 1: Case Resolution Without Fix Verification**
- Current: Human closes case after manual intervention
- Problem: Did fixes actually prevent recurrence? Was it just temporary band-aid?
- Example: Disabling SMOKE_BRIEFINGS fixes incident, but doesn't prevent future re-enabling
- **Action:** Require resolution evidence (e.g., "hard cap deployed and tested" not just "env var disabled")

**Gap 2: Ticket Tracking Disconnected from Case**
- Current: BugOps generates ticket templates; human manually files tickets
- Problem: Tickets can be lost, reprioritized, deprioritized without case knowledge
- **Action:** Link cases to tickets; track case closure until all related tickets are resolved

**Gap 3: Monitoring Blind Spots**
- Current: Case correlation depends on monitors firing
- Problem: What if something broke silently (e.g., cost tracking itself failed)?
- Example: Cost tracking logs not reaching database → no cost alerts → no case
- **Action:** Add "monitor health" alerts (are monitors themselves healthy?)

### 16.5 Process Gaps

**Gap 1: No Mandatory Post-Incident Review**
- Current: Case closed, team moves on
- Problem: Prevention recommendations rarely implemented
- Pattern: Same bugs recur (retry logic in BUG-056, BUG-057, BUG-062)
- **Action:** Require post-incident review; link to prevention ticket tracker

**Gap 2: Knowledge Capture Decays**
- Current: Deterministic trace + LLM synthesis = good analysis
- Problem: Knowledge lives in case; not in code, not in runbooks, not in team mental models
- **Action:** Auto-generate runbook from case (e.g., "If cost spike + SMOKE_* → disable X, restart Y")

**Gap 3: Similar Cascades in Other Domains Not Detected**
- Current: Pattern analysis happens per-incident
- Gap: Cost cascade analysis not applied to auth cascades, performance cascades, etc.
- **Action:** Extract generalizable patterns (alert correlation rules, trace generation, LLM prompts)

---

## Summary: BugOps Case Correlation Design

### Key Decision

**Single Parent Case for Correlated Alerts**

Instead of:
```
INC-001: Cost Spike (14:34)
INC-002: Smoke Environment (14:35)
INC-003: Retry Storm (14:37)
INC-004: Circuit-Breaker (15:00)
```

We have:
```
INC-001: Production Cost Spike (14:34-15:00)
  ├─ Alert 1: Cost Runaway (14:34)
  ├─ Alert 2: Smoke Env (14:35) ← Root cause clue
  ├─ Alert 3: Retry Storm (14:37) ← Secondary effect
  └─ Alert 4: Circuit-Breaker (15:00) ← Terminal

[Deterministic Trace] → [LLM Synthesis] → [Human Decision Point]
```

### Correlation Rule (v1)

```
IF multiple alerts fire within [30 minutes]
AND share at least one:
  - service (e.g., "enrichment")
  - operation (e.g., "entity_enrichment")
  - cost domain (budget, spend, cost tracking)
  - model (e.g., "claude-sonnet")
THEN attach all to single parent case
ELSE create separate cases
```

### Benefits

1. **Time to Decision:** 2-3 min (vs. 15-30 min manual)
2. **Context Preserved:** All signals in one place (not scattered across Slack)
3. **Deterministic Data:** Trace generated before LLM (prevents hallucination)
4. **Repeatability:** Same structure for all cascades (cost, performance, auth, etc.)
5. **Prevention:** Automated ticket generation from case

### Open Questions for Next Iteration

1. **Is 30 minutes right?** Should some domains have longer windows?
2. **How to handle alert storms?** If 20 cost alerts fire in 5 minutes, is it one case or 20?
3. **When NOT to correlate?** What are the false-positive risks?
4. **Cross-service cascades?** If cost spike in billing service affects article service, how to correlate?
5. **Cost of case lifecycle?** How long should a case stay open? When does it auto-resolve?

---

**End of Walkthrough**

This document is a **design artifact**, not a production runbook. It exposes the case-correlation problem and proposes a v1 solution. The next phase would be to implement the correlation engine and test it against real incident patterns.
