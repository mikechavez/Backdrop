---
id: BUG-087
type: bug
status: backlog
priority: medium
severity: low
created: 2026-04-16
updated: 2026-04-16
---

# Dormant narratives render on frontend narratives page

## Problem
Users report that the narratives page continues to render narratives with `lifecycle_state: "dormant"`. These should be filtered out of the active view.

Initial assumption (from session 34 handoff) was that the narratives endpoint lacks a `lifecycle_state != "dormant"` filter. That assumption is **incorrect**. The `/narratives/active` endpoint in `src/crypto_news_aggregator/api/v1/endpoints/narratives.py:259` already filters by a whitelist of active states (lines 305-312):

```python
active_states = ['emerging', 'rising', 'hot', 'cooling', 'reactivated']
match_stage = {
    '$or': [
        {'lifecycle_state': {'$in': active_states}},
        {'lifecycle_state': {'$exists': False}}
    ]
}
```

So the real question is: why are dormants rendering despite this filter? Three plausible root causes, each with a different fix:

1. **Frontend is calling a different endpoint.** The narratives page might be hitting `/narratives/archived` (which is meant to show dormants) or an older `/narratives/` variant without filters.
2. **Legacy fallback bleed.** The `{'lifecycle_state': {'$exists': False}}` clause includes old narratives that never had `lifecycle_state` set. If any of those are functionally dormant (no recent articles, stale summary) they render as "active".
3. **State transition lag.** Narratives flipped to dormant by a scheduled job might not be caught if the filter runs against stale lifecycle data.

## Expected Behavior
Dormant narratives do not render on the default narratives view. They remain accessible via `/narratives/archived` for operators and history views.

## Actual Behavior
Dormant narratives appear in the default narratives list despite the `/active` endpoint's filter.

## Steps to Reproduce
1. Identify a known-dormant narrative: `db.narratives.findOne({lifecycle_state: "dormant"})`
2. Load the frontend narratives page
3. Check whether that narrative renders in the default view
4. Inspect the network request the frontend makes — confirm which endpoint is actually called and what filter params are passed

## Environment
- Environment: production
- User impact: low (visual noise, not a data correctness issue)

## Screenshots/Logs
Relevant code: `src/crypto_news_aggregator/api/v1/endpoints/narratives.py:259-346` (`get_active_narratives_endpoint`)

---

## Resolution

**Status:** Open
**Fixed:** YYYY-MM-DD
**Branch:**
**Commit:**

### Root Cause
To be determined by the audit below.

### Investigation Steps

1. **Confirm which endpoint the frontend calls.**
   Open browser devtools on the narratives page, find the request, capture the exact URL and query params. Expected: `/api/v1/narratives/active`. If different, that's the fix: point the frontend at `/active` (or port the `/active` filter to whatever endpoint is being hit).

2. **If it is `/active`, quantify the `$exists: False` bleed.**
   ```
   db.narratives.countDocuments({lifecycle_state: {$exists: false}})
   ```
   If this returns a meaningful count (>10), those narratives are the likely source. They were created before `lifecycle_state` was added to the schema. Fix: backfill them with a computed lifecycle_state based on `last_updated` and `article_count`, then tighten the `/active` filter to require `lifecycle_state $in: active_states` (drop the `$exists: False` fallback).

3. **If it is `/active` and `$exists: False` count is low, check state transition timing.**
   Find narratives currently rendering as "active" on the frontend whose `lifecycle_state` in the DB is actually `dormant`. If any exist, it's a cache issue — the 60s signals cache or the `_narratives_cache` in `narratives.py` is serving stale data past state transitions.

### Changes Made
To be filled in based on audit findings. Most likely fix profile depending on root cause:

**Case 1 (wrong endpoint):** Frontend fix only. Point the narratives page fetch at `/api/v1/narratives/active`.

**Case 2 (legacy bleed):** Backfill script + filter tightening.
```python
# Migration: backfill lifecycle_state on narratives missing it
# Run once, then:
# In narratives.py match_stage, drop the $or and simplify to:
match_stage = {'lifecycle_state': {'$in': active_states}}
```

**Case 3 (cache staleness):** Shorten cache TTL on `_narratives_cache` or invalidate it when lifecycle transitions run.

### Testing
- Frontend network tab shows the correct endpoint being hit
- Query for dormant narratives and confirm none appear in `/active` response
- If backfill applied: re-run `db.narratives.countDocuments({lifecycle_state: {$exists: false}})` returns 0

### Files Changed
- To be determined based on audit

### Notes
- This ticket was originally scoped (in session 34 handoff) as "add the dormant filter." The filter already exists. Rescoped as an audit to find what's actually letting dormants through.
- Ship independently — no dependencies on BUG-088 / FEATURE-012 / FEATURE-013 / BUG-086.