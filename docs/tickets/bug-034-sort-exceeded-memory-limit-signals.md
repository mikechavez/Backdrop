---
ticket_id: BUG-034
title: Sort Exceeded Memory Limit on Signals Page
priority: HIGH
severity: HIGH
status: PR_OPEN
date_created: 2026-02-23
branch: fix/bug-034-aggregate-allowdiskuse
effort_estimate: 15 minutes
---

# BUG-034: Sort Exceeded Memory Limit on Signals Page

## Problem Statement

The signals page crashes with a MongoDB aggregation error: `Sort exceeded memory limit of 33554432 bytes, but did not opt in to external sorting.` (error code 292, `QueryExceededMemoryLimitNoDiskUseAllowed`).

The `compute_trending_signals()` function in `signal_service.py` runs multiple aggregation pipelines with `$sort`, `$lookup`, and `$group` stages that exceed MongoDB Atlas's 32MB in-memory sort limit as article/mention volume has grown.

### Root Cause

Five `.aggregate()` calls in `signal_service.py` do not pass `allowDiskUse=True`, so MongoDB attempts to sort entirely in memory. With growing data volume (~450 articles/day × months of operation), the sort stage now exceeds the 32MB limit.

### Error (Production)
```
Failed to compute trending signals: PlanExecutor error during aggregation :: caused by ::
Sort exceeded memory limit of 33554432 bytes, but did not opt in to external sorting.
Code: 292, CodeName: QueryExceededMemoryLimitNoDiskUseAllowed
```

---

## Solution

Add `allowDiskUse=True` to all 5 `.aggregate()` calls in `signal_service.py`.

### Changes Required

**File:** `src/crypto_news_aggregator/services/signal_service.py`

**1. `_count_filtered_mentions()` — line 144**
```python
# Before
result = await collection.aggregate(pipeline).to_list(length=1)

# After
result = await collection.aggregate(pipeline, allowDiskUse=True).to_list(length=1)
```

**2. `calculate_source_diversity()` — line 303**
```python
# Before
result = await db.entity_mentions.aggregate(pipeline).to_list(length=1)

# After
result = await db.entity_mentions.aggregate(pipeline, allowDiskUse=True).to_list(length=1)
```

**3. `get_top_entities_by_mentions()` — line 635**
```python
# Before
results = await db.entity_mentions.aggregate(pipeline).to_list(length=limit)

# After
results = await db.entity_mentions.aggregate(pipeline, allowDiskUse=True).to_list(length=limit)
```

**4. `compute_trending_signals()` — line 736 (main pipeline)**
```python
# Before
results = await db.entity_mentions.aggregate(pipeline).to_list(length=limit * 2)

# After
results = await db.entity_mentions.aggregate(pipeline, allowDiskUse=True).to_list(length=limit * 2)
```

**5. `compute_trending_signals()` — line 743 (narrative lookup)**
```python
# Before
narrative_counts = await db.narratives.aggregate([
    {"$match": {"entities": {"$in": entities}}},
    {"$unwind": "$entities"},
    {"$match": {"entities": {"$in": entities}}},
    {"$group": {"_id": "$entities", "count": {"$sum": 1}, "narrative_ids": {"$push": {"$toString": "$_id"}}}}
]).to_list(length=None)

# After
narrative_counts = await db.narratives.aggregate([
    {"$match": {"entities": {"$in": entities}}},
    {"$unwind": "$entities"},
    {"$match": {"entities": {"$in": entities}}},
    {"$group": {"_id": "$entities", "count": {"$sum": 1}, "narrative_ids": {"$push": {"$toString": "$_id"}}}}
], allowDiskUse=True).to_list(length=None)
```

---

## Verification

```bash
# 1. Confirm all aggregate calls have allowDiskUse
rg -n "\.aggregate\(" src/crypto_news_aggregator/services/signal_service.py | grep -v "allowDiskUse"
# Must return 0 results

# 2. Test signals endpoint
curl -s https://context-owl-production.up.railway.app/api/v1/signals/trending | python -m json.tool | head -20
# Should return valid JSON with trending signals, no 500 error

# 3. Test all timeframes
curl -s "https://context-owl-production.up.railway.app/api/v1/signals/trending?timeframe=24h"
curl -s "https://context-owl-production.up.railway.app/api/v1/signals/trending?timeframe=7d"
curl -s "https://context-owl-production.up.railway.app/api/v1/signals/trending?timeframe=30d"
# All should return valid responses
```

---

## Implementation Status

**Code Fix:** ✅ COMPLETED
- **Branch:** `fix/bug-034-aggregate-allowdiskuse`
- **Commit:** `b5a1c7b` — All 5 aggregate calls updated with `allowDiskUse=True`
- **PR:** OPEN (awaiting Vercel runtime fix deployment)
- **Date Implemented:** 2026-02-23

**Blocking Issue:** 🔴 Vercel Python 3.14 Incompatibility
- Vercel trying to build with Python 3.14
- PyO3 (pydantic-core) only supports Python ≤3.13
- **Fix Applied:** PR #179 merged to main — `runtime.txt` updated to `python-3.13.1`
- **Next Step:** Once Vercel runtime fix is verified, BUG-034 PR should deploy successfully

---

## Impact

- ✅ **Signals page**: Restores functionality — page currently broken in production
- ✅ **API reliability**: `/api/v1/signals/trending` returns data instead of 500 error
- ✅ **Future-proofing**: `allowDiskUse=True` handles continued data growth

---

## Files Changed

- `src/crypto_news_aggregator/services/signal_service.py` — 5 aggregate calls updated
  - Line 144: `_count_filtered_mentions()`
  - Line 303: `calculate_source_diversity()`
  - Line 635: `get_top_entities_by_mentions()`
  - Line 736: `compute_trending_signals()` main pipeline
  - Line 743: `compute_trending_signals()` narrative lookup

## Related Tickets

- BUG-035: Same fix needed in signals API endpoint (`signals.py`)
- TASK-011: Codebase-wide audit of all `.aggregate()` calls
- TASK-012: MongoDB index optimization to reduce sort memory pressure