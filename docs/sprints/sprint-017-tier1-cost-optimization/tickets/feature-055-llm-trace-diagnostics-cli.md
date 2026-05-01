---
id: FEATURE-055
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-01
updated: 2026-05-01
---

# Trace Analysis Layer for LLM Observability

## Problem/Opportunity

TASK-088 rebuilds the `llm_traces` write path so traces contain richer structured fields.

However, rich trace data is not useful unless it can be inspected without writing manual MongoDB aggregation queries every time.

The system needs a simple trace analysis layer that answers:

- Which operations cost the most?
- Which models cost the most?
- Which operations fail most often?
- Which calls are slow?
- Is caching working?
- Is model routing being overridden?
- How much does briefing generation, critique, and refinement cost?
- Are smoke/test traces separated from production traces?

This feature should provide a compact CLI report over `llm_traces`.

This is not a dashboard ticket. This is not a UI ticket. This is not an eval framework ticket.

---

## Proposed Solution

Add a script:

```text
scripts/analyze_traces.py
```

The script queries MongoDB `llm_traces` and prints a compact JSON report.

The report should support:

```bash
python scripts/analyze_traces.py --days 1
python scripts/analyze_traces.py --days 7
python scripts/analyze_traces.py --days 1 --include-smoke
```

Default behavior:

- Look back 1 day.
- Exclude smoke traces where `is_smoke == true`.
- Read only from `llm_traces`.
- Never write to MongoDB.
- Never delete MongoDB documents.
- Never mutate application data.

---

## User Story

As the system owner, I want a single trace analysis command so that I can understand LLM cost, failures, cache behavior, routing overrides, and briefing self-refine behavior without manually writing MongoDB queries.

---

## Dependencies

- TASK-088 must be completed first.
- `llm_traces` must contain the TASK-088 schema.
- MongoDB connection must be available through existing `MONGODB_URI`.

---

## Files to Add

Add only this file:

```text
scripts/analyze_traces.py
```

Do not modify API routes.
Do not modify the frontend.
Do not add a dashboard.
Do not add a scheduled task.

---

## Output Contract

The script must print JSON with this exact top-level shape:

```json
{
  "window": {
    "days": 1,
    "include_smoke": false,
    "start": "ISO timestamp",
    "end": "ISO timestamp"
  },
  "totals": {
    "calls": 0,
    "cost": 0.0,
    "input_tokens": 0,
    "output_tokens": 0,
    "errors": 0,
    "cache_hits": 0,
    "routing_overrides": 0,
    "avg_duration_ms": 0.0,
    "error_rate": 0.0,
    "cache_hit_rate": 0.0,
    "routing_override_rate": 0.0
  },
  "by_operation": [],
  "by_model": [],
  "by_provider": [],
  "errors": [],
  "slowest_calls": [],
  "cache": {
    "by_operation": []
  },
  "routing": {
    "overrides": []
  },
  "briefing_phases": []
}
```

All percentage/rate fields should be represented as decimals between 0 and 1.

Example:

```json
"cache_hit_rate": 0.25
```

Do not print markdown.
Do not print prose before or after the JSON.
Do not output Python repr.

---

## Exact Script Implementation

Create `scripts/analyze_traces.py` with the following implementation.

```python
#!/usr/bin/env python3
"""
Analyze LLM traces from MongoDB.

Read-only script.
Does not write, update, or delete MongoDB documents.

Usage:
    python scripts/analyze_traces.py --days 1
    python scripts/analyze_traces.py --days 7
    python scripts/analyze_traces.py --days 1 --include-smoke
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from pymongo import MongoClient


DB_NAME = "crypto_news"
COLLECTION_NAME = "llm_traces"


def _json_default(value: Any) -> str:
    """JSON serializer for datetimes and unknown values."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _rate(numerator: float, denominator: float) -> float:
    """Safe decimal rate helper."""
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _build_match(start: datetime, include_smoke: bool) -> Dict[str, Any]:
    """Build base Mongo match query."""
    match: Dict[str, Any] = {
        "timestamp": {"$gte": start},
    }

    if not include_smoke:
        match["is_smoke"] = {"$ne": True}

    return match


def _aggregate_one(collection, pipeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return first aggregate result or empty dict."""
    results = list(collection.aggregate(pipeline))
    return results[0] if results else {}


def _aggregate_many(collection, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return all aggregate results as a list."""
    return list(collection.aggregate(pipeline))


def get_totals(collection, match: Dict[str, Any]) -> Dict[str, Any]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": None,
                "calls": {"$sum": 1},
                "cost": {"$sum": "$cost"},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "cache_hits": {"$sum": {"$cond": ["$cached", 1, 0]}},
                "routing_overrides": {"$sum": {"$cond": ["$routing_overridden", 1, 0]}},
                "avg_duration_ms": {"$avg": "$duration_ms"},
            }
        },
    ]

    result = _aggregate_one(collection, pipeline)

    calls = result.get("calls", 0) or 0
    errors = result.get("errors", 0) or 0
    cache_hits = result.get("cache_hits", 0) or 0
    routing_overrides = result.get("routing_overrides", 0) or 0

    return {
        "calls": calls,
        "cost": round(result.get("cost", 0.0) or 0.0, 6),
        "input_tokens": result.get("input_tokens", 0) or 0,
        "output_tokens": result.get("output_tokens", 0) or 0,
        "errors": errors,
        "cache_hits": cache_hits,
        "routing_overrides": routing_overrides,
        "avg_duration_ms": round(result.get("avg_duration_ms", 0.0) or 0.0, 2),
        "error_rate": _rate(errors, calls),
        "cache_hit_rate": _rate(cache_hits, calls),
        "routing_override_rate": _rate(routing_overrides, calls),
    }


def get_by_operation(collection, match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$operation",
                "calls": {"$sum": 1},
                "cost": {"$sum": "$cost"},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "cache_hits": {"$sum": {"$cond": ["$cached", 1, 0]}},
                "routing_overrides": {"$sum": {"$cond": ["$routing_overridden", 1, 0]}},
                "avg_duration_ms": {"$avg": "$duration_ms"},
            }
        },
        {"$sort": {"cost": -1, "calls": -1}},
    ]

    rows = _aggregate_many(collection, pipeline)

    output = []
    for row in rows:
        calls = row.get("calls", 0) or 0
        output.append({
            "operation": row.get("_id"),
            "calls": calls,
            "cost": round(row.get("cost", 0.0) or 0.0, 6),
            "input_tokens": row.get("input_tokens", 0) or 0,
            "output_tokens": row.get("output_tokens", 0) or 0,
            "errors": row.get("errors", 0) or 0,
            "cache_hits": row.get("cache_hits", 0) or 0,
            "routing_overrides": row.get("routing_overrides", 0) or 0,
            "avg_duration_ms": round(row.get("avg_duration_ms", 0.0) or 0.0, 2),
            "error_rate": _rate(row.get("errors", 0) or 0, calls),
            "cache_hit_rate": _rate(row.get("cache_hits", 0) or 0, calls),
            "routing_override_rate": _rate(row.get("routing_overrides", 0) or 0, calls),
        })

    return output


def get_by_model(collection, match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$model",
                "calls": {"$sum": 1},
                "cost": {"$sum": "$cost"},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "avg_duration_ms": {"$avg": "$duration_ms"},
            }
        },
        {"$sort": {"cost": -1, "calls": -1}},
    ]

    rows = _aggregate_many(collection, pipeline)

    return [
        {
            "model": row.get("_id"),
            "calls": row.get("calls", 0) or 0,
            "cost": round(row.get("cost", 0.0) or 0.0, 6),
            "input_tokens": row.get("input_tokens", 0) or 0,
            "output_tokens": row.get("output_tokens", 0) or 0,
            "errors": row.get("errors", 0) or 0,
            "avg_duration_ms": round(row.get("avg_duration_ms", 0.0) or 0.0, 2),
            "error_rate": _rate(row.get("errors", 0) or 0, row.get("calls", 0) or 0),
        }
        for row in rows
    ]


def get_by_provider(collection, match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$provider",
                "calls": {"$sum": 1},
                "cost": {"$sum": "$cost"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "avg_duration_ms": {"$avg": "$duration_ms"},
            }
        },
        {"$sort": {"cost": -1, "calls": -1}},
    ]

    rows = _aggregate_many(collection, pipeline)

    return [
        {
            "provider": row.get("_id"),
            "calls": row.get("calls", 0) or 0,
            "cost": round(row.get("cost", 0.0) or 0.0, 6),
            "errors": row.get("errors", 0) or 0,
            "avg_duration_ms": round(row.get("avg_duration_ms", 0.0) or 0.0, 2),
            "error_rate": _rate(row.get("errors", 0) or 0, row.get("calls", 0) or 0),
        }
        for row in rows
    ]


def get_recent_errors(collection, match: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    error_match = dict(match)
    error_match["status"] = "error"

    cursor = collection.find(
        error_match,
        {
            "_id": 0,
            "trace_id": 1,
            "timestamp": 1,
            "operation": 1,
            "provider": 1,
            "model": 1,
            "error_type": 1,
            "error": 1,
            "duration_ms": 1,
            "task_id": 1,
            "briefing_id": 1,
            "phase": 1,
            "iteration": 1,
        },
    ).sort("timestamp", -1).limit(limit)

    return list(cursor)


def get_slowest_calls(collection, match: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    cursor = collection.find(
        match,
        {
            "_id": 0,
            "trace_id": 1,
            "timestamp": 1,
            "operation": 1,
            "provider": 1,
            "model": 1,
            "duration_ms": 1,
            "cost": 1,
            "cached": 1,
            "task_id": 1,
            "briefing_id": 1,
            "phase": 1,
            "iteration": 1,
        },
    ).sort("duration_ms", -1).limit(limit)

    return list(cursor)


def get_cache_by_operation(collection, match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$operation",
                "calls": {"$sum": 1},
                "cache_hits": {"$sum": {"$cond": ["$cached", 1, 0]}},
                "cache_misses": {"$sum": {"$cond": ["$cached", 0, 1]}},
            }
        },
        {"$sort": {"cache_hits": -1, "calls": -1}},
    ]

    rows = _aggregate_many(collection, pipeline)

    output = []
    for row in rows:
        calls = row.get("calls", 0) or 0
        output.append({
            "operation": row.get("_id"),
            "calls": calls,
            "cache_hits": row.get("cache_hits", 0) or 0,
            "cache_misses": row.get("cache_misses", 0) or 0,
            "cache_hit_rate": _rate(row.get("cache_hits", 0) or 0, calls),
        })

    return output


def get_routing_overrides(collection, match: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    routing_match = dict(match)
    routing_match["routing_overridden"] = True

    cursor = collection.find(
        routing_match,
        {
            "_id": 0,
            "trace_id": 1,
            "timestamp": 1,
            "operation": 1,
            "provider": 1,
            "requested_model": 1,
            "model": 1,
            "actual_model": 1,
            "task_id": 1,
            "briefing_id": 1,
            "phase": 1,
            "iteration": 1,
        },
    ).sort("timestamp", -1).limit(limit)

    return list(cursor)


def get_briefing_phases(collection, match: Dict[str, Any]) -> List[Dict[str, Any]]:
    briefing_match = dict(match)
    briefing_match["briefing_id"] = {"$ne": None}

    pipeline = [
        {"$match": briefing_match},
        {
            "$group": {
                "_id": {
                    "operation": "$operation",
                    "phase": "$phase",
                    "iteration": "$iteration",
                },
                "calls": {"$sum": 1},
                "cost": {"$sum": "$cost"},
                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "avg_duration_ms": {"$avg": "$duration_ms"},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
            }
        },
        {"$sort": {"_id.phase": 1, "_id.iteration": 1}},
    ]

    rows = _aggregate_many(collection, pipeline)

    return [
        {
            "operation": row.get("_id", {}).get("operation"),
            "phase": row.get("_id", {}).get("phase"),
            "iteration": row.get("_id", {}).get("iteration"),
            "calls": row.get("calls", 0) or 0,
            "cost": round(row.get("cost", 0.0) or 0.0, 6),
            "errors": row.get("errors", 0) or 0,
            "avg_duration_ms": round(row.get("avg_duration_ms", 0.0) or 0.0, 2),
            "input_tokens": row.get("input_tokens", 0) or 0,
            "output_tokens": row.get("output_tokens", 0) or 0,
        }
        for row in rows
    ]


def build_report(days: int, include_smoke: bool) -> Dict[str, Any]:
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI is not set")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    match = _build_match(start=start, include_smoke=include_smoke)

    try:
        report = {
            "window": {
                "days": days,
                "include_smoke": include_smoke,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            "totals": get_totals(collection, match),
            "by_operation": get_by_operation(collection, match),
            "by_model": get_by_model(collection, match),
            "by_provider": get_by_provider(collection, match),
            "errors": get_recent_errors(collection, match),
            "slowest_calls": get_slowest_calls(collection, match),
            "cache": {
                "by_operation": get_cache_by_operation(collection, match),
            },
            "routing": {
                "overrides": get_routing_overrides(collection, match),
            },
            "briefing_phases": get_briefing_phases(collection, match),
        }
    finally:
        client.close()

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze LLM traces from MongoDB.")
    parser.add_argument("--days", type=int, default=1, help="Number of days to look back.")
    parser.add_argument(
        "--include-smoke",
        action="store_true",
        help="Include smoke/test traces where is_smoke is true.",
    )

    args = parser.parse_args()

    if args.days <= 0:
        raise ValueError("--days must be greater than 0")

    report = build_report(days=args.days, include_smoke=args.include_smoke)
    print(json.dumps(report, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
```

---

## Verification

### Compile check

Run:

```bash
python -m compileall scripts/analyze_traces.py
```

### Execute report

Run:

```bash
python scripts/analyze_traces.py --days 1
```

Expected:

- Outputs valid JSON.
- Does not print markdown.
- Does not write to MongoDB.
- Does not delete anything.

### Execute smoke-inclusive report

Run:

```bash
python scripts/analyze_traces.py --days 1 --include-smoke
```

Expected:

- Outputs valid JSON.
- Includes traces where `is_smoke == true`.

### Validate JSON shape

Run:

```bash
python scripts/analyze_traces.py --days 1 > /tmp/trace-report.json
python -m json.tool /tmp/trace-report.json > /dev/null
```

Expected:

- Exit code 0.

---

## Acceptance Criteria

- [ ] Adds `scripts/analyze_traces.py`.
- [ ] Script reads only from `llm_traces`.
- [ ] Script does not write, update, or delete MongoDB documents.
- [ ] Script supports `--days`.
- [ ] Script supports `--include-smoke`.
- [ ] Default behavior excludes smoke traces.
- [ ] Output is valid JSON only.
- [ ] Output includes `window`.
- [ ] Output includes `totals`.
- [ ] Output includes `by_operation`.
- [ ] Output includes `by_model`.
- [ ] Output includes `by_provider`.
- [ ] Output includes recent `errors`.
- [ ] Output includes `slowest_calls`.
- [ ] Output includes cache metrics by operation.
- [ ] Output includes routing override examples.
- [ ] Output includes briefing phase metrics.
- [ ] Script compiles with `python -m compileall`.
- [ ] Script output passes `python -m json.tool`.

---

## Open Questions

- [ ] Should a later ticket expose this report through an admin API endpoint?
- [ ] Should a later ticket save daily reports to a collection for history?
- [ ] Should a later ticket generate a markdown summary for sprint docs?

Do not resolve these in this feature.

---

## Implementation Notes

Do not add a frontend dashboard.

Do not add an API route.

Do not add scheduled jobs.

Do not mutate the database.

This feature is intentionally a read-only CLI report.

---

## Completion Summary

- Actual complexity:
- Key decisions made:
- Deviations from plan:
