# BUG-045: Entity Articles Endpoint Time-Bound (7d cutoff)

**Priority:** Critical\
**Severity:** High\
**Status:** ✅ PR CREATED\
**Created:** 2026-02-25\
**Completed:** 2026-02-25 13:45:00Z

## Summary

`/api/v1/signals/{entity}/articles` took 10-45s for large entities (Bitcoin/Ethereum) due to unbounded article/mention scans. Fixed by enforcing 7-day cutoff at MongoDB query level.

## Solution Implemented

✅ **MongoDB Query Cutoff** (line 168-170)
- Added time-bound filter in `$match` stage: `"created_at": {"$gte": cutoff_date}`
- Applied cutoff **before** `$group` stage to prevent memory bloat
- Calculated as: `datetime.now() - timedelta(days=days)`

✅ **API Parameter Clamping** (line 623)
- `limit`: clamped to max 20
- `days`: clamped to max 7 (default 7)

✅ **Applied to Both Functions**
- `get_recent_articles_for_entity()` - single entity fetch
- `get_recent_articles_batch()` - batch fetch for trending signals

## Files Changed

- `src/crypto_news_aggregator/api/v1/endpoints/signals.py` (+35/-9)

## Acceptance Criteria

- ✅ Enforce 7-day cutoff at DB query level
- ✅ Apply cutoff **before** grouping/sorting
- ✅ Clamp `days≤7`, `limit≤20` for public API
- Expected: Cold <3s, warm <300ms (Bitcoin/Ethereum <2s cold)

## Implementation Details

### Commit
- **Hash:** bf601df
- **Branch:** fix/bug-045-entity-articles-time-bound
- **PR:** #203

### Code Changes

**get_recent_articles_for_entity():**
```python
async def get_recent_articles_for_entity(entity: str, limit: int = 5, days: int = 7):
    limit = min(limit, 20)  # Clamp to max 20
    days = min(days, 7)     # Clamp to max 7
    cutoff_date = datetime.now() - timedelta(days=days)
    pipeline = [
        {"$match": {
            "entity": entity,
            "created_at": {"$gte": cutoff_date}  # BUG-045: Time-bound at query level
        }},
        ...
    ]
```

**get_entity_articles() endpoint:**
```python
@router.get("/{entity}/articles")
async def get_entity_articles(
    entity: str,
    limit: int = Query(default=5, ge=1, le=20),
    days: int = Query(default=7, ge=1, le=7),
) -> Dict[str, Any]:
```

## Next Steps

- [ ] Merge PR #203
- [ ] Deploy to production (Railway)
- [ ] Monitor entity article latency in logs
- [ ] Proceed to FEATURE-049 (Redis cache)
