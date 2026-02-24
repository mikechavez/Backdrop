---
id: BUG-036
type: bug
status: in-progress
priority: high
severity: high
created: 2026-02-24
updated: 2026-02-24
branch: fix/bug-036-compute-trending-m0-sort
commit: 5dcfc6c
---

# BUG-036: compute_trending_signals() Exceeds Atlas M0 32MB Sort Limit

## Problem

`compute_trending_signals()` in `signal_service.py` crashes on Atlas M0 (free tier) because M0 **silently ignores** `allowDiskUse=True`. The pipeline has `$sort` and `$limit` stages after `$group` on computed fields (`current_mentions`), which cannot be covered by any index since those fields only exist as aggregation output. As data grows, these sorts exceed the 32MB in-memory limit.

Additionally, `$addToSet: "$source"` inside the main `$group` bloats per-entity documents, pushing the `$group` stage itself toward memory limits.

**This supersedes BUG-034's fix** (which added `allowDiskUse=True` — ineffective on M0).

## Expected Behavior

Signals page loads without `Sort exceeded memory limit` errors regardless of data volume.

## Actual Behavior

500 error on `/api/v1/signals/trending` with MongoDB error: `Sort exceeded memory limit of 33554432 bytes`.

## Steps to Reproduce
1. Allow entity_mentions collection to grow beyond ~50K documents
2. Hit `/api/v1/signals/trending?timeframe=7d`
3. Observe 500 error in Railway logs

## Environment
- Environment: production (Railway + Atlas M0)
- User impact: high — signals page completely broken

---

## Resolution

**Reference implementation:** See attached `signal_service.py` from team.

### Changes to `compute_trending_signals()`

**1. Remove from pipeline:**
- `"sources": {"$addToSet": "$source"}` from `$group` stage
- `{"$sort": {"current_mentions": -1}}`
- `{"$limit": limit * 2}`

**2. Add Python sort/limit after pipeline:**
```python
results = await db.entity_mentions.aggregate(pipeline).to_list(length=20000)
results.sort(key=lambda x: x["current_mentions"], reverse=True)
results = results[:limit * 2]
```

**3. Add second pass for sources (after sort/limit, top entities only):**
```python
top_entities = [doc["_id"] for doc in results]
source_pipeline = [
    {"$match": {
        "entity": {"$in": top_entities},
        "is_primary": True,
        "created_at": {"$gte": previous_period_start},
    }},
    {"$group": {"_id": "$entity", "sources": {"$addToSet": "$source"}}},
]
source_results = await db.entity_mentions.aggregate(source_pipeline).to_list(length=len(top_entities))
source_map = {doc["_id"]: len(doc["sources"]) for doc in source_results}
```

**4. Update source_count reference:**
- `source_count = len(doc["sources"])` → `source_count = source_map.get(entity, 0)`

### Why This Is Safe
Post-`$group` results are small (one doc per entity, a few hundred at most), so Python sort is instant. Moving `$addToSet` to a second pass on only top-N entities keeps grouped document sizes small.

### Testing
- `curl -s https://your-api-domain/api/v1/signals/trending?timeframe=7d&limit=5 | jq '.count'`
- Verify Railway logs have no `Sort exceeded memory limit` errors
- Confirm source_count values are non-zero for entities with multiple sources

### Files Changed
- `src/crypto_news_aggregator/services/signal_service.py`

---

## Implementation Status

### ✅ Code Changes Applied (2026-02-24)

All changes from the Resolution section have been implemented:

1. ✅ Removed `$sort`, `$limit`, `$addToSet: "$source"` from main pipeline
2. ✅ Added Python sort on post-$group results: `results.sort(key=lambda x: x["current_mentions"], reverse=True)`
3. ✅ Added Python limit: `results = results[:limit * 2]`
4. ✅ Implemented second-pass aggregation for sources on top-N entities only
5. ✅ Updated source_count reference to use `source_map.get(entity, 0)`

**Commit:** 5dcfc6c (`fix(signal): BUG-036 - Remove $sort/$limit from compute_trending_signals pipeline for Atlas M0`)

### ⚠️ Testing Required

The implementation is complete but **requires testing before merging**:

**Manual Testing Steps:**
1. Deploy to staging/test environment
2. Run: `curl -s https://your-api-domain/api/v1/signals/trending?timeframe=7d&limit=5 | jq '.count'`
3. Verify trending signals load without errors
4. Check Railway logs for no `Sort exceeded memory limit` errors
5. Confirm source_count values are non-zero for entities with multiple sources
6. Verify signal scores are calculated correctly

**Automated Testing:**
- [ ] Run `pytest tests/db/test_signal_scores.py` — verify signal calculations unchanged
- [ ] Run `pytest tests/api/test_signals.py` — verify API response structure unchanged
- [ ] Run `pytest tests/api/test_signals_caching.py` — verify caching layer works

**Load Testing (optional but recommended):**
- Simulate large entity_mentions collection (100K+ documents)
- Verify no timeout or memory errors on `/api/v1/signals/trending`

### Next Steps

1. Run test suite
2. Deploy to staging for integration testing
3. Monitor production deployment for errors
4. Move to "completed" status after successful testing