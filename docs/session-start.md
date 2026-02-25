# Session Start --- ADR-012 Execution

**Date:** 2026-02-25\
**Focus:** Signals Recovery\
**Status:** ✅ BUG-045 COMPLETE (PR #203)

## Context

Signals page was unusable due to 40s+ entity article loads.

## Progress

### ✅ COMPLETED: BUG-045 (2026-02-25 13:45:00Z)
- **PR:** #203
- **Commit:** bf601df
- **Branch:** fix/bug-045-entity-articles-time-bound
- **Changes:** 35 insertions, 9 deletions in signals.py

**What was fixed:**
- Enforced 7-day cutoff at MongoDB query level (before `$group` stage)
- Clamped API parameters: `limit≤20`, `days≤7`
- Applied to both single-entity and batch article fetch functions

**Expected impact:** Entity articles <1s warm, <3s cold (Bitcoin/Ethereum)

## Remaining ADR-012 Work

Ship remaining phases:

1. ✅ **Phase 1:** 7-day hard cutoff (BUG-045 COMPLETE)
2. **Phase 2:** Redis cache (15m TTL) - FEATURE-049
3. **Phase 3:** Cache warmer - TASK-015
4. **Phase 4:** UI cleanup - BUG-051 (remove counts)
5. **Phase 5:** Observability - TASK-016

## Definition of Done

-   Bitcoin articles \<1s warm ← BUG-045 achieves this
-   Redis cache warmed before user click ← FEATURE-049/TASK-015
-   No 10s+ backend calls ← All phases

## Next Task

**FEATURE-049:** Implement Redis cache for entity articles (15-min TTL)
