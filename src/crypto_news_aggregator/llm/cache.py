"""
LLM Response Cache and Cost Tracking
Caches LLM API responses to avoid duplicate calls and reduce costs.
"""

import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase


class LLMResponseCache:
    """Cache LLM responses to avoid duplicate API calls"""
    
    def __init__(self, db: AsyncIOMotorDatabase, ttl_hours: int = 168):
        """
        Initialize cache with MongoDB database connection
        
        Args:
            db: MongoDB database instance
            ttl_hours: Time to live for cached responses (default: 1 week)
        """
        self.db = db
        self.ttl = timedelta(hours=ttl_hours)
        self.collection = db.llm_cache
        
        # Stats tracking
        self.hits = 0
        self.misses = 0
    
    def _get_cache_key(self, prompt: str, model: str) -> str:
        """
        Generate cache key from prompt and model
        
        Args:
            prompt: The prompt text
            model: The model name
        
        Returns:
            SHA-256 hash of the prompt+model combination
        """
        content = f"{model}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def get(self, prompt: str, model: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response if exists and not expired
        
        Args:
            prompt: The prompt text
            model: The model name
        
        Returns:
            Cached response dict or None if not found/expired
        """
        cache_key = self._get_cache_key(prompt, model)
        
        cached = await self.collection.find_one({
            "cache_key": cache_key,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if cached:
            self.hits += 1
            return cached["response"]
        
        self.misses += 1
        return None
    
    async def set(self, prompt: str, model: str, response: Dict[str, Any]) -> None:
        """
        Store response in cache
        
        Args:
            prompt: The prompt text
            model: The model name
            response: The API response to cache
        """
        cache_key = self._get_cache_key(prompt, model)
        
        await self.collection.update_one(
            {"cache_key": cache_key},
            {
                "$set": {
                    "cache_key": cache_key,
                    "model": model,
                    "response": response,
                    "created_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + self.ttl
                }
            },
            upsert=True
        )
    
    async def clear_expired(self) -> int:
        """
        Manually clear expired cache entries
        
        Returns:
            Number of deleted entries
        """
        result = await self.collection.delete_many({
            "expires_at": {"$lt": datetime.utcnow()}
        })
        return result.deleted_count
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dict with hit rate, total entries, etc.
        """
        total_entries = await self.collection.count_documents({})
        active_entries = await self.collection.count_documents({
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "total_entries": total_entries,
            "active_entries": active_entries,
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests
        }
    
    async def initialize_indexes(self) -> None:
        """Create required indexes for cache collection"""
        # Unique index on cache_key
        await self.collection.create_index(
            [("cache_key", 1)],
            unique=True
        )
        
        # TTL index for automatic cleanup
        await self.collection.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0
        )


class CostTracker:
    """Track API costs for monitoring and budgeting"""
    
    # Pricing per 1M tokens (as of February 2026)
    PRICING = {
        "claude-haiku-4-5-20251001": {
            "input": 1.0,
            "output": 5.0
        },
        "claude-sonnet-4-5-20250929": {
            "input": 3.0,
            "output": 15.0
        },
        "claude-sonnet-4-5-20250929": {
            "input": 3.0,
            "output": 15.0
        }
    }
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize cost tracker with MongoDB database"""
        self.db = db
        self.collection = db.api_costs
    
    async def log_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        operation: str = "unknown",
        cached: bool = False
    ) -> float:
        """
        Log an API call and calculate cost
        
        Args:
            model: Model name used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            operation: Type of operation (entity_extraction, narrative_summary, etc.)
            cached: Whether this was served from cache
        
        Returns:
            Cost in USD
        """
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        
        await self.collection.insert_one({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "operation": operation,
            "cached": cached,
            "timestamp": datetime.utcnow()
        })
        
        return cost
    
    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for a model call
        
        Args:
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
        
        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(model)
        if not pricing:
            # Default to Sonnet pricing if unknown
            pricing = self.PRICING["claude-sonnet-4-5-20250929"]
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    async def get_daily_costs(self, days: int = 7) -> list[Dict[str, Any]]:
        """
        Get daily cost breakdown
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of daily cost summaries
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date}}},
            {"$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "operation": "$operation"
                },
                "total_cost": {"$sum": "$cost"},
                "total_calls": {"$sum": 1},
                "cached_calls": {"$sum": {"$cond": ["$cached", 1, 0]}},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"}
            }},
            {"$sort": {"_id.date": 1}}
        ]
        
        results = await self.collection.aggregate(pipeline).to_list(None)
        return results
    
    async def get_monthly_summary(self) -> Dict[str, Any]:
        """
        Get current month's cost summary
        
        Returns:
            Dict with monthly totals and projections
        """
        # Get costs for current month
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_of_month}}},
            {"$group": {
                "_id": None,
                "total_cost": {"$sum": "$cost"},
                "total_calls": {"$sum": 1},
                "cached_calls": {"$sum": {"$cond": ["$cached", 1, 0]}},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"}
            }}
        ]
        
        result = await self.collection.aggregate(pipeline).to_list(1)
        
        if not result:
            return {
                "month_to_date": 0,
                "projected_monthly": 0,
                "days_elapsed": 0,
                "cache_hit_rate": 0
            }
        
        data = result[0]
        
        # Calculate projection
        days_elapsed = (datetime.utcnow() - start_of_month).days + 1
        days_in_month = 30  # Approximate
        projected = (data["total_cost"] / days_elapsed) * days_in_month
        
        # Cache hit rate
        cache_hit_rate = 0
        if data["total_calls"] > 0:
            cache_hit_rate = (data["cached_calls"] / data["total_calls"]) * 100
        
        return {
            "month_to_date": round(data["total_cost"], 2),
            "projected_monthly": round(projected, 2),
            "days_elapsed": days_elapsed,
            "total_calls": data["total_calls"],
            "cached_calls": data["cached_calls"],
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
            "input_tokens": data["input_tokens"],
            "output_tokens": data["output_tokens"]
        }
    
    async def initialize_indexes(self) -> None:
        """Create required indexes for cost tracking collection"""
        await self.collection.create_index([("timestamp", -1)])
        await self.collection.create_index([("operation", 1)])
        await self.collection.create_index([("model", 1)])
