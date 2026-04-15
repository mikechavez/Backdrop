# ADR-079: Budget Enforcement Single Source of Truth

**Status:** Accepted  
**Date:** 2026-04-14  
**Deciders:** Engineering Team  
**Implements:** BUG-079

## Context

The budget enforcement system had a critical blind spot: `entity_extraction` costs (~$0.177/day, 198 calls) were not being recorded to the `api_costs` collection, making them invisible to the hard limit enforcement.

The problem was architectural:
- Async `call()` path correctly wrote to both `llm_traces` and `api_costs`
- Sync `call_sync()` path calculated cost but only wrote to `llm_traces`, missing `api_costs`
- A fragile manual async task in `extract_entities_batch()` attempted to backfill `api_costs` via `asyncio.create_task()` in Celery worker contexts, but tasks were silently dropped when event loops weren't running

Result: Hard limit read from `api_costs` ($0.957/day) while actual spend was in `llm_traces` ($1.134/day) — 13% over without enforcement.

## Decision

**Use `llm_traces` as the single source of truth for budget enforcement.**

### Rationale

1. **Data Completeness**: `llm_traces` already contains all LLM calls from both sync and async paths with correct costs
2. **Simplicity**: One collection, one query, no double-write patterns or sync/async bridges
3. **Reliability**: No fragile async task scheduling or event loop state dependencies
4. **Prerequisite Met**: BUG-078 ensures all `llm_traces` entries have meaningful operation names
5. **Lower Risk**: Only changes query target, not write path — less surface area for bugs

### Alternatives Considered

**Option A: Make `api_costs` the source of truth**
- Would require adding a new sync write path to `call_sync()` matching `_write_trace_sync()` pattern
- Higher complexity: duplicates the sync MongoDB write logic
- Removes `llm_traces` from enforcement use (but kept for latency/quality diagnostics)
- Risk: Introduces new sync write path that could diverge from async path

**Option B (Selected): Make `llm_traces` the source of truth**
- `llm_traces` already has complete, correct data for all calls
- Only changes query target in `get_daily_cost()` and related methods
- Removes manual cost tracking calls from `_tracked` methods and `extract_entities_batch()`
- Lower risk, faster to implement, immediately solves the blind spot

## Implementation

### Changes to `cost_tracker.py`

Updated methods to query `llm_traces` instead of `api_costs`:
- `get_daily_cost()` — line 182: `await self.db.llm_traces.aggregate(pipeline).to_list(1)`
- `get_monthly_cost()` — line 209: `await self.db.llm_traces.aggregate(pipeline).to_list(1)`
- `get_cost_by_operation()` — line 235: `await self.db.llm_traces.aggregate(pipeline).to_list(1)`
- `get_cost_by_model()` — line 264: `await self.db.llm_traces.aggregate(pipeline).to_list(1)`

### Changes to `anthropic.py`

1. **Removed fragile async cost tracking** from `extract_entities_batch()` (lines 380-410)
   - Gateway's `_write_trace_sync()` already records to `llm_traces`
   - Manual `tracker.track_call()` via `asyncio.create_task()` was unreliable in Celery contexts

2. **Removed manual cost tracking** from `_tracked` async methods (3 occurrences):
   - `score_relevance_tracked()`
   - `analyze_sentiment_tracked()`
   - `extract_themes_tracked()`
   - Gateway's `_track_cost()` via `call()` already writes to `llm_traces`

### Test Updates

Updated all cost aggregation tests to write directly to `llm_traces`:
- `test_cost_tracker.py`: Updated daily/monthly cost tests
- `test_spend_logging_aggregation.py`: Updated operation/model aggregation tests
- `test_cost_controls_e2e.py`: Updated E2E tests
- `test_llm_cost_tracking.py`: Updated integration tests
- `test_bug_056_spend_cap.py`: Updated mock DB setup to include `llm_traces`

All 50 cost-related tests pass.

## Consequences

### Positive
- Hard limit now enforces against **true spend** ($1.134/day vs blind $0.957/day)
- Eliminates 110 lines of fragile async code from anthropic.py
- Single, reliable query path for all cost aggregations
- Entity extraction costs now visible to enforcement

### Negative
- `api_costs` collection is now write-only (only populated by legacy code and `tracker.track_call()`)
- Future code should not use `api_costs` for budget queries (but still populated for backward compatibility)

### Neutral
- `llm_traces` is retained for latency, quality, and diagnostic queries
- No changes to LLM call paths (gateway and provider behavior unchanged)

## Verification

After deployment, verify:

1. **Daily cost now includes entity_extraction**:
   ```javascript
   // llm_traces aggregate (truth)
   db.llm_traces.aggregate([
     { $match: { timestamp: { $gte: new Date(Date.now() - 86400000) } } },
     { $group: { _id: null, total: { $sum: "$cost" } } }
   ])
   // Should match refresh_budget_cache() output
   ```

2. **Entity extraction costs visible**:
   ```javascript
   db.llm_traces.aggregate([
     { $match: {
       operation: "entity_extraction",
       timestamp: { $gte: new Date(Date.now() - 86400000) }
     }},
     { $group: { _id: null, cost: { $sum: "$cost" }, calls: { $sum: 1 } } }
   ])
   // Expected: ~198 calls, ~$0.177/day
   ```

3. **Hard limit triggers correctly**:
   - Check logs for `HARD LIMIT reached` when true spend exceeds $1.00
   - Before enforcing, deploy TASK-071 threshold recalibration (soft $0.80, hard $1.20)

## References

- **BUG-079**: Budget enforcement is blind to entity_extraction costs
- **BUG-078**: RSS enrichment operation names (prerequisite)
- **TASK-071**: Threshold recalibration (post-fix deployment)
