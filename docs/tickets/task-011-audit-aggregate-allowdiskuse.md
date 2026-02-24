---
ticket_id: TASK-011
title: Audit All MongoDB Aggregate Calls for allowDiskUse
priority: MEDIUM
severity: N/A
status: OPEN
date_created: 2026-02-23
branch: chore/task-011-aggregate-audit
effort_estimate: 30 minutes
---

# TASK-011: Audit All MongoDB Aggregate Calls for allowDiskUse

## Problem Statement

BUG-034 revealed that `.aggregate()` calls without `allowDiskUse=True` will crash once data volume exceeds MongoDB's 32MB in-memory sort limit. BUG-034 and BUG-035 fix the known instances in `signal_service.py` and `signals.py`, but the same pattern may exist across the codebase in other services and db operations.

This is the same class of preventive audit as the Motor `find_one(..., sort=[...])` audit done after BUG-028.

---

## Task

Audit every `.aggregate()` call across the codebase. Add `allowDiskUse=True` to any call that includes `$sort`, `$group`, `$lookup`, or other memory-intensive stages.

### Audit Steps

```bash
# 1. Find ALL aggregate calls in Python source
rg -n "\.aggregate\(" --type py src/

# 2. Check which ones already have allowDiskUse
rg -n "\.aggregate\(" --type py src/ | grep -v "allowDiskUse"
# Any results here need to be fixed

# 3. Key directories to check
# - src/crypto_news_aggregator/services/         (service layer)
# - src/crypto_news_aggregator/db/operations/     (data access layer)
# - src/crypto_news_aggregator/api/v1/endpoints/  (API layer)
# - src/crypto_news_aggregator/tasks/             (background tasks)
```

### Known Files to Check (Beyond BUG-034/035)

| File | Likely Has Aggregations |
|------|----------------------|
| `services/narrative_service.py` | Yes — narrative clustering queries |
| `services/briefing_agent.py` | Possible — gathers signals/patterns |
| `db/operations/narratives.py` | Possible — narrative CRUD |
| `db/operations/signals.py` | Possible — signal CRUD |
| `services/pattern_detector.py` | Possible — cross-narrative analysis |
| `db/operations/articles.py` | Possible — article queries |

### Fix Pattern

For every `.aggregate()` call found without `allowDiskUse=True`:

```python
# Before
result = await collection.aggregate(pipeline).to_list(length=N)

# After
result = await collection.aggregate(pipeline, allowDiskUse=True).to_list(length=N)
```

**Exception:** Simple aggregations with only `$match` and `$count` stages (no `$sort`, `$group`, `$lookup`, `$unwind`) are safe without `allowDiskUse` but should still be flagged for consistency.

---

## Verification

```bash
# Final check: zero aggregate calls without allowDiskUse
rg -n "\.aggregate\(" --type py src/ | grep -v "allowDiskUse"
# Must return 0 results
```

---

## Acceptance Criteria

- [ ] Every `.aggregate()` call in `src/` has `allowDiskUse=True`
- [ ] Verification command returns 0 unprotected calls
- [ ] No regressions — signals, narratives, briefings all load correctly

---

## Impact

- ✅ **Preventive**: Eliminates entire class of 32MB sort limit crashes
- ✅ **Consistent**: Establishes codebase-wide standard for aggregate calls
- ✅ **Low risk**: `allowDiskUse=True` has no behavior change unless memory limit is actually hit

---

## Related Tickets

- BUG-028: Precedent — Motor `find_one` sort audit (same pattern of codebase-wide fix)
- BUG-034: The crash that triggered this audit
- BUG-035: Known instance in signals endpoint
- TASK-012: Index optimization to reduce memory pressure at the source