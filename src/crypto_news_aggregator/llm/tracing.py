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
