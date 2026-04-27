---
id: BUG-060
type: bug
status: fixed
priority: critical
severity: critical
created: 2026-04-09
updated: 2026-04-09
---

# Timezone-Naive Datetime Bug Breaking Signal Computation

## Problem

Briefing generation was being skipped with "insufficient data (signals=0)" even though articles and narratives were available. The issue was in `signal_service.py` where `datetime.now(timezone.utc).replace(tzinfo=None)` was stripping timezone information before comparing against MongoDB documents.

## Expected Behavior

Signal computation should return trending entities/signals based on entity_mentions from the last 24 hours.

## Actual Behavior

Signal computation returns 0 results because:
1. `now` datetime is converted to naive (no timezone)
2. MongoDB $gte/$lt operators compare against timezone-aware datetimes in the collection
3. Comparison fails silently, filtering out all documents
4. Returns empty list, which triggers "insufficient data" skip in briefing_agent

## Root Cause

Five instances in `signal_service.py` (lines 167, 226, 411, 574, 704) had:
```python
now = datetime.now(timezone.utc).replace(tzinfo=None)
```

The `.replace(tzinfo=None)` call converts a timezone-aware UTC datetime to a naive datetime. When this naive `now` is compared against timezone-aware MongoDB document fields using `$gte`/`$lt`, the comparison fails.

The incorrect comment suggested "MongoDB returns naive datetimes" — but MongoDB actually returns timezone-aware UTC datetimes.

## Environment
- Environment: production
- User impact: critical (blocks all briefing generation)
- Affected functions:
  - `compute_signal_scores()` (line 167)
  - `compute_trending_signals_detailed()` (line 226)
  - `get_signal_velocity()` (line 411)
  - `_get_high_signal_article_ids()` (line 574)
  - `compute_trending_signals()` (line 704)

## Resolution

**Status:** Fixed  
**Fixed:** 2026-04-09  
**Branch:** fix/bug-058-soft-limit-and-type-error  
**Commit:** 5808da4

### Changes Made

Removed `.replace(tzinfo=None)` from all five instances in `signal_service.py`:
```python
# Before
now = datetime.now(timezone.utc).replace(tzinfo=None)

# After
now = datetime.now(timezone.utc)
```

This preserves timezone awareness, allowing MongoDB date comparisons to work correctly.

### Impact

- Briefing generation can now compute trending signals
- Signal computation returns correct results based on entity_mentions
- "Insufficient data" errors will no longer block briefing generation

### Testing

Verified by:
1. Triggered briefing generation after fix
2. Signal computation now returns non-zero results
3. Briefing generation proceeds (no longer skipped)
4. Celery logs show "Retrieved X trending signals" instead of 0

### Files Changed
- `src/crypto_news_aggregator/services/signal_service.py` (5 instances)
