"""
Celery task for warming the entity articles cache.

This task runs every 10 minutes to precompute articles for the top 25 signal entities.
This avoids the first-user penalty when accessing the /signals/{entity}/articles endpoint.

Schedule: Every 10 minutes (defined in beat_schedule.py)
"""

import asyncio
import logging
import time
from typing import Dict, Any

from celery import shared_task

from crypto_news_aggregator.db.mongodb import initialize_mongodb, mongo_manager
from crypto_news_aggregator.services.signal_service import compute_trending_signals

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async code with proper event loop handling for Celery workers."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


async def _ensure_mongodb():
    """Ensure MongoDB is initialized."""
    try:
        db = await mongo_manager.get_async_database()
        return True
    except Exception:
        await initialize_mongodb()
        return True


async def _warm_cache_async() -> Dict[str, Any]:
    """
    Async implementation of cache warming.

    Fetches the top 25 trending entities and precomputes their articles
    in the Redis cache (with in-memory fallback).
    """
    # Import here to avoid circular imports
    from crypto_news_aggregator.api.v1.endpoints.signals import (
        get_recent_articles_for_entity,
        set_in_cache
    )

    start_time = time.time()
    await _ensure_mongodb()

    try:
        # Get top 25 trending entities from the last 24 hours
        logger.info("[WarmCache] Starting cache warm for top 25 entities")
        signals = await compute_trending_signals(timeframe="24h", limit=25)

        if not signals:
            logger.warning("[WarmCache] No trending signals found")
            return {
                "status": "completed",
                "entities_warmed": 0,
                "duration_seconds": time.time() - start_time,
                "message": "No trending signals found"
            }

        # Extract entity names from signals
        entities = [signal["entity"] for signal in signals]
        logger.info(f"[WarmCache] Top 25 entities: {entities}")

        # Warm cache for each entity with limit=5, days=7
        warmed_count = 0
        failed_count = 0

        for entity in entities:
            try:
                entity_start = time.time()
                articles = await get_recent_articles_for_entity(
                    entity=entity,
                    limit=5,
                    days=7
                )

                # Build response in the same format as the API
                response = {
                    "entity": entity,
                    "articles": articles,
                }

                # Cache the response for 15 minutes (900 seconds)
                cache_key = f"signals:articles:v1:{entity}:5:7d"
                set_in_cache(cache_key, response, ttl_seconds=900)

                entity_duration = time.time() - entity_start
                logger.info(
                    f"[WarmCache] Warmed cache for {entity}: "
                    f"{len(articles)} articles in {entity_duration:.2f}s"
                )
                warmed_count += 1

            except Exception as e:
                logger.error(f"[WarmCache] Failed to warm cache for {entity}: {e}")
                failed_count += 1
                continue

        total_duration = time.time() - start_time
        logger.info(
            f"[WarmCache] Cache warming completed: "
            f"{warmed_count} succeeded, {failed_count} failed in {total_duration:.2f}s"
        )

        return {
            "status": "completed",
            "entities_warmed": warmed_count,
            "entities_failed": failed_count,
            "duration_seconds": total_duration,
            "message": f"Warmed cache for {warmed_count}/{len(entities)} entities"
        }

    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"[WarmCache] Failed to warm cache: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "duration_seconds": total_duration,
        }


@shared_task(name="warm_cache")
def warm_cache_task() -> Dict[str, Any]:
    """
    Celery task to warm the entity articles cache.

    This task:
    1. Fetches the top 25 trending entities from the last 24 hours
    2. Precomputes articles (limit=5, days=7) for each entity
    3. Stores the results in Redis cache with 15-minute TTL

    This is scheduled to run every 10 minutes to ensure the cache
    is always warm for users accessing the signals page.

    Returns:
        Dictionary with status, number of entities warmed, and duration
    """
    return _run_async(_warm_cache_async())
