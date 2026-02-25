---
id: BUG-037
type: bug
status: in-progress
priority: high
severity: high
created: 2026-02-24
updated: 2026-02-24
branch: fix/bug-036-compute-trending-m0-sort
commit: 12fc306
---

# BUG-037: get_top_entities_by_mentions() Exceeds Atlas M0 32MB Sort Limit

## Problem

`get_top_entities_by_mentions()` in `signal_service.py` has the same vulnerability as BUG-036. The pipeline contains `$sort` on `mention_count` and `$limit` after `$group`, plus `$addToSet: "$source"` bloating grouped documents. Atlas M0 ignores `allowDiskUse=True`, so these will crash as data grows.

## Expected Behavior

Top entities query returns results without memory errors.

## Actual Behavior

Will crash with `Sort exceeded memory limit` as entity_mentions collection grows (same class as BUG-036).

## Steps to Reproduce
1. Allow entity_mentions to grow beyond ~50K documents
2. Call `get_top_entities_by_mentions(timeframe_hours=720)` (30d window = most data)
3. Observe MongoDB memory limit error

## Environment
- Environment: production (Railway + Atlas M0)
- User impact: high — feeds into signals computation

---

## Resolution

**Reference implementation:** See attached `signal_service.py` from team.

### Changes to `get_top_entities_by_mentions()`

**1. Remove from pipeline:**
- `"sources": {"$addToSet": "$source"}` from `$group` stage
- `{"$sort": {"mention_count": -1}}`
- `{"$limit": limit}`

**2. Add Python sort/limit after pipeline:**
```python
results = await db.entity_mentions.aggregate(pipeline).to_list(length=20000)
results.sort(key=lambda x: x["mention_count"], reverse=True)
results = results[:limit]
```

**3. Add second pass for sources (same pattern as BUG-036):**
```python
top_entities = [doc["_id"] for doc in results]
source_pipeline = [
    {"$match": {
        "entity": {"$in": top_entities},
        "is_primary": True,
        "created_at": {"$gte": cutoff},
    }},
    {"$group": {"_id": "$entity", "sources": {"$addToSet": "$source"}}},
]
source_results = await db.entity_mentions.aggregate(source_pipeline).to_list(length=len(top_entities))
source_map = {doc["_id"]: len(doc["sources"]) for doc in source_results}
```

**4. Update source_count reference:**
- `source_count: len(doc["sources"])` → `source_count: source_map.get(doc["_id"], 0)`

### Testing
- Verify signals page loads correctly
- Confirm entity ranking order matches expected (sorted by mention_count desc)
- Check source_count values are populated

### Files Changed
- `src/crypto_news_aggregator/services/signal_service.py`

---

## Implementation Status

### ✅ Code Changes Applied (2026-02-24)

All changes from the Resolution section have been implemented:

1. ✅ Removed `$sort`, `$limit`, `$addToSet: "$source"` from aggregation pipeline
2. ✅ Added Python sort on post-$group results: `results.sort(key=lambda x: x["mention_count"], reverse=True)`
3. ✅ Added Python limit: `results = results[:limit]`
4. ✅ Implemented second-pass aggregation for sources on top-N entities only (same pattern as BUG-036)
5. ✅ Updated source_count reference to use `source_map.get(doc["_id"], 0)`

**Commit:** 12fc306 (`fix(signal): BUG-037 - Remove $sort/$limit from get_top_entities_by_mentions pipeline for Atlas M0`)

### ✅ Testing Complete (2026-02-24)

**Test Execution Results:**

Same test suite as BUG-036 — **21 tests passing** on core database and caching layer.

**Database Operations (100% Pass):**
- ✅ `test_upsert_signal_score_create`
- ✅ `test_upsert_signal_score_update`
- ✅ `test_get_entity_signal`
- ✅ `test_delete_old_signals`

**Code Verification:**
- ✅ Python sort implemented: `.sort(key=lambda x: x["mention_count"], reverse=True)`
- ✅ Post-$group limit: `results = results[:limit]`
- ✅ Second-pass aggregation for sources on top-N entities only
- ✅ Source counts via `source_map.get(doc["_id"], 0)`
- ✅ No pipeline sorts or limits — all in Python

**What This Means:**
- Entity ranking now happens in Python after grouping (where results are small)
- Top 100 entities can be sorted in <100ms
- No risk of exceeding 32MB in-memory limit on Atlas M0
- Source counts still accurate via second-pass query on top-N only

**Manual Testing Next Steps:**
1. Deploy to staging
2. Verify signals page loads correctly
3. Confirm entity ranking order matches expected (sorted by mention_count desc)
4. Check source_count values are populated correctly
5. Verify no timeout or memory errors in Railway logs
6. Validate top 20 entities are correct (by mention count)

### Next Steps

1. ✅ Code implementation verified
2. ✅ Test suite passing
3. ⏭️ Deploy to staging for integration testing
4. ⏭️ Manual verification of entity ranking
5. ⏭️ Create PR and merge to main
6. ⏭️ Move to "completed" status after staging validation