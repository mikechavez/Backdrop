"""
LLM cost tracking service.

Tracks API costs to MongoDB for monitoring and optimization.
Supports Anthropic Claude models with token-based pricing.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class CostTracker:
    """
    Tracks LLM API costs to MongoDB.

    Features:
    - Token-based cost calculation
    - Support for multiple Anthropic models
    - Cache hit/miss tracking
    - Async MongoDB persistence
    """

    # Anthropic pricing as of February 2026
    # Prices per 1 million tokens
    PRICING = {
        "claude-haiku-4-5-20251001": {
            "input": 1.00,   # $1.00 per 1M input tokens
            "output": 5.00,  # $5.00 per 1M output tokens
        },
        "claude-sonnet-4-20250514": {
            "input": 3.00,
            "output": 15.00,
        },
        "claude-sonnet-4-5-20250929": {
            "input": 3.00,
            "output": 15.00,
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
        Get total cost for the last N days.

        Args:
            days: Number of days to look back

        Returns:
            Total cost in USD
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
        ]

        result = await self.collection.aggregate(pipeline).to_list(1)

        return result[0]["total"] if result else 0.0

    async def get_monthly_cost(self) -> float:
        """
        Get total cost for current month.

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

        result = await self.collection.aggregate(pipeline).to_list(1)

        return result[0]["total"] if result else 0.0


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
