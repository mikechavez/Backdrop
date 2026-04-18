"""
LLM cost tracking service.

Tracks API costs to MongoDB for monitoring and optimization.
Supports Anthropic Claude models with token-based pricing.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# --- Cached budget state ---
# Eliminates per-call DB reads and the sync/async bridge problem.
# All callers read from this cache. A single async refresh updates it.
_budget_cache = {
    "daily_cost": 0.0,
    "status": "ok",                 # "ok" | "degraded" | "hard_limit"
    "monthly_cost": 0.0,            # NEW
    "monthly_status": "ok",         # NEW: "ok" | "degraded" | "hard_limit"
    "monthly_alert_sent": False,    # NEW: idempotency for 75% Slack alert
    "monthly_alert_month": None,    # NEW: tracks which UTC month the alert was sent for
    "last_checked": 0.0,            # timestamp
    "ttl": 30,                      # seconds between DB reads
}


class CostTracker:
    """
    Tracks LLM API costs to MongoDB.

    Features:
    - Token-based cost calculation
    - Support for multiple Anthropic models
    - Cache hit/miss tracking
    - Async MongoDB persistence
    """

    # Anthropic pricing as of March 2026
    # Prices per 1 million tokens
    PRICING = {
        "claude-haiku-4-5-20251001": {
            "input": 1.00,   # $1.00 per 1M input tokens
            "output": 5.00,  # $5.00 per 1M output tokens
        },
        "claude-sonnet-4-5-20250929": {
            "input": 3.00,
            "output": 15.00,
        },
        "claude-opus-4-6": {
            "input": 15.00,
            "output": 75.00,
        },
    }

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize cost tracker.

        Args:
            db: MongoDB database instance
        """
        self.db = db
        self.collection = db.api_costs

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate cost for an API call.

        Args:
            model: Model name (e.g., "claude-haiku-4-5-20251001")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD

        Raises:
            ValueError: If model not in pricing table
        """
        if model not in self.PRICING:
            logger.warning(f"Unknown model '{model}', defaulting to Haiku pricing")
            # Default to Haiku if model unknown
            pricing = self.PRICING["claude-haiku-4-5-20251001"]
        else:
            pricing = self.PRICING[model]

        # Calculate cost: (tokens / 1,000,000) * price_per_million
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        total_cost = input_cost + output_cost

        return round(total_cost, 6)  # Round to 6 decimal places

    async def track_call(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False,
        cache_key: Optional[str] = None
    ) -> float:
        """
        Track an LLM API call to the database.

        Args:
            operation: Operation type (e.g., "entity_extraction")
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached: Whether this was a cache hit
            cache_key: Cache key if applicable

        Returns:
            Cost in USD
        """
        # Calculate cost (cache hits are free)
        cost = 0.0 if cached else self.calculate_cost(model, input_tokens, output_tokens)

        # Prepare document
        doc = {
            "timestamp": datetime.now(timezone.utc),
            "operation": operation,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "cached": cached,
        }

        if cache_key:
            doc["cache_key"] = cache_key

        # Write to database (async, non-blocking)
        try:
            await self.collection.insert_one(doc)

            logger.info(
                f"Tracked {operation} call: {model}, "
                f"{input_tokens}+{output_tokens} tokens, "
                f"${cost:.4f} (cached={cached})"
            )
        except Exception as e:
            logger.error(f"Failed to track cost: {e}")
            # Don't raise - tracking failures shouldn't break LLM operations

        return cost

    async def get_daily_cost(self, days: int = 1) -> float:
        """
        Get total cost for the specified calendar day (UTC).

        For days=1 (default), returns cost for today (00:00-23:59 UTC).
        For days=2, returns cost for yesterday, etc.

        Queries llm_traces (the single source of truth for budget enforcement).
        llm_traces contains complete and correct data for all LLM calls (both
        sync and async paths write here). See BUG-079 for context.

        Args:
            days: Number of calendar days back (1=today, 2=yesterday, etc.)

        Returns:
            Total cost in USD
        """
        now = datetime.now(timezone.utc)

        # Calculate start of the target calendar day in UTC
        # days=1 → today 00:00 UTC
        # days=2 → yesterday 00:00 UTC
        start_of_day = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        pipeline = [
            {"$match": {"timestamp": {"$gte": start_of_day}}},
            {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
        ]

        result = await self.db.llm_traces.aggregate(pipeline).to_list(1)

        return result[0]["total"] if result else 0.0

    async def get_monthly_cost(self) -> float:
        """
        Get total cost for current month.

        Queries llm_traces (the single source of truth for budget enforcement).
        See BUG-079 for context.

        Returns:
            Total cost in USD
        """
        start_of_month = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        pipeline = [
            {"$match": {"timestamp": {"$gte": start_of_month}}},
            {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
        ]

        result = await self.db.llm_traces.aggregate(pipeline).to_list(1)

        return result[0]["total"] if result else 0.0

    async def get_cost_by_operation(self, days: int = 1) -> dict:
        """
        Get total cost broken down by operation type.

        Queries llm_traces (the single source of truth for budget enforcement).
        See BUG-079 for context.

        Args:
            days: Number of days to look back (default: 1)

        Returns:
            Dict mapping operation names to costs (e.g., {"sentiment_analysis": 1.23, "entity_extraction": 4.56})
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$operation",
                "cost": {"$sum": "$cost"},
                "calls": {"$sum": 1}
            }},
            {"$sort": {"cost": -1}}
        ]

        results = await self.db.llm_traces.aggregate(pipeline).to_list(None)

        return {item["_id"]: {"cost": item["cost"], "calls": item["calls"]} for item in results}

    async def get_cost_by_model(self, days: int = 1) -> dict:
        """
        Get total cost broken down by model.

        Queries llm_traces (the single source of truth for budget enforcement).
        See BUG-079 for context.

        Args:
            days: Number of days to look back (default: 1)

        Returns:
            Dict mapping model names to costs
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$model",
                "cost": {"$sum": "$cost"},
                "calls": {"$sum": 1}
            }},
            {"$sort": {"cost": -1}}
        ]

        results = await self.db.llm_traces.aggregate(pipeline).to_list(None)

        return {item["_id"]: {"cost": item["cost"], "calls": item["calls"]} for item in results}

    async def refresh_budget_cache(self) -> dict:
        """
        Refresh the module-level budget cache from the database.

        Called periodically (every ~30s) rather than on every LLM call.
        Evaluates both daily and monthly spend against limits.
        Returns the updated cache dict.
        """
        from ..core.config import get_settings
        settings = get_settings()

        try:
            daily_cost = await self.get_daily_cost(days=1)
            monthly_cost = await self.get_monthly_cost()
        except Exception as e:
            logger.error(f"Failed to refresh budget cache: {e}")
            _budget_cache["status"] = "degraded"
            _budget_cache["monthly_status"] = "degraded"
            _budget_cache["last_checked"] = time.time()
            return _budget_cache

        # Daily evaluation (existing)
        hard_limit = settings.LLM_DAILY_HARD_LIMIT
        soft_limit = settings.LLM_DAILY_SOFT_LIMIT
        _budget_cache["daily_cost"] = daily_cost

        if daily_cost >= hard_limit:
            _budget_cache["status"] = "hard_limit"
        elif daily_cost >= soft_limit:
            _budget_cache["status"] = "degraded"
        else:
            _budget_cache["status"] = "ok"

        # Monthly evaluation (NEW)
        monthly_hard = settings.ANTHROPIC_MONTHLY_API_LIMIT
        monthly_soft = monthly_hard * 0.75
        _budget_cache["monthly_cost"] = monthly_cost

        if monthly_cost >= monthly_hard:
            _budget_cache["monthly_status"] = "hard_limit"
            logger.warning(
                f"MONTHLY HARD LIMIT reached: ${monthly_cost:.4f} >= ${monthly_hard:.2f}"
            )
        elif monthly_cost >= monthly_soft:
            _budget_cache["monthly_status"] = "degraded"
            # Fire Slack alert once per month at 75% crossing
            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if _budget_cache.get("monthly_alert_month") != current_month:
                await self._send_monthly_alert(monthly_cost, monthly_hard)
                _budget_cache["monthly_alert_month"] = current_month
        else:
            _budget_cache["monthly_status"] = "ok"

        _budget_cache["last_checked"] = time.time()

        logger.info(
            f"[CACHE REFRESH] daily=${daily_cost:.4f}/{hard_limit:.2f} ({_budget_cache['status']}), "
            f"monthly=${monthly_cost:.4f}/{monthly_hard:.2f} ({_budget_cache['monthly_status']})"
        )

        return _budget_cache

    async def _send_monthly_alert(self, monthly_cost: float, monthly_hard: float) -> None:
        """Send Slack alert at 75% monthly threshold. Idempotent via cache month tracking."""
        try:
            from .slack_service import send_slack_message
            pct = (monthly_cost / monthly_hard) * 100
            msg = (
                f"[BUDGET ALERT] Monthly API spend at {pct:.0f}% of ceiling: "
                f"${monthly_cost:.2f} / ${monthly_hard:.2f}. "
                f"Non-critical operations will be blocked."
            )
            await send_slack_message(msg)
        except Exception as e:
            logger.error(f"Failed to send monthly budget alert: {e}")

    def is_critical_operation(self, operation: str) -> bool:
        """
        Determine if an operation is critical (allowed during soft limit).

        Critical operations (allowed during degraded mode):
        - briefing_generation: Core product output
        - briefing_generate: Primary briefing generation LLM call
        - briefing_critique: Quality check during self-refine loop (part of briefing pipeline)
        - briefing_refine: Refinement pass during self-refine loop (part of briefing pipeline)
        - entity_extraction: Required for pipeline continuity

        Non-critical operations (blocked during degraded mode):
        - health_check: Operations/monitoring ping (should not consume budget)
        - theme_extraction
        - sentiment_analysis
        - relevance_scoring
        - article_enrichment_batch
        - narrative_enrichment (discover_narrative_from_article)
        """
        CRITICAL_OPERATIONS = {
            "briefing_generation",
            "briefing_generate",
            "briefing_critique",
            "briefing_refine",
            "entity_extraction",
        }
        return operation in CRITICAL_OPERATIONS


# Global instance (initialized by dependency injection)
_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker(db: AsyncIOMotorDatabase) -> CostTracker:
    """
    Get or create cost tracker instance.

    Args:
        db: MongoDB database instance

    Returns:
        CostTracker instance
    """
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker(db)
    return _cost_tracker


async def refresh_budget_if_stale() -> None:
    """
    Refresh the budget cache if it's older than its TTL.

    Called from async contexts (enrichment pipeline, briefing agent).
    Safe to call frequently -- it no-ops if the cache is fresh.
    """
    if time.time() - _budget_cache["last_checked"] > _budget_cache["ttl"]:
        try:
            from ..db.mongodb import mongo_manager
            db = await mongo_manager.get_async_database()
            tracker = get_cost_tracker(db)
            await tracker.refresh_budget_cache()
        except Exception as e:
            logger.error(f"Budget cache refresh failed: {e}")


def check_llm_budget(operation: str = "") -> tuple[bool, str]:
    """
    Synchronous budget check against the cached state.

    This is the function that all LLM call sites use. No DB call,
    no async, no event loop gymnastics. Just reads from cache.

    Args:
        operation: Operation name for critical/non-critical classification

    Returns:
        Tuple of (allowed, reason):
        - (True, "ok"): Proceed normally
        - (True, "degraded"): Over soft limit, but operation is critical
        - (False, "soft_limit"): Over soft limit, non-critical operation blocked
        - (False, "hard_limit"): Over hard limit, all operations blocked
        - (False, "monthly_hard_limit"): Monthly hard limit hit, all operations blocked
        - (False, "monthly_soft_limit"): Monthly soft limit hit, non-critical operation blocked
        - (True, "no_data"): Cache never populated, fail open with warning
    """
    status = _budget_cache["status"]
    monthly_status = _budget_cache["monthly_status"]
    age = time.time() - _budget_cache["last_checked"]

    logger.debug(
        f"[BUDGET CHECK] operation={operation}, status={status}, "
        f"monthly_status={monthly_status}, "
        f"daily_cost=${_budget_cache['daily_cost']:.4f}, "
        f"monthly_cost=${_budget_cache['monthly_cost']:.4f}, age={age:.1f}s"
    )

    # If the cache has never been populated, fail open but warn
    if _budget_cache["last_checked"] == 0.0:
        logger.warning(
            f"Budget cache not yet populated. Allowing '{operation}' (fail open)."
        )
        return True, "no_data"

    # If the cache is extremely stale (>5 min), treat as degraded
    if age > 300:
        logger.warning(
            f"Budget cache stale ({age:.0f}s). Treating as degraded for '{operation}'."
        )
        status = "degraded"
        monthly_status = "degraded"

    # Monthly hard limit overrides everything
    if monthly_status == "hard_limit":
        logger.warning(
            f"LLM call blocked: monthly hard limit. operation='{operation}', "
            f"monthly_cost=${_budget_cache['monthly_cost']:.4f}"
        )
        return False, "monthly_hard_limit"

    # Daily hard limit
    if status == "hard_limit":
        logger.warning(
            f"LLM call blocked: daily hard limit. operation='{operation}', "
            f"daily_cost=${_budget_cache['daily_cost']:.4f}"
        )
        return False, "hard_limit"

    # Degraded mode: either daily OR monthly soft breach triggers it
    is_degraded = status == "degraded" or monthly_status == "degraded"
    if is_degraded:
        tracker = CostTracker.__new__(CostTracker)
        is_critical = tracker.is_critical_operation(operation)
        if is_critical:
            reason = "monthly_degraded" if monthly_status == "degraded" else "degraded"
            return True, reason
        else:
            reason = "monthly_soft_limit" if monthly_status == "degraded" else "soft_limit"
            logger.warning(f"Soft limit active ({reason}): blocking non-critical '{operation}'")
            return False, reason

    return True, "ok"
