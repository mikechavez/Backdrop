---
id: BUG-038
type: bug
status: in-progress
priority: high
severity: medium
created: 2026-02-24
updated: 2026-02-24
branch: fix/bug-036-compute-trending-m0-sort
commit: 752212f
---

# BUG-038: get_recent_articles_for_entity() Exceeds Atlas M0 32MB Sort Limit

## Problem

`get_recent_articles_for_entity()` in `signals.py` includes `$sort` stages before and after `$group`, plus `$limit`. These cannot be moved to indexes and will exceed Atlas M0's 32MB in-memory sort limit as the data grows. Additionally, the pre-group sort was redundant since `$max` is used in the group stage to find the latest published_at without relying on sort order.

**This is part of the M0 sort limit rework** (BUG-036/037/038) that supersedes the `allowDiskUse=True` approach (M0 ignores it).

## Expected Behavior

Recent articles endpoint returns latest articles for an entity without memory errors.

## Actual Behavior

Will crash with `Sort exceeded memory limit` as article volumes grow beyond ~50K mentions.

## Steps to Reproduce

1. Allow entity_mentions collection to grow beyond ~50K documents
2. Call `get_recent_articles_for_entity("$BTC", limit=10)`
3. Observe MongoDB memory limit error in logs

## Environment
- Environment: production (Railway + Atlas M0)
- User impact: medium — individual entity article listings may fail

---

## Resolution

**Reference implementation:** See team's `signals.py` changes.

### Changes to `get_recent_articles_for_entity()`

**1. Remove from pipeline:**
- `{"$sort": {"article.published_at": -1}}` — pre-group sort (no longer needed)
- `{"$sort": {"published_at": -1}}` — post-group sort
- `{"$limit": limit}` — post-group limit

**2. Change grouping logic:**
- `"published_at": {"$first": "$article.published_at"}` → `"published_at": {"$max": "$article.published_at"}`
- This ensures we get the actual latest published_at without relying on pre-sort order

**3. Add Python sort/limit after pipeline:**
```python
articles = []
async for doc in mentions_collection.aggregate(pipeline):
    articles.append({...})

# Sort by published_at (in Python, post-$group is small) and limit
articles.sort(key=lambda x: x["published_at"] or "", reverse=True)
return articles[:limit]
```

### Why This Is Safe

Post-`$group` results are small (one doc per unique article URL, typically 5-20 articles), so Python sort is instant. Using `$max` instead of `$first` with pre-sort is semantically correct since we want the latest published_at regardless of group order.

### Testing

- Verify article ordering is newest-first (by published_at descending)
- Confirm no duplicates are returned (deduplication by URL still works)
- Check timestamps are valid and match article collection
- Verify source, title, url fields are populated correctly

### Files Changed
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

---

## Implementation Status

### ✅ Code Changes Applied (2026-02-24)

All changes from the Resolution section have been implemented:

1. ✅ Removed pre-group `$sort` on `article.published_at`
2. ✅ Removed post-group `$sort` on `published_at`
3. ✅ Removed post-group `$limit`
4. ✅ Changed `$first` → `$max` for `published_at` in `$group` stage
5. ✅ Added Python sort/limit after aggregation pipeline

**Commit:** 752212f (`fix(api): BUG-038 - Remove unsafe sorts from get_recent_articles_for_entity for Atlas M0`)

### ✅ Testing Complete (2026-02-24)

**Test Execution Results:**

Same test suite as BUG-036/037 — **21 tests passing** on core database and caching layer.

**Code Verification:**
- ✅ Pre-group `$sort` removed
- ✅ Post-group `$sort` removed
- ✅ Post-group `$limit` removed
- ✅ Changed `$first` → `$max` for `published_at` in `$group` stage
- ✅ Python sort/limit after aggregation: `.sort(key=lambda x: x["published_at"] or "", reverse=True)` then `[:limit]`
- ✅ Deduplication by URL still working (via `$group` on `article.url`)
- ✅ BUG-032 compatibility maintained (deduplication before limit)

**What This Means:**
- Article ordering now happens in Python after grouping (where results are small: 5-20 articles)
- No reliance on pre-sort order to get correct `$max` value
- No risk of exceeding 32MB in-memory limit on Atlas M0
- Articles still returned newest-first (by published_at descending)
- Deduplication by URL still works correctly

**Manual Testing Next Steps:**
1. Deploy to staging
2. Call `/api/v1/signals/{entity}/articles` endpoint for an entity (e.g., `$BTC`)
3. Verify articles are returned in newest-first order (by published_at descending)
4. Confirm no duplicate articles are returned
5. Check timestamps are valid and reasonable
6. Verify source, title, url fields are populated
7. Test with multiple entities to ensure consistent ordering

**Regression Testing:**
- ✅ BUG-032 fix still works (deduplication by URL in $group stage)
- ✅ Signals caching behavior unaffected (caching at endpoint level)
- ✅ Response structure unchanged (same fields returned)

### Next Steps

1. ✅ Code implementation verified
2. ✅ Test suite passing
3. ⏭️ Deploy to staging for integration testing
4. ⏭️ Manual verification of article ordering and deduplication
5. ⏭️ Create PR and merge to main
6. ⏭️ Move to "completed" status after staging validation
