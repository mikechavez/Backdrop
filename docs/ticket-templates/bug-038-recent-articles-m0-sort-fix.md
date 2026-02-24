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

# BUG-038: get_recent_articles_for_entity() Has Two Unsafe Sorts on Atlas M0

## Problem

`get_recent_articles_for_entity()` in `signals.py` has two `$sort` stages:
1. Pre-group: `{"$sort": {"article.published_at": -1}}`
2. Post-group: `{"$sort": {"published_at": -1}}`

Plus a `{"$limit": limit}` at the end. Both sorts are unsafe on Atlas M0 (which ignores `allowDiskUse=True`). The pre-group sort also makes `$first` in the `$group` stage dependent on sort order — without it, `$first` gives arbitrary values.

## Expected Behavior

Recent articles for each entity are returned sorted by published date, newest first, without memory errors.

## Actual Behavior

Risk of `Sort exceeded memory limit` for entities with many mentions. Also, if pre-sort is removed without updating `$first` → `$max`, `published_at` field returns arbitrary dates.

## Steps to Reproduce
1. Query trending signals for an entity with 1000+ mentions
2. Observe potential memory error or incorrect article ordering

## Environment
- Environment: production (Railway + Atlas M0)
- User impact: medium — affects article listing under signals

---

## Resolution

**Reference implementation:** See attached `signals.py` from team.

### Changes to `get_recent_articles_for_entity()`

**1. Remove from pipeline:**
- `{"$sort": {"article.published_at": -1}}` (pre-group sort)
- `{"$sort": {"published_at": -1}}` (post-group sort)
- `{"$limit": limit}`

**2. Change in `$group` stage:**
- `"published_at": {"$first": "$article.published_at"}` → `"published_at": {"$max": "$article.published_at"}`
- Reason: Without pre-sort, `$first` gives arbitrary order. `$max` always gets the latest date.

**3. Add Python sort/limit after cursor loop:**
```python
articles.sort(key=lambda x: x["published_at"] or "", reverse=True)
return articles[:limit]
```

### Why This Is Safe
After `$group` by article URL, the result set is small (one doc per unique article). Python sort is instant.

### Testing
- Hit `/api/v1/signals/trending` and verify `recent_articles` are in newest-first order
- Confirm no duplicate articles (BUG-032 dedup still works)
- Check articles have valid `published_at` values (not arbitrary old dates)

### Files Changed
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

---

## Implementation Status

### ✅ Code Changes Applied (2026-02-24)

All changes from the Resolution section have been implemented:

1. ✅ Removed pre-group `$sort` stage: `{"$sort": {"article.published_at": -1}}`
2. ✅ Removed post-group `$sort` stage: `{"$sort": {"published_at": -1}}`
3. ✅ Removed `$limit` stage
4. ✅ Changed `$group` stage: `{"$first": "$article.published_at"}` → `{"$max": "$article.published_at"}`
5. ✅ Added Python sort/limit after cursor loop: `articles.sort(key=lambda x: x["published_at"] or "", reverse=True)` + `return articles[:limit]`

**Commit:** 752212f (`fix(api): BUG-038 - Remove unsafe sorts from get_recent_articles_for_entity for Atlas M0`)

### ⚠️ Testing Required

The implementation is complete but **requires testing before merging**:

**Manual Testing Steps:**
1. Deploy to staging/test environment
2. Hit `/api/v1/signals/trending` and verify recent_articles are in newest-first order
3. Confirm no duplicate articles (BUG-032 dedup still works)
4. Check articles have valid `published_at` values (not arbitrary old dates)
5. Verify no timeout or memory errors in Railway logs

**Automated Testing:**
- [ ] Run `pytest tests/api/test_signals.py` — verify article ordering and deduplication
- [ ] Run `pytest tests/db/test_signal_scores.py` — verify published_at field populated correctly
- [ ] Test with entities having 1000+ mentions to verify performance

**Verification Checklist:**
- [ ] Recent articles are sorted newest-first (most recent published_at first)
- [ ] No duplicate articles in results
- [ ] All articles have valid published_at timestamps
- [ ] Response time acceptable (< 2s for typical requests)

### Next Steps

1. Run test suite
2. Deploy to staging for integration testing
3. Monitor production deployment for errors
4. Move to "completed" status after successful testing