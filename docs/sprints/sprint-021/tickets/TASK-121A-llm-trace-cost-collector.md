---
ticket_id: TASK-121A
title: Collect LLM Trace and Cost Evidence
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-121a-llm-trace-cost-collector
effort_estimate: small
---

# TASK-121A: Collect LLM Trace and Cost Evidence

## Problem Statement

The Evidence Pack has no visibility into LLM activity at the time of an incident. Many production failures — including BUG-064 — are caused by cost control behavior, budget enforcement, or LLM routing issues. Without trace data in the Evidence Pack, the InvestigationProvider cannot reason about whether the failure was LLM-related.

---

## Context

`llm_traces` is the single source of truth for all LLM cost, routing, and budget activity in Backdrop. It is written by `gateway.py` after every LLM call, regardless of operation type.

**Critical field names** (from `50-data-model.md` — these are exact, not approximate):
- Timestamp field: `timestamp` — NOT `created_at` (does not exist on this collection)
- Cost field: `cost` — NOT `cost_usd`
- TTL: 30 days on `timestamp` index

**llm_traces document shape:**
```javascript
{
  "_id": ObjectId("..."),
  "operation": "briefing_generate",
  "model": "claude-haiku-4-5-20251001",
  "input_tokens": 1200,
  "output_tokens": 800,
  "cost": 0.00031,
  "timestamp": ISODate("..."),
  "cached": false
}
```

The collector queries `llm_traces` for the window surrounding the BugCase. This is deterministic — no LLM involved.

Can run in parallel with TASK-117, TASK-118, TASK-119, and TASK-121 — no external dependencies.

Use `EvidenceReferenceAllocator` for reference IDs.

---

## Task

1. Create `LLMTraceCollector` at `bugops/evidence/collectors/llm_traces.py`
2. Register with `EvidenceCollector`
3. Write unit tests

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/collectors/llm_traces.py
tests/bugops/test_llm_trace_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/evidence/collector.py  (register collector)
src/crypto_news_aggregator/bugops/models.py              (add LLMTraceSummary nested model)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/llm/tracing.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### New nested model to add to models.py

```python
class LLMTraceSummary(BaseModel):
    """Summary of LLM activity during the BugCase window."""
    window_start: datetime
    window_end: datetime
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Aggregate stats
    total_calls: int = 0
    total_cost: float = 0.0        # Sum of llm_traces.cost (NOT cost_usd)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cached_calls: int = 0
    
    # Per-operation breakdown
    operations: dict = Field(default_factory=dict)
    # Shape: {"briefing_generate": {"calls": 4, "cost": 0.0012, "last_at": datetime}}
    
    # Budget events
    budget_events: list[dict] = Field(default_factory=list)
    # Each: {"operation": str, "event": "soft_limit_reached|hard_limit_reached",
    #        "cost_at_event": float, "timestamp": datetime}
    
    # Recent traces (last 10 within window, most recent first)
    recent_traces: list[dict] = Field(default_factory=list)
    # Each: {"operation": str, "model": str, "cost": float,
    #        "input_tokens": int, "output_tokens": int,
    #        "cached": bool, "timestamp": datetime}
```

### LLMTraceCollector

Implements `EvidenceCollectorBase`. `collector_name = "llm_traces"`.

```python
LOOKBACK_MINUTES = 60  # Extend window to capture pre-incident LLM activity

class LLMTraceCollector:
    
    def __init__(self, db):
        """db: Motor async database instance"""
        self.db = db
    
    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        # Extend window further back — LLM activity precedes failures
        window_start = bugcase.first_seen_at - timedelta(minutes=LOOKBACK_MINUTES)
        window_end = bugcase.last_seen_at or bugcase.first_seen_at
        
        # Query llm_traces using "timestamp" field (NOT "created_at")
        traces_cursor = self.db["llm_traces"].find({
            "timestamp": {
                "$gte": window_start,
                "$lte": window_end,
            }
        }).sort("timestamp", -1)
        
        traces = await traces_cursor.to_list(length=500)
        
        if not traces:
            await store.update_evidence_pack_section(pack_id, {
                "llm_trace_summary": LLMTraceSummary(
                    window_start=window_start,
                    window_end=window_end,
                ).model_dump(),
            })
            return
        
        # Aggregate stats
        total_cost = sum(t.get("cost", 0.0) for t in traces)   # "cost" not "cost_usd"
        total_input = sum(t.get("input_tokens", 0) for t in traces)
        total_output = sum(t.get("output_tokens", 0) for t in traces)
        cached_calls = sum(1 for t in traces if t.get("cached", False))
        
        # Per-operation breakdown
        operations: dict[str, dict] = {}
        for trace in traces:
            op = trace.get("operation", "unknown")
            if op not in operations:
                operations[op] = {"calls": 0, "cost": 0.0, "last_at": None}
            operations[op]["calls"] += 1
            operations[op]["cost"] += trace.get("cost", 0.0)
            ts = trace.get("timestamp")
            if ts and (operations[op]["last_at"] is None or ts > operations[op]["last_at"]):
                operations[op]["last_at"] = ts
        
        # Convert datetime to isoformat for storage
        for op_data in operations.values():
            if isinstance(op_data.get("last_at"), datetime):
                op_data["last_at"] = op_data["last_at"].isoformat()
        
        # Recent traces (last 10)
        recent_traces = [
            {
                "operation": t.get("operation", "unknown"),
                "model": t.get("model", "unknown"),
                "cost": t.get("cost", 0.0),
                "input_tokens": t.get("input_tokens", 0),
                "output_tokens": t.get("output_tokens", 0),
                "cached": t.get("cached", False),
                "timestamp": t["timestamp"].isoformat() if isinstance(t.get("timestamp"), datetime) else str(t.get("timestamp", "")),
            }
            for t in traces[:10]
        ]
        
        summary = LLMTraceSummary(
            window_start=window_start,
            window_end=window_end,
            total_calls=len(traces),
            total_cost=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            cached_calls=cached_calls,
            operations=operations,
            recent_traces=recent_traces,
        )
        
        # Add evidence references
        ref_cost = ref_allocator.next_ref()
        ref_ops = ref_allocator.next_ref()
        evidence_references = {
            ref_cost: {
                "description": f"LLM spend in window: ${total_cost:.4f} across {len(traces)} calls",
                "section": "llm_trace_summary",
                "field": "total_cost",
            },
            ref_ops: {
                "description": f"Operations in window: {list(operations.keys())}",
                "section": "llm_trace_summary",
                "field": "operations",
            },
        }
        
        await store.update_evidence_pack_section(pack_id, {
            "llm_trace_summary": summary.model_dump(),
            "evidence_references": evidence_references,
        })
```

### EvidencePack schema addition

Add `llm_trace_summary` field to `EvidencePackCreate` in `models.py`:

```python
llm_trace_summary: Optional[dict] = None
# Shape: LLMTraceSummary.model_dump()
```

This field was not in the original TASK-114 schema. TASK-114A schema review should be updated to include it — add to the BUG-064 schema mapping document.

### Registration in EvidenceCollector

```python
# In EvidenceCollector.__init__ or TASK-123 monitor wiring:
self.evidence_collector.register_collector(LLMTraceCollector(db=self.db))
```

The `db` parameter is the Motor async database instance already available in `BugOpsMonitor`.

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_llm_trace_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] Queries `llm_traces` using `timestamp` field (NOT `created_at`)
- [ ] Uses `cost` field for cost aggregation (NOT `cost_usd`)
- [ ] Window start is `first_seen_at - 60 minutes`
- [ ] Window end is `last_seen_at` (or `first_seen_at` if `last_seen_at` is None)
- [ ] Aggregates `total_calls`, `total_cost`, `total_input_tokens`, `total_output_tokens`, `cached_calls` correctly
- [ ] Per-operation breakdown includes call count, cost, and last timestamp
- [ ] `recent_traces` returns at most 10 traces, most recent first
- [ ] Handles zero traces in window — writes empty `LLMTraceSummary`, does not raise
- [ ] Adds two evidence references: one for cost, one for operations
- [ ] Uses `ref_allocator.next_ref()` — does not hardcode reference IDs
- [ ] `operations` dict correctly identifies `"provider_fallback"` operation name as anomaly indicator

---

## Acceptance Criteria

- [ ] `LLMTraceSummary` nested model added to `models.py`
- [ ] `llm_trace_summary` field added to `EvidencePackCreate`
- [ ] `LLMTraceCollector` queries `llm_traces` with correct field names (`timestamp`, `cost`)
- [ ] Zero traces handled gracefully
- [ ] Two evidence references added per collection
- [ ] Collector registered with `EvidenceCollector`
- [ ] TASK-114A schema mapping document updated to include `llm_trace_summary`
- [ ] All tests pass, no regressions

---

## Design Note

The BUG-064 Golden Incident would have been significantly easier to diagnose if this collector had existed. The Evidence Pack would have shown:

```
LLM activity in window (60 min before incident):
  total_calls: 12
  total_cost: $0.2954
  operations:
    briefing_generate: {calls: 8, cost: $0.24}
    entity_extraction: {calls: 4, cost: $0.055}
  recent_traces:
    - operation: briefing_generate, cost: $0.031, timestamp: 00:00:08
    - operation: briefing_generate, cost: $0.031, timestamp: 23:58:42
    ...
```

Combined with `config_evidence.llm_daily_soft_limit = $0.25`, this would have made the hypothesis confirmable from the Evidence Pack alone.

---

## Related Tickets

- TASK-114: Model (add `LLMTraceSummary` and `llm_trace_summary` field)
- TASK-114A: Schema review (update mapping to include `llm_trace_summary`)
- TASK-116: Framework (must be complete first)
- TASK-121: Config Evidence (complementary — config + traces together tell the full cost story)
- TASK-123: Monitor wiring (register this collector)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Deviations from plan:
