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
    await collection.create_index("trace_id", unique=True)
    await collection.create_index([("model", 1), ("timestamp", -1)])
    await collection.create_index([("provider", 1), ("timestamp", -1)])
    await collection.create_index([("status", 1), ("timestamp", -1)])
    await collection.create_index([("cached", 1), ("timestamp", -1)])
    await collection.create_index([("briefing_id", 1), ("phase", 1), ("iteration", 1)])

    logger.info("llm_traces indexes ensured")


async def get_traces_summary(db: AsyncIOMotorDatabase, days: int = 1) -> list[dict]:
    """
    Get cost/calls/tokens grouped by operation for the last N days.
    Used by TASK-041 burn-in analysis.

    Returns list of dicts:
        [{"operation": "briefing_generate", "total_cost": 0.15,
          "call_count": 10, "total_input_tokens": 12000,
          "total_output_tokens": 4000, "avg_duration_ms": 1500.0,
          "error_rate": 0.0, "cache_hit_rate": 0.0, "routing_override_rate": 0.0}]
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
            "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
            "cache_hits": {"$sum": {"$cond": ["$cached", 1, 0]}},
            "routing_overrides": {"$sum": {"$cond": ["$routing_overridden", 1, 0]}},
        }},
        {"$sort": {"total_cost": -1}},
    ]

    results = await collection.aggregate(pipeline).to_list(None)
    for r in results:
        r["operation"] = r.pop("_id")
        call_count = r.get("call_count", 0) or 0
        r["error_rate"] = (r.get("error_count", 0) / call_count) if call_count else 0.0
        r["cache_hit_rate"] = (r.get("cache_hits", 0) / call_count) if call_count else 0.0
        r["routing_override_rate"] = (r.get("routing_overrides", 0) / call_count) if call_count else 0.0
    return results
