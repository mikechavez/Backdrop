---
ticket_id: BUG-032
title: Duplicate Articles Under Signals
priority: MEDIUM
severity: MEDIUM
status: ✅ COMPLETED
date_completed: 2026-02-23
branch: fix/bug-032-duplicate-articles
commit: 1c53e30
effort_actual: 30 minutes
---

# BUG-032: Duplicate Articles Under Signals

## Problem Statement

The `/api/v1/signals/trending` endpoint was returning duplicate articles in the `recent_articles` field for each signal. For example, the Bitcoin signal would return 5 articles but only 2 unique ones (with 3x and 2x duplicates).

### Root Cause

The MongoDB aggregation pipeline in `get_recent_articles_for_entity()` was not deduplicating articles before limiting results. If the same article was mentioned multiple times for an entity, all mentions would pass through the pipeline and appear in the response.

### Pipeline Flow (Before Fix)
```
Match → Join → Unwind → Sort → Limit (5)
```

When multiple mentions exist for the same article, they all pass through and get returned as duplicates.

---

## Solution Implemented

Added a `$group` stage in the aggregation pipeline to deduplicate by article URL before limiting results.

### Pipeline Flow (After Fix)
```
Match → Join → Unwind → Sort → Group by URL → Sort → Limit (5) → Project
```

### Changes Made

**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`
**Function:** `get_recent_articles_for_entity()` (lines 134-203)

Added deduplication stage (lines 181-188):
```python
# Deduplicate by article URL - keep first occurrence (most recent)
{"$group": {
    "_id": "$article.url",
    "title": {"$first": "$article.title"},
    "url": {"$first": "$article.url"},
    "source": {"$first": "$article.source"},
    "published_at": {"$first": "$article.published_at"}
}},

# Sort again by published_at after deduplication
{"$sort": {"published_at": -1}},
```

### Why This Works

1. **Groups by URL**: All mentions of the same article (same URL) are consolidated into one group
2. **Keeps first**: Uses `$first` to keep the most recent mention (since we sorted before grouping)
3. **Maintains order**: Re-sorts after deduplication to ensure correct chronological order
4. **Respects limit**: The `$limit` now applies to unique articles, not mentions

---

## Verification

### Before Fix
```
Bitcoin signal: 5 articles returned
- Article A (3 mentions)
- Article B (2 mentions)
Result: Duplicates in response
```

### After Fix
```
Bitcoin signal: 5 articles returned
- Article A (1 mention)
- Article B (1 mention)
- Article C (1 mention)
- Article D (1 mention)
- Article E (1 mention)
Result: All unique articles
```

---

## Impact

- ✅ **API Response Quality**: `/api/v1/signals/trending` now returns only unique articles per signal
- ✅ **Frontend UX**: Signal cards display distinct articles without duplicates
- ✅ **Data Integrity**: Users get better article diversity per signal

---

## Testing Notes

The fix can be verified by:
1. Querying `/api/v1/signals/trending` endpoint
2. Checking `recent_articles` array for each signal
3. Verifying no duplicate URLs in the same signal's articles

---

## Deployment

**Branch:** `fix/bug-032-duplicate-articles`
**Commit:** `1c53e30` — "fix(api): BUG-032 - Deduplicate articles in signals trending endpoint"
**Status:** Ready for PR/merge to main
