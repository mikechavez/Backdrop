---
id: FEATURE-058
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-08
updated: 2026-05-08
branch: feature/bugops-signal-intake
---

# FEATURE-058: Implement llm_traces Cost-Runaway Signal Source

## Problem/Opportunity

The highest-impact historical bug cluster involved LLM cost runaway. `llm_traces` is the cleanest current structured signal source for detecting excessive LLM spend.

## Proposed Solution

Implement `LLMTraceCostSignalSource` that queries `llm_traces`, detects spend threshold breaches, and returns normalized `BugAlertEventCreate` objects.

## User Story

As a solo operator, I want BugOps to alert when LLM spend crosses a configured threshold so I can investigate before a cost cascade escalates.

## Implementation Scope

### Files to Create/Modify

```text
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
tests/bugops/test_llm_traces_cost_source.py
```

### Do Not Modify

```text
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/services/cost_tracker.py
src/crypto_news_aggregator/api/admin.py
```

## Exact Implementation Requirements

### Source behavior

`LLMTraceCostSignalSource.collect()` must:

1. Query `llm_traces`, not `api_costs`.
2. Use `timestamp` field for time filtering.
3. Sum `cost` field for recent spend.
4. Compute:

```text
last_5_min_spend
last_60_min_spend
projected_hourly_spend
cost_by_operation for window
cost_by_model for window
```

5. Return `[]` if thresholds are not breached.
6. Return one normalized alert event if thresholds are breached.

### Threshold rules for Sprint 018

Use simple absolute thresholds only. Do not implement baseline multiplier logic.

Alert if either condition is true:

```text
last_5_min_spend >= BUGOPS_COST_5MIN_THRESHOLD_USD
projected_hourly_spend >= BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD
```

### Severity rules

```text
critical = last_5_min_spend >= BUGOPS_COST_5MIN_THRESHOLD_USD
warning = projected_hourly_spend >= BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD but last_5_min threshold is not breached
```

### Dedupe key rule

Cost-runaway dedupe key must be rolling hourly UTC:

```text
llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}
```

Example:

```text
llm_traces:cost_runaway:2026-05-08:14
```

Do not use a permanent key like `llm_cost_runaway`.

### Required normalized fields

For cost runaway events:

```python
source_type = "llm_traces"
source_id = "llm_traces.cost_runaway"
alert_type = "cost_runaway"
domain = ["llm", "cost"]
correlation_keys = ["domain:llm", "domain:cost"]
```

If one operation dominates the cost window, include:

```python
operation = top_operation
correlation_keys.append(f"operation:{top_operation}")
```

If one model dominates the cost window, include:

```python
model = top_model
correlation_keys.append(f"model:{top_model}")
```

### Metric payload

Include at least:

```python
metric = {
    "last_5_min_spend": float,
    "last_60_min_spend": float,
    "projected_hourly_spend": float,
    "threshold_5min": float,
    "threshold_projected_hourly": float,
    "top_operations": list,
    "top_models": list,
    "window_start": iso_datetime,
    "window_end": iso_datetime,
}
```

## Acceptance Criteria

- [ ] Cost source queries `llm_traces` using `timestamp` and `cost`.
- [ ] Cost source does not query `api_costs`.
- [ ] Threshold breach creates normalized alert event with `severity`.
- [ ] Cost-runaway `dedupe_key` uses UTC date and hour.
- [ ] No alert event is returned when thresholds are not breached.
- [ ] Tests cover no-breach, warning breach, critical breach, and dedupe key format.

## Dependencies

- FEATURE-056.
- FEATURE-057.

## Test Plan

Create tests:

```text
tests/bugops/test_llm_traces_cost_source.py
```

Test cases:

- No traces → no alert.
- Spend below thresholds → no alert.
- Projected hourly threshold only → warning alert.
- 5-minute threshold breach → critical alert.
- Dedupe key format is `llm_traces:cost_runaway:YYYY-MM-DD:HH`.
- Metric payload includes top operations and top models.

## Manual Verification

Insert sample `llm_traces` records into local/test Mongo with current timestamps and costs above threshold. Run:

```bash
BUGOPS_ENABLED=true python -m crypto_news_aggregator.bugops.monitor
```

Expected: one `bug_alert_events` document and one `bug_cases` document.

## Rollback Plan

Disable with `BUGOPS_ENABLED=false`. No production app path depends on this source.

## Completion Summary

- Actual complexity:
- Key decisions made:
- Deviations from plan:
