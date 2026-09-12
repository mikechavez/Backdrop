"""
LLM tracing schema, indexes, and query helpers.

Traces are written by LLMGateway._write_trace() (gateway.py).
This module handles schema validation, index setup, and analysis queries.
"""

import logging
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..core.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "llm_traces"
TTL_DAYS = 30


async def ensure_trace_indexes(
    db: AsyncIOMotorDatabase, retention_days: int | None = None
) -> None:
    """Ensure trace indexes and enforce the configured TTL without hiding errors."""
    if retention_days is None:
        retention_days = get_settings().LLM_TRACE_RETENTION_DAYS
    if retention_days <= 0:
        raise ValueError("LLM_TRACE_RETENTION_DAYS must be greater than zero")

    collection = db[COLLECTION_NAME]

    ttl_seconds = retention_days * 86400
    existing = await collection.index_information()
    timestamp_ttl = next(
        (
            (name, spec)
            for name, spec in existing.items()
            if spec.get("key") == [("timestamp", 1)]
            and "expireAfterSeconds" in spec
        ),
        None,
    )
    if timestamp_ttl and timestamp_ttl[1].get("expireAfterSeconds") != ttl_seconds:
        await db.command(
            "collMod",
            COLLECTION_NAME,
            index={"keyPattern": {"timestamp": 1}, "expireAfterSeconds": ttl_seconds},
        )
    elif not timestamp_ttl:
        # If a non-TTL timestamp index already exists, use collMod to add TTL
        # without dropping/rebuilding an index on production data.
        timestamp_index = next(
            (
                spec
                for spec in existing.values()
                if spec.get("key") == [("timestamp", 1)]
            ),
            None,
        )
        if timestamp_index:
            await db.command(
                "collMod",
                COLLECTION_NAME,
                index={"keyPattern": {"timestamp": 1}, "expireAfterSeconds": ttl_seconds},
            )
        else:
            await collection.create_index(
                [("timestamp", 1)],
                expireAfterSeconds=ttl_seconds,
            )

    indexes = [
        ([("operation", 1)], {}),
        ([("operation", 1), ("timestamp", -1)], {}),
        ([("trace_id", 1)], {"unique": True}),
        ([("model", 1), ("timestamp", -1)], {}),
        ([("provider", 1), ("timestamp", -1)], {}),
        ([("status", 1), ("timestamp", -1)], {}),
        ([("cached", 1), ("timestamp", -1)], {}),
        ([("briefing_id", 1), ("phase", 1), ("iteration", 1)], {}),
    ]
    for keys, options in indexes:
        matching_index = next(
            (spec for spec in existing.values() if spec.get("key") == keys), None
        )
        if matching_index is None:
            await collection.create_index(keys, **options)
        elif options.get("unique") and not matching_index.get("unique", False):
            raise RuntimeError(
                "llm_traces trace_id index exists without the required unique constraint; "
                "resolve duplicate trace IDs and migrate the index explicitly"
            )

    logger.info("llm_traces indexes ensured; ttl_days=%s", retention_days)


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
