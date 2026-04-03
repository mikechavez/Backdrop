"""
Health check endpoint for system monitoring.

Returns status of all subsystems: database, redis, LLM, data freshness.
No authentication required -- this is an ops/status endpoint.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...db.mongodb import mongo_manager
from ...core.redis_rest_client import redis_client
from ...core.config import get_settings
from ...services.heartbeat import get_heartbeat

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Individual health checks ---


async def check_database() -> dict:
    """Check MongoDB connectivity via admin ping."""
    start = time.monotonic()
    try:
        db = await mongo_manager.get_async_database()
        await db.command("ping")
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: database failed", exc_info=True)
        return {"status": "error", "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_redis() -> dict:
    """Check Redis (Upstash) connectivity via PING."""
    start = time.monotonic()
    try:
        pong = redis_client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if pong:
            return {"status": "ok", "latency_ms": latency_ms}
        return {"status": "error", "latency_ms": latency_ms, "error": "PING returned False"}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: redis failed", exc_info=True)
        return {"status": "error", "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_llm() -> dict:
    """Minimal LLM ping: cheapest model, max_tokens=1, no retry.

    Cost: ~0.0001 cents per check (1 input token + 1 output token on Haiku).
    """
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"status": "error", "error": "ANTHROPIC_API_KEY not set"}

    model = settings.ANTHROPIC_DEFAULT_MODEL
    start = time.monotonic()
    try:
        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ok"}],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "model": model, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: LLM ping failed", exc_info=True)
        return {"status": "error", "model": model, "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_data_freshness() -> dict:
    """Check if most recent article was ingested within 24 hours."""
    try:
        db = await mongo_manager.get_async_database()
        collection = db["articles"]
        latest = await collection.find_one(
            sort=[("published_at", -1)],
            projection={"published_at": 1, "title": 1},
        )
        if not latest:
            return {"status": "warning", "error": "No articles found in database"}

        published = latest.get("published_at")
        if not published:
            return {"status": "warning", "error": "Latest article has no published_at timestamp"}

        # Ensure timezone-aware comparison
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - published
        age_hours = round(age.total_seconds() / 3600, 1)

        if age > timedelta(hours=24):
            return {
                "status": "warning",
                "latest_article_age_hours": age_hours,
                "latest_article_title": latest.get("title", "unknown")[:80],
            }

        return {
            "status": "ok",
            "latest_article_age_hours": age_hours,
            "latest_article_title": latest.get("title", "unknown")[:80],
        }
    except Exception as e:
        logger.error("Health check: data freshness failed", exc_info=True)
        return {"status": "error", "error": str(e)[:100]}


# --- Main endpoint ---

# Critical checks: if these fail, system is unhealthy
CRITICAL_CHECKS = {"database", "llm"}


async def check_pipeline_heartbeats() -> dict:
    """Check if critical pipeline stages have recent heartbeats."""
    settings = get_settings()
    try:
        db = await mongo_manager.get_async_database()
        pipeline_ok = True
        pipeline_checks = {}

        # Check article fetch heartbeat
        fetch_hb = await get_heartbeat(db, "fetch_news")
        if fetch_hb is None:
            pipeline_checks["fetch_news"] = {
                "status": "warning",
                "message": "No heartbeat recorded yet (pipeline may not have run since deploy)",
            }
        else:
            age_seconds = (datetime.now(timezone.utc) - fetch_hb["last_success"]).total_seconds()
            if age_seconds > settings.HEARTBEAT_FETCH_NEWS_MAX_AGE:
                pipeline_ok = False
                pipeline_checks["fetch_news"] = {
                    "status": "critical",
                    "message": f"Last successful fetch was {age_seconds / 3600:.1f} hours ago",
                    "last_success": fetch_hb["last_success"].isoformat(),
                    "threshold_hours": settings.HEARTBEAT_FETCH_NEWS_MAX_AGE / 3600,
                }
            else:
                pipeline_checks["fetch_news"] = {
                    "status": "ok",
                    "last_success": fetch_hb["last_success"].isoformat(),
                    "last_summary": fetch_hb.get("last_result_summary", ""),
                }

        # Check briefing heartbeat
        briefing_hb = await get_heartbeat(db, "generate_briefing")
        if briefing_hb is None:
            pipeline_checks["generate_briefing"] = {
                "status": "warning",
                "message": "No heartbeat recorded yet",
            }
        else:
            age_seconds = (datetime.now(timezone.utc) - briefing_hb["last_success"]).total_seconds()
            if age_seconds > settings.HEARTBEAT_BRIEFING_MAX_AGE:
                pipeline_ok = False
                pipeline_checks["generate_briefing"] = {
                    "status": "critical",
                    "message": f"Last briefing was {age_seconds / 3600:.1f} hours ago",
                    "last_success": briefing_hb["last_success"].isoformat(),
                    "threshold_hours": settings.HEARTBEAT_BRIEFING_MAX_AGE / 3600,
                }
            else:
                pipeline_checks["generate_briefing"] = {
                    "status": "ok",
                    "last_success": briefing_hb["last_success"].isoformat(),
                    "last_summary": briefing_hb.get("last_result_summary", ""),
                }

        return {"ok": pipeline_ok, "checks": pipeline_checks}

    except Exception as e:
        logger.error("Health check: pipeline heartbeats failed", exc_info=True)
        return {
            "ok": False,
            "checks": {
                "error": {
                    "status": "error",
                    "message": f"Failed to check pipeline heartbeats: {str(e)[:100]}",
                }
            },
        }


@router.get("/health", response_model=Dict[str, Any], tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check for all Backdrop subsystems.

    Returns:
        - **healthy**: All checks pass
        - **degraded**: Non-critical checks failing (redis, data_freshness, pipeline warnings)
        - **unhealthy**: Critical checks failing (database, llm, stale pipeline)

    HTTP 500 is returned when pipeline is stale beyond thresholds (UptimeRobot alerts).
    No authentication required.
    """
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "llm": await check_llm(),
        "data_freshness": await check_data_freshness(),
    }

    # Check pipeline heartbeats
    pipeline_result = await check_pipeline_heartbeats()
    checks["pipeline"] = pipeline_result["checks"]
    pipeline_ok = pipeline_result["ok"]

    critical_failed = any(
        checks[name]["status"] == "error"
        for name in CRITICAL_CHECKS
        if name in checks
    )
    any_issue = any(
        checks[name].get("status") in ("error", "warning", "critical")
        for name in checks
        if name != "pipeline"  # pipeline is a dict of checks
    )

    # Pipeline critical failures mean the system is unhealthy
    if not pipeline_ok and any(
        check.get("status") == "critical" for check in checks["pipeline"].values()
    ):
        critical_failed = True

    if critical_failed:
        overall = "unhealthy"
    elif any_issue:
        overall = "degraded"
    else:
        overall = "healthy"

    response_body = {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    # Return 500 when pipeline is stale (triggers UptimeRobot alerts)
    if not pipeline_ok and any(
        check.get("status") == "critical" for check in checks["pipeline"].values()
    ):
        return JSONResponse(content=response_body, status_code=500)

    return response_body
