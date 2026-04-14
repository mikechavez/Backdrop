---
ticket_id: TASK-066
title: Clean up stale October 2025 narratives from collection
priority: low
severity: low
status: OPEN
date_created: 2026-04-14
branch: task/task-066-stale-narrative-cleanup
effort_estimate: S (< 1 hour)
---

# TASK-066: Clean up stale October 2025 narratives from MongoDB collection

## Problem Statement
Approximately 300+ narrative documents from October 2025 remain in the collection with active `lifecycle_state` values (`"cooling"`, `"emerging"`, etc.). They no longer surface in queries now that BUG-074's sort fix is in place, but they add noise to the collection and could resurface if the recency filter is ever loosened or the sort is accidentally removed. Addressing this is optional but keeps the collection clean and reduces the risk of stale data re-emerging.

---

## Task
Run a one-time migration against the `narratives` collection. Two options — choose one:

**Option A (soft — recommended):** Set `lifecycle_state: "dormant"` on all narratives with `last_updated` before `2025-12-01`. Preserves documents for historical reference.
```javascript
db.narratives.updateMany(
  { last_updated: { $lt: ISODate("2025-12-01T00:00:00Z") } },
  { $set: { lifecycle_state: "dormant" } }
)
```

**Option B (hard):** Delete all narratives with `last_updated` before `2025-12-01` outright.
```javascript
db.narratives.deleteMany(
  { last_updated: { $lt: ISODate("2025-12-01T00:00:00Z") } }
)
```

Prior to running either option, take a count and confirm scope:
```javascript
db.narratives.countDocuments(
  { last_updated: { $lt: ISODate("2025-12-01T00:00:00Z") } }
)
```

---

## Verification
1. Run count query before migration — record the number
2. Execute chosen migration
3. Re-run count query — confirm result is 0
4. Spot-check that recent narratives (April 2026) are unaffected
5. Trigger a manual briefing and confirm it runs correctly

---

## Acceptance Criteria
- [ ] Count of documents with `last_updated < 2025-12-01` is 0 after migration
- [ ] No narratives with `last_updated >= 2025-12-01` are affected
- [ ] Briefing pipeline runs normally after migration
- [ ] Migration approach (Option A or B) documented in commit message

---

## Impact
Reduces collection noise and eliminates the risk of stale October 2025 documents re-surfacing under future query changes. Low risk, low urgency — do not prioritize over open bugs.

---

## Related Tickets
- BUG-074 (stale documents discovered during investigation)