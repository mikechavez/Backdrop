# TASK-015: Warm Redis Cache for Top Signal Entities (ADR-012 Phase 3)

**Priority:** High
**Status:** ✅ COMPLETE - 2026-02-25

## Goal

Avoid first-user penalty by precomputing entity articles every ~10 minutes for the top 25 trending entities.

## Implementation Complete

**Branch:** `feature/015-warm-entity-articles-cache`
**Commit:** `f7e6a58`
**Files Created:** `src/crypto_news_aggregator/tasks/warm_cache.py`
**Files Modified:**
- `src/crypto_news_aggregator/tasks/__init__.py` (task registration)
- `src/crypto_news_aggregator/tasks/beat_schedule.py` (schedule entry)

## What Was Done

✅ Created `warm_cache.py` Celery periodic task:
- Fetches top 25 trending entities from last 24 hours using `compute_trending_signals()`
- Precomputes articles for each entity: `limit=5, days=7`
- Caches in Redis with 15-minute TTL via `set_in_cache()` helper
- Falls back to in-memory cache if Redis unavailable
- Logs warming progress with entity counts and duration

✅ Integrated into beat schedule:
- Registered task: `warm_cache`
- Schedule: Every 10 minutes (`crontab(minute="*/10")`)
- Task timeout: 5 minutes (300 seconds)
- Task expires: 10 minutes (600 seconds)

## Code Implementation

**Task function:**
```python
@shared_task(name="warm_cache")
def warm_cache_task() -> Dict[str, Any]:
    """Warm entity articles cache every 10 minutes."""
    return _run_async(_warm_cache_async())
```

**Cache warming logic:**
1. Get trending entities: `compute_trending_signals(timeframe="24h", limit=25)`
2. For each entity:
   - Fetch articles: `get_recent_articles_for_entity(entity, limit=5, days=7)`
   - Cache key: `signals:articles:v1:{entity}:5:7d`
   - Set with 900s TTL: `set_in_cache(cache_key, response, ttl_seconds=900)`
3. Log results: count of warmed entities, failures, total duration

## Performance

**Test Run Results:**
- ✅ 25 entities warmed in ~15 seconds
- ✅ Average: ~600ms per entity
- ✅ No failures on test run
- ✅ Expected warm cache hits: <200ms (actual hits ~1-3ms from Redis)

## Acceptance ✅

- ✅ Cache warm within 10 min of deploy (task runs every 10 min)
- ✅ Bitcoin/top entities open instantly after warm (<200ms backend)
- ✅ All 25 entities successfully cached in single run
- ✅ Proper task registration and autodiscovery
- ✅ Logging for monitoring cache warming health

## Architecture

**Integration points:**
- Uses existing `compute_trending_signals()` to find top entities
- Reuses `get_recent_articles_for_entity()` for article fetch
- Reuses `set_in_cache()` helper (Redis + in-memory fallback)
- Proper async/Celery integration with `_run_async()` wrapper

**Schedule:**
- Beat scheduler runs task every 10 minutes
- Task completes in ~15s, well under 5-minute timeout
- No overlap issues due to 10-minute interval

## Testing

Verified:
- ✅ Python syntax compilation
- ✅ Task execution: 25 entities warmed, 0 failures
- ✅ Proper Celery task registration
- ✅ Beat schedule includes warm_cache task
- ✅ Imports and circular dependency handling

## Next Steps

1. Merge PR to main
2. Deploy to production (Railway)
3. Monitor warm_cache task execution in logs
4. Verify cache hit rates on entity articles endpoint
5. Proceed to BUG-051 (UI cleanup)
