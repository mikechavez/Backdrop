---
id: BUG-074
type: bug
status: open
priority: critical
severity: critical
created: 2026-04-14
updated: 2026-04-14
---

# BUG-074: Missing sort in `_get_active_narratives()` causes briefing agent to receive empty narrative list

## Problem
The briefing agent consistently receives an empty narrative list, causing the model to refuse generation. The `_get_active_narratives()` method in `briefing_agent.py` fetches narratives with no sort order, so MongoDB returns documents in natural insertion order — all from October 2025. Every document fails the 7-day recency check. The 156 narratives created since January 2026 are never reached.

## Expected Behavior
`_get_active_narratives()` should return the most recently updated narratives first, so current documents pass the recency filter and the briefing agent has real content to work with.

## Actual Behavior
The method returns an empty list. The briefing agent passes the empty list to the model, which correctly refuses to generate and publishes an error report instead of a briefing. The UI shows stale data and the pipeline appears frozen.

## Steps to Reproduce
1. Trigger a manual briefing run
2. Observe the published output — it will be an error report, not a briefing
3. Check `briefing_agent.py` → `_get_active_narratives()` — the narratives query has no `.sort()` call
4. Query MongoDB directly: `db.narratives.find({}).limit(45)` — all returned documents will have `last_updated` in October 2025

## Environment
- Environment: production
- User impact: critical — briefings have not published correctly since October 2025

## Screenshots/Logs
MongoDB query confirming stale document surfacing:
```
db.narratives.find(
  { lifecycle_state: { $in: ["emerging", "hot", "rising"] } },
  { title: 1, last_updated: 1 }
).limit(5)
// All results: last_updated: 2025-10-12
```

---

## Resolution

**Status:** Fixed
**Fixed:** 2026-04-14
**Branch:** fix/bug-073-fingerprint-generation
**Commit:** (pending push)

### Root Cause
`_get_active_narratives()` fetches `limit × 3 = 45` documents with no sort. MongoDB returns oldest documents first (natural insertion order). All 45 are from October 2025 and fail the 7-day recency check. Method returns `[]`.

### Changes Made
Add `.sort("last_updated", -1)` before `.limit(limit * 3)` in the narratives query in `_get_active_narratives()`:

```python
).sort("last_updated", -1).limit(limit * 3)
```

Index `idx_lifecycle_state_last_updated` already exists — no migration needed.

### Testing
1. Deploy the one-line fix
2. Run the sanity check query to confirm recent narratives are present:
   ```
   db.narratives.find(
     { lifecycle_state: { $in: ["emerging","hot","rising"] } },
     { title: 1, last_updated: 1 }
   ).sort({ last_updated: -1 }).limit(5)
   ```
3. Trigger a manual briefing
4. Confirm published document contains `narrative`, `key_insights`, and `recommendations` fields populated with April 2026 content

### Files Changed
- `briefing_agent.py` — `_get_active_narratives()`, one-line sort addition