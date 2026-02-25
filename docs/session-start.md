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

## ADR-012 Progress

Ship remaining phases:

1. ✅ **Phase 1:** 7-day hard cutoff (BUG-045 COMPLETE)
2. ✅ **Phase 2:** Redis cache (15m TTL) (FEATURE-049 COMPLETE)
3. ✅ **Phase 3:** Cache warmer (TASK-015 COMPLETE)
4. ✅ **Phase 4:** UI cleanup - BUG-051 (remove counts) COMPLETE
5. **Phase 5:** Observability - TASK-016 [NEXT]

## Definition of Done

-   Bitcoin articles \<1s warm ← BUG-045 achieves this
-   Redis cache warmed before user click ← FEATURE-049 ✅ / TASK-015
-   No 10s+ backend calls ← All phases

### ✅ COMPLETED: BUG-051 (2026-02-25)
- **Branch:** fix/bug-051-remove-ui-counts
- **Commit:** 05fb2d3
- **Changes:** Removed header count display and source count from signal cards

**What was fixed:**
- Removed "(X of Y)" count display from Signals page header
- Removed "X sources" count from individual signal cards
- Cleaned up unused totalCount variable

**Frontend validation:** Build successful - 2146 modules, 144KB gzipped

## Next Task

**TASK-016:** Observability + clamps (Phase 5 - Final ADR-012 Phase)
