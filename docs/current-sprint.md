# Sprint 10 --- UI Polish & Stability

**Last Updated:** 2026-02-25
**Status:** ADR-012 Complete + Deployment Ready

## Major Epic: ADR-012 — Signals Recovery (✅ COMPLETE)

🎯 **All 5 phases shipped to main. Ready for Railway deployment.**

1. ✅ **BUG-045** --- Time-bound entity articles (7d) [COMPLETE - PR #203]
2. ✅ **FEATURE-049** --- Redis cache entity articles [COMPLETE - PR #206]
3. ✅ **TASK-015** --- Cache warming task [COMPLETE - PR #207]
4. ✅ **BUG-051** --- Remove UI counts [COMPLETE - PR #209]
5. ✅ **TASK-016** --- Observability + clamps [COMPLETE - PR #210/#211]
6. ✅ **BUG-052** --- "Recent mentions" two-click fix [COMPLETE - PR #210/#211]
7. ✅ **BUG-053** --- UI text cleanup (pagination text) [COMPLETE - PR #210/#211]

## Post-ADR-012 Sprint Work

### Remaining Sprint 10 Items (Paused During ADR-012, Now Available)

## Phase 1 Completion (BUG-045)

**Merged into PR #203:**
- ✅ Enforce 7-day cutoff at MongoDB query level
- ✅ Apply cutoff before `$group` stage (prevents memory bloat)
- ✅ Clamp API parameters: `limit≤20`, `days≤7`
- ✅ Updated both single-entity and batch fetch functions

**Expected Results:**
- Entity articles: <1s warm, <3s cold
- Bitcoin/Ethereum: <2s cold (from 10-45s)
- Eliminates unbounded article/mention scans

## Success Criteria

- ✅ Signals page <5s cold (BUG-045 achieves <3s for articles)
- ✅ Entity articles <1s warm (BUG-045 expected impact)
- ⏳ No 10s+ backend calls (all phases needed)

## Phase 4 Completion (BUG-051)

**Changes:**
- ✅ Remove header count display "(X of Y signals)"
- ✅ Remove source count from signal cards
- ✅ Clean up unused totalCount variable
- ✅ Frontend build verification: 2146 modules, 144KB gzipped

**Impact:** Cleaner UI, removes internal metrics display

## Phase 5 Completion (TASK-016)

**Implementation:**
- ✅ Fixed duplicate logging issue in main.py
  - Removed redundant basicConfig() call
  - Consolidated handler chain
  - Verified with tests: zero duplicates

- ✅ Added comprehensive observability logging
  - All endpoints log with consistent format: `operation: key1=value1, key2=value2`
  - Millisecond-precision timing for all operations
  - Request tracing with unique IDs for correlation

- ✅ Parameter clamp tracking
  - limit≤20, days≤7 with visible logging
  - Format: `param_clamped: original_value → clamped_value`

- ✅ Comprehensive testing
  - 7 tests in test_task_016_observability.py
  - All tests passing
  - Verified no duplicate handlers
  - Verified consistent logging format

**Branch:** fix/task-016-observability-clamps
**Commits:** fad129a, a420bdd

## Ready for Deployment (ADR-012 + Polish)

✅ All ADR-012 phases complete and tested
✅ Signals page performance optimized (<5s cold expected)
✅ Entity articles cached (15m TTL, <1s warm expected)
✅ Full observability for production monitoring
✅ Zero duplicate log messages
✅ Parameter clamps verified and logged
✅ BUG-052 Fixed: "Recent mentions" two-click bug + hover UX improved

### Latest: BUG-052 Resolution (2026-02-25)
- Fixed button requiring two clicks to expand
- Articles now fetch in background (non-blocking)
- Enhanced hover UX: background highlight, padding, rounded, transition
- Build verified: 2146 modules, 144KB gzipped

---

## Other Sprint 10 Work (Previously Completed)

### ✅ BUG-027: Remove Afternoon Scheduled Briefing
- **Status:** COMPLETE
- **Resolved:** 2026-02-10
- **Branch:** `fix/bug-027-remove-afternoon-scheduled-briefing`
- **Changes:** Removed 2 PM briefing from Celery Beat schedule, fixed manual afternoon trigger

### ✅ BUG-028: Website Always Shows Same Briefing
- **Status:** COMPLETE
- **Resolved:** 2026-02-10
- **Root Cause:** Motor's `find_one(..., sort=[...])` ignores sort argument
- **Fix:** Replaced with `find().sort().limit(1)` in `get_latest_briefing()`

### ✅ BUG-032: Duplicate Articles Under Signals
- **Status:** COMPLETE
- **Resolved:** 2026-02-23
- **Branch:** `fix/bug-032-duplicate-articles`
- **Changes:** Added `$group` stage to deduplicate articles before limit

### ✅ BUG-034: Sort Exceeded Memory Limit on Signals Page
- **Status:** COMPLETE (Merged PR #179)
- **Resolved:** 2026-02-23
- **Root Cause:** `allowDiskUse=True` missing from 5 aggregation pipelines
- **Fix:** Added to all aggregations in signal_service.py

### ✅ BUG-035: Signals Endpoint Aggregation Missing allowDiskUse
- **Status:** COMPLETE (Merged PR #180)
- **Resolved:** 2026-02-24
- **Preventive Fix:** Added allowDiskUse to 2 aggregations in signals endpoint

### ✅ BUG-041: Skeleton Loaders Not in Production
- **Status:** COMPLETE (Deployed to Vercel)
- **Resolved:** 2026-02-24
- **Changes:** New `Skeleton.tsx` component with loaders for all 5 pages

### ✅ BUG-042: useInfiniteQuery Refetch Storm
- **Status:** COMPLETE
- **Resolved:** 2026-02-25
- **Root Cause:** FEATURE-048d/048e hardcoded `staleTime: 0` + `refetchOnWindowFocus: true`
- **Fix:** Added `refetchOnWindowFocus: false` to Signals.tsx and Narratives.tsx

### ✅ FEATURE-048a: Backend Signals Pagination
- **Status:** COMPLETE
- **Resolved:** 2026-02-25
- **Changes:** Implemented offset-based pagination for `/api/v1/signals/trending`
- **Details:** Default limit 50→15, cache strategy shared across pages

---

## Next Steps

1. ✅ ADR-012 deployed to main (commit fcfdad5)
2. Deploy to Railway (production)
3. Monitor performance metrics and observability logs
4. Close ADR-012 epic
5. Continue with remaining Sprint 10 items as needed
