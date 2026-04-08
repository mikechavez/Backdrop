---
id: TASK-037
type: feature
status: complete
priority: critical
complexity: low
created: 2026-04-08
updated: 2026-04-08
completed: 2026-04-08
---

# Tracing Schema — llm_traces Collection + MongoDB Indexes

## Problem/Opportunity

With all LLM calls flowing through the gateway (TASK-036), we need a structured trace record for every call. This gives us cost attribution by operation, call volume analysis, and latency tracking. The `quality` placeholder fields make Sprint 14's eval system a drop-in addition.

## Proposed Solution

Define the trace schema, create the `llm_traces` MongoDB collection with appropriate indexes, and ensure the gateway writes to it on every call. The schema is already embedded in TASK-036's `_write_trace` method — this ticket formalizes it, adds indexes, and adds a query helper for the burn-in analysis (TASK-041).

## Acceptance Criteria

- [ ] MongoDB collection `llm_traces` is created on app startup (via index creation)
- [ ] Indexes created: `timestamp` (descending, for time-range queries), `operation` (for grouping), compound `(operation, timestamp)` for filtered time queries
- [ ] TTL index on `timestamp` field: 30 days (auto-cleanup, traces are operational not archival)
- [ ] Trace document schema validated by unit test asserting all required fields present
- [ ] Query helper function `get_traces_summary(days=1)` returns cost/calls/tokens grouped by operation — this is the function TASK-041 burn-in will call
- [ ] Unit tests for: index creation, trace document shape, summary query

## Dependencies

- TASK-036 (gateway writes traces; this ticket defines what it writes)

## Implementation Notes

### Trace Document Schema

```python
{
    "trace_id": "uuid-string",           # Unique per LLM call
    "operation": "briefing_generate",     # Caller-assigned label
    "timestamp": datetime(UTC),           # When the call was made
    "model": "claude-sonnet-4-5-20250929",
    "input_tokens": 1200,
    "output_tokens": 400,
    "cost": 0.0096,                       # USD, calculated by CostTracker
    "duration_ms": 1500.3,
    "error": None,                        # String if call failed, else None
    # Sprint 14 placeholders — not enforced yet
    "quality": {
        "passed": None,                   # bool once eval system exists
        "score": None,                    # float 0-1
        "checks": [],                     # list of check results
    },
}
```

### File: `src/crypto_news_aggregator/llm/tracing.py`

```python
"""
LLM tracing schema, indexes, and query helpers.

Traces are written by LLMGateway._write_trace() (gateway.py).
This module handles schema validation, index setup, and analysis queries.
"""

import logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

COLLECTION_NAME = "llm_traces"
TTL_DAYS = 30


async def ensure_trace_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes on llm_traces collection. Safe to call repeatedly."""
    collection = db[COLLECTION_NAME]
    await collection.create_index("timestamp", expireAfterSeconds=TTL_DAYS * 86400)
    await collection.create_index("operation")
    await collection.create_index([("operation", 1), ("timestamp", -1)])
    logger.info("llm_traces indexes ensured")


async def get_traces_summary(db: AsyncIOMotorDatabase, days: int = 1) -> list[dict]:
    """
    Get cost/calls/tokens grouped by operation for the last N days.
    Used by TASK-041 burn-in analysis.

    Returns list of dicts:
        [{"operation": "briefing_generate", "total_cost": 0.15,
          "call_count": 10, "total_input_tokens": 12000,
          "total_output_tokens": 4000, "avg_duration_ms": 1500.0}]
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    collection = db[COLLECTION_NAME]

    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$operation",
            "total_cost": {"$sum": "$cost"},
            "call_count": {"$sum": 1},
            "total_input_tokens": {"$sum": "$input_tokens"},
            "total_output_tokens": {"$sum": "$output_tokens"},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "error_count": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}},
        }},
        {"$sort": {"total_cost": -1}},
    ]

    results = await collection.aggregate(pipeline).to_list(None)
    for r in results:
        r["operation"] = r.pop("_id")
    return results
```

### Index initialization

Add to app startup (wherever `ensure_indexes` is called, likely `main.py` or `app.py`):
```python
from crypto_news_aggregator.llm.tracing import ensure_trace_indexes
# inside startup:
await ensure_trace_indexes(db)
```

### Test file: `tests/test_tracing.py`

1. `test_ensure_indexes_creates_expected` — call `ensure_trace_indexes`, query `list_indexes()`, assert 3 custom indexes exist
2. `test_trace_document_shape` — insert a sample trace, read it back, assert all fields present with correct types
3. `test_get_traces_summary` — insert 5 traces across 2 operations, call `get_traces_summary(days=1)`, assert correct grouping and sums

## Open Questions

- None

## Completion Summary
- Actual complexity: Low (as estimated)
- Key decisions made: Schema matches gateway's _write_trace() exactly; TTL set to 30 days for operational traces (not archival)
- Deviations from plan: None
- Commit: b6a60bd
- Files: src/crypto_news_aggregator/llm/tracing.py (57 lines), main.py (wired indexes), tests/test_tracing.py (4 tests, all passing)