"""Bounded, idempotent MongoDB retention and storage diagnostics."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


def classify_storage_usage(
    percent_used: float | None, warning_percent: float, critical_percent: float
) -> str | None:
    """Classify an available estimate; missing metrics never become zero usage."""
    if percent_used is None:
        return None
    if percent_used >= critical_percent:
        return "critical"
    if percent_used >= warning_percent:
        return "warning"
    return None


async def storage_report(db: AsyncIOMotorDatabase, quota_mb: float | None) -> dict[str, Any]:
    """Return MongoDB storage estimates; dbStats is not an Atlas quota meter."""
    stats = await db.command("dbStats", scale=1)
    storage_value = stats.get("storageSize")
    index_value = stats.get("indexSize")
    has_storage_metrics = storage_value is not None and index_value is not None
    storage_bytes = int(storage_value) if has_storage_metrics else None
    index_bytes = int(index_value) if has_storage_metrics else None
    estimate_bytes = storage_bytes + index_bytes if has_storage_metrics else None
    percentage = None
    if estimate_bytes is not None and quota_mb and quota_mb > 0:
        percentage = estimate_bytes / (quota_mb * 1024 * 1024) * 100
    return {
        "database": stats.get("db"),
        "collections": int(stats.get("collections", 0) or 0),
        "data_bytes": int(stats.get("dataSize", 0) or 0),
        "storage_bytes": storage_bytes,
        "index_bytes": index_bytes,
        "estimated_used_bytes": estimate_bytes,
        "configured_quota_bytes": int(quota_mb * 1024 * 1024) if quota_mb else None,
        "estimated_percent_used": round(percentage, 2) if percentage is not None else None,
        "measurement": "MongoDB dbStats estimate; verify actual quota in Atlas",
    }


async def _bounded_delete(
    db: AsyncIOMotorDatabase,
    collection_name: str,
    query: dict[str, Any],
    batch_size: int,
    dry_run: bool,
    cutoff: datetime | None = None,
) -> dict[str, Any]:
    """Select and optionally delete at most batch_size explicit document IDs."""
    started = time.monotonic()
    collection = db[collection_name]
    matched = await collection.count_documents(query)
    cursor = collection.find(query, {"_id": 1}).sort("_id", 1).limit(batch_size)
    selected = await cursor.to_list(length=batch_size)
    ids = [doc["_id"] for doc in selected if "_id" in doc]
    deleted = 0
    if ids and not dry_run:
        result = await collection.delete_many({"_id": {"$in": ids}})
        deleted = int(result.deleted_count)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        "Mongo retention collection=%s cutoff=%s matched=%d selected=%d deleted=%d dry_run=%s duration_ms=%s",
        collection_name,
        cutoff.isoformat() if cutoff else "configured-expiry",
        matched,
        len(ids),
        deleted,
        dry_run,
        duration_ms,
    )
    return {
        "collection": collection_name,
        "cutoff": cutoff.isoformat() if cutoff else "configured-expiry",
        "matched_count": matched,
        "selected_count": len(ids),
        "deleted_count": deleted,
        "batch_size": batch_size,
        "dry_run": dry_run,
        "duration_ms": duration_ms,
    }


async def _unreferenced_tier3_query(
    db: AsyncIOMotorDatabase, cutoff: datetime, batch_size: int
) -> dict[str, Any]:
    """Build safe tier-3 filter while preserving every article referenced by narratives."""
    articles = db["articles"]
    base_query = {"relevance_tier": 3, "published_at": {"$lt": cutoff}}
    offset = 0
    safe_ids: list[Any] = []
    while len(safe_ids) < batch_size:
        candidates = await articles.find(
            base_query, {"_id": 1}
        ).sort("_id", 1).skip(offset).limit(batch_size).to_list(length=batch_size)
        if not candidates:
            break
        offset += len(candidates)
        candidate_ids = [doc["_id"] for doc in candidates]
        candidate_values = candidate_ids + [str(value) for value in candidate_ids]
        referenced: set[Any] = set()
        async for narrative in db["narratives"].find(
            {"article_ids": {"$in": candidate_values}}, {"article_ids": 1}
        ):
            referenced.update(narrative.get("article_ids", []))
        safe_ids.extend(
            value for value in candidate_ids
            if value not in referenced and str(value) not in referenced
        )
    return {"_id": {"$in": safe_ids[:batch_size]}}


async def run_retention_cleanup(
    db: AsyncIOMotorDatabase,
    settings: Any,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Run isolated, per-collection cleanup batches. Articles are disabled by default."""
    now = datetime.now(timezone.utc)
    batch_size = int(settings.MONGODB_CLEANUP_BATCH_SIZE)
    trace_cutoff = now - timedelta(days=settings.LLM_TRACE_RETENTION_DAYS)
    cache_cutoff = now - timedelta(days=settings.LLM_CACHE_RETENTION_DAYS)
    plans: list[tuple[str, dict[str, Any], datetime]] = [
        (
            "llm_traces",
            {"timestamp": {"$lt": trace_cutoff}},
            trace_cutoff,
        ),
        (
            "llm_cache",
            {
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {
                        "expires_at": {"$exists": False},
                        "cached_at": {"$lt": cache_cutoff},
                    },
                ]
            },
            cache_cutoff,
        ),
    ]

    if settings.ARTICLE_TIER3_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=settings.ARTICLE_TIER3_RETENTION_DAYS)
        try:
            safe_article_query = await _unreferenced_tier3_query(db, cutoff, batch_size)
            plans.append(("articles", safe_article_query, cutoff))
        except Exception as exc:
            logger.exception("Mongo retention collection=articles planning failed")
            article_error = {"collection": "articles", "error": type(exc).__name__}
        else:
            article_error = None
    else:
        article_error = {"collection": "articles", "status": "disabled_by_configuration"}

    results = []
    for collection_name, query, cutoff in plans:
        try:
            results.append(
                await _bounded_delete(
                    db, collection_name, query, batch_size, dry_run, cutoff=cutoff
                )
            )
        except Exception as exc:
            logger.exception("Mongo retention collection=%s failed", collection_name)
            results.append({"collection": collection_name, "error": type(exc).__name__})
    if article_error:
        results.append(article_error)
    return {"dry_run": dry_run, "batch_size_per_collection": batch_size, "results": results}
