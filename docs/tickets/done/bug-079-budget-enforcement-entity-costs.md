---
id: BUG-079
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-14
updated: 2026-04-14
---

# Budget enforcement is blind to entity_extraction costs — hard limit not enforcing against true spend

## Problem

The budget enforcement system calls `get_daily_cost()` in `cost_tracker.py`, which queries the `api_costs` collection. `entity_extraction` (198 calls/day, $0.177/day) goes through the gateway's `call_sync()` path. In `call_sync()`, cost is calculated inline but only written to `llm_traces` via `_write_trace_sync()` — there is no `api_costs` write in the sync path.

`call_sync()` has a secondary manual cost write in `extract_entities_batch()` (lines 379–400 in `anthropic.py`) that schedules an async `tracker.track_call()` as a background task. This write targets `api_costs` with operation `entity_extraction` — but the task fires via `asyncio.create_task()` in a Celery worker context where the event loop may not be running. If the task is dropped (silently, no exception propagates), `entity_extraction` costs never reach `api_costs`.

The result: `api_costs` reports $0.957/day, `llm_traces` reports $1.134/day. The $1.00 hard limit reads from `api_costs` only and never triggers. The system believes it is under limit when actual Anthropic spend is already 13% over.

Secondary architectural issue: the `_tracked` async methods in `AnthropicProvider` (`analyze_sentiment_tracked`, `score_relevance_tracked`, `extract_themes_tracked`) route through the gateway (which writes to `llm_traces`) and then call `tracker.track_call()` manually afterward (which writes to `api_costs`). This is a partial double-write: same call, two records, two collection names, two different operation labels. BUG-068 was supposed to close this but the write pattern persists.

## Expected Behavior

`get_daily_cost()` returns a number that matches the actual Anthropic spend for the day. The hard limit enforces against that number. If actual spend is $1.134/day, the hard limit of $1.00 triggers.

## Actual Behavior

`get_daily_cost()` queries `api_costs` and returns $0.957/day. The hard limit never triggers. $0.177/day of real spend is invisible to the enforcement system.

## Steps to Reproduce

1. Aggregate actual spend from `llm_traces` (correct field is `timestamp`, not `created_at`):
   ```javascript
   db.llm_traces.aggregate([
     { $match: { timestamp: { $gte: new Date(Date.now() - 86400000) } } },
     { $group: { _id: null, total: { $sum: "$cost" } } }
   ])
   // Returns ~$1.134
   ```
2. Aggregate from `api_costs`:
   ```javascript
   db.api_costs.aggregate([
     { $match: { timestamp: { $gte: new Date(Date.now() - 86400000) } } },
     { $group: { _id: null, total: { $sum: "$cost" } } }
   ])
   // Returns ~$0.957
   ```
3. Note that `entity_extraction` has no entries in `api_costs`:
   ```javascript
   db.api_costs.find({ operation: "entity_extraction" }).count()
   // Returns 0
   ```
4. Confirm that `api_costs` is the collection `get_daily_cost()` queries in `cost_tracker.py` (line 141: `self.collection = db.api_costs`).

## Environment

- Environment: production (Railway)
- Services affected: CostTracker, LLMGateway (sync path), budget enforcement (all LLM call sites via `check_llm_budget()`)
- User impact: critical — the system's primary cost protection mechanism is silently broken. Actual spend exceeds hard limit with no enforcement response.

---

## Code Location

**`call_sync()` in gateway.py — sync cost write path (lines 592–602):**

```python
# src/crypto_news_aggregator/llm/gateway.py

def call_sync(self, ...) -> GatewayResponse:
    ...
    # Sync cost tracking: create tracker inline, write synchronously via pymongo
    cost = 0.0
    try:
        from ..services.cost_tracker import CostTracker as CT
        ct = CT.__new__(CT)
        cost = ct.calculate_cost(model, input_tokens, output_tokens)  # CALCULATES ONLY
    except Exception as e:
        logger.error(f"Sync cost calculation failed: {e}")

    # Write trace synchronously (blocking, but fire-and-forget semantics)
    self._write_trace_sync(trace_id, operation, model, input_tokens, output_tokens, cost, duration_ms)
    # ↑ writes to llm_traces only. No api_costs write anywhere in call_sync().
```

Compare to `call()` (async path), which correctly calls `_track_cost()`:

```python
# call() — line 481
cost = await self._track_cost(operation, model, input_tokens, output_tokens)
# _track_cost() calls tracker.track_call() → writes to api_costs ✓
await self._write_trace(...)
# _write_trace() writes to llm_traces ✓
# Async path writes to BOTH collections correctly.
```

**Manual async task in `extract_entities_batch()` — the fragile secondary write (anthropic.py lines 373–400):**

```python
# src/crypto_news_aggregator/llm/anthropic.py

# Track cost (async, non-blocking)
try:
    async def _track_entity_cost():
        db = await mongo_manager.get_async_database()
        tracker = CostTracker(db)
        await tracker.track_call(
            operation="entity_extraction",
            model=entity_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_track_entity_cost())   # May be dropped silently in Celery
        else:
            import threading
            threading.Thread(target=lambda: asyncio.run(_track_entity_cost()), daemon=True).start()
    except RuntimeError:
        import threading
        threading.Thread(...).start()
```

**`get_daily_cost()` in cost_tracker.py — queries api_costs only (line 141 + line 131):**

```python
def __init__(self, db):
    self.collection = db.api_costs   # line 141

async def get_daily_cost(self, days: int = 1) -> float:
    ...
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_of_day}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]
    result = await self.collection.aggregate(pipeline).to_list(1)  # queries api_costs only
    return result[0]["total"] if result else 0.0
```

---

## Resolution

**Status:** Open
**Fixed:** —
**Branch:** —
**Commit:** —

### Root Cause

`call_sync()` was written without a `_track_cost()` equivalent. The async `call()` correctly writes to both collections. The sync path calculates cost but only writes to `llm_traces`. The manual async task in `extract_entities_batch()` was added as a workaround but is unreliable in Celery worker contexts where event loop state is unpredictable. When the task drops, `api_costs` never receives the entry and the enforcement system is blind to that spend.

### Decision Required

Choose one collection as the single source of truth for budget enforcement. Document this decision in an ADR before implementation.

**Option A — Make `api_costs` the single source of truth:**

- Fix `call_sync()` to call a sync-compatible version of `tracker.track_call()` using pymongo directly (matching the pattern already used in `_write_trace_sync()`). This removes the need for the fragile async task in `extract_entities_batch()`.
- Remove manual `tracker.track_call()` calls from all `_tracked` async methods — gateway's `_track_cost()` already handles this for the async path.
- Keep `llm_traces` for latency, quality, and diagnostics only (not cost enforcement).
- Update `get_daily_cost()` to reflect this is now the canonical cost source.

**Option B (recommended) — Make `llm_traces` the single source of truth:**

- `llm_traces` already has complete and correct data for every call (both async and sync paths write here).
- Update `get_daily_cost()` to query `llm_traces` using the `timestamp` field instead of `api_costs`.
- Remove manual `tracker.track_call()` calls from `_tracked` async methods (eliminates the double-write).
- Remove the fragile async task from `extract_entities_batch()`.
- Prerequisite: BUG-078 must land first so all `llm_traces` entries have meaningful operation names before `llm_traces` is used for cost attribution.

Option B is lower risk because `llm_traces` already contains the correct complete data and requires only a query target change in `get_daily_cost()`. Option A requires adding a new sync write path to `call_sync()`.

### Changes Required (Option B)

**1. Update `get_daily_cost()` in `cost_tracker.py` to query `llm_traces`:**

```python
async def get_daily_cost(self, days: int = 1) -> float:
    now = datetime.now(timezone.utc)
    start_of_day = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_of_day}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]
    result = await self.db.llm_traces.aggregate(pipeline).to_list(1)
    return result[0]["total"] if result else 0.0
```

**2. Remove the fragile manual async task from `extract_entities_batch()` in `anthropic.py` (lines 373–400):**

The gateway's `_write_trace_sync()` already records the correct cost in `llm_traces` for every `call_sync()` invocation. The manual task is redundant under Option B and should be deleted.

**3. Remove manual `tracker.track_call()` calls from `_tracked` async methods in `anthropic.py`:**

The gateway's `_track_cost()` (called via `call()`) already writes to `api_costs`. Under Option B, `api_costs` is no longer the enforcement source, so the manual writes in `_tracked` methods become vestigial. Remove them to eliminate the double-write.

### Testing

After deploying:

1. Verify `get_daily_cost()` now returns true spend:
   ```javascript
   // llm_traces aggregate (truth)
   db.llm_traces.aggregate([
     { $match: { timestamp: { $gte: new Date(Date.now() - 86400000) } } },
     { $group: { _id: null, total: { $sum: "$cost" } } }
   ])
   // budget enforcement value
   // Call refresh_budget_cache() and check _budget_cache["daily_cost"]
   // Both numbers must match.
   ```
2. Verify `entity_extraction` costs are now visible in the enforcement total:
   ```javascript
   db.llm_traces.aggregate([
     { $match: {
       operation: "entity_extraction",
       timestamp: { $gte: new Date(Date.now() - 86400000) }
     }},
     { $group: { _id: null, cost: { $sum: "$cost" }, calls: { $sum: 1 } } }
   ])
   // Expected: ~198 calls, ~$0.177
   ```
3. Confirm the hard limit is now triggering correctly by checking logs for `HARD LIMIT reached` entries now that true spend ($1.134) is above $1.00.
4. Before enforcing, deploy TASK-071 threshold recalibration (soft $0.80, hard $1.20) to avoid immediately blocking production.

### Files to Change

- `src/crypto_news_aggregator/services/cost_tracker.py`
  - `get_daily_cost()` — change collection from `self.collection` (api_costs) to `self.db.llm_traces`
  - `get_cost_by_operation()` — update for consistency if also used in dashboard (TASK-069)
- `src/crypto_news_aggregator/llm/anthropic.py`
  - `extract_entities_batch()` — remove manual async cost tracking task (lines 373–400)
  - `_tracked` async methods — remove manual `tracker.track_call()` calls
- ADR document — record the Option A vs Option B decision and rationale before merging