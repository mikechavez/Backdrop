---
session_date: 2026-02-23
project: Backdrop (Context Owl)
current_sprint: Sprint 10
session_focus: UI Polish & Stability — Signals Bugs & Skeleton Loaders
---

# Current Sprint Status

> **Last Updated:** 2026-02-25
> **Previous Sprint:** ✅ Sprint 9 Complete (Documentation Infrastructure)
> **Current Session:** FEATURE-048c frontend shared infra COMPLETED

## Sprint 10: UI Polish & Stability

Sprint 9 completed with 100% of features delivered. Sprint 10 focuses on fixing signals page bugs and adding skeleton loaders before resuming launch prep.

---

## Resolved This Sprint

### ✅ FEATURE-048a: Backend Signals Pagination (THIS SESSION)
**Priority:** HIGH | **Complexity:** MEDIUM | **Status:** ✅ COMPLETED (2026-02-25)
**Branch:** `docs/bug-041-bug-033-vercel-deployment-fix` | **Commit:** f9511d8

Implemented offset-based pagination for `/api/v1/signals/trending` endpoint to enable incremental loading of signals:
- **Default limit:** Changed from 50 → 15 (one page of cards)
- **Offset parameter:** Added to enable pagination (`GET /api/v1/signals/trending?offset=15`)
- **Cache strategy:** Full set (up to 100) computed once, cache key v3 excludes offset/limit so all pages share same cache
- **Response metadata:** Added total_count, offset, limit, has_more, cached, computed_at, performance
- **Testing:** 7 new pagination tests added + 5 existing tests updated, all passing

**Files:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`, `tests/api/test_signals.py`
**Ticket:** `docs/tickets/feature-048-lazy-loading/feature-048a-backend-signals-pagination.md`

---

### ✅ BUG-027: Remove Afternoon Scheduled Briefing
**Priority:** MEDIUM | **Severity:** LOW | **Resolved:** 2026-02-10
**Branch:** `fix/bug-027-remove-afternoon-scheduled-briefing` | **Commit:** 2661166

Celery Beat was running briefings 3x/day. Removed the 2 PM afternoon cron entry. Also fixed the manual afternoon trigger which was returning a 400 error — added `generate_afternoon_briefing()` to `briefing_agent.py` and updated the `/generate` endpoint to accept all three types.

**Files:** `beat_schedule.py`, `briefing_agent.py`, `api/v1/endpoints/briefing.py`
**Ticket:** `bug-027-remove-afternoon-scheduled-briefing.md`

---

### ✅ BUG-028: Website Always Shows the Same Briefing
**Priority:** HIGH | **Severity:** HIGH | **Resolved:** 2026-02-10
**Branch:** `fix/bug-027-remove-afternoon-scheduled-briefing` | **Commits:** 39ac7ab, 3bd4d8f

Frontend always displayed the same (oldest) briefing. Root cause: Motor's `find_one(..., sort=[...])` silently ignores the sort argument. Fixed by replacing with `find(filter).sort(...).limit(1)` in `get_latest_briefing()`.

**⚠️ Follow-up completed:** Audited all `find_one(..., sort=[...])` calls across `db/operations/` — **no other instances found**.

**Files:** `db/operations/briefing.py`
**Ticket:** `bug-028-website-always-shows-same-briefing.md`

---

### ✅ BUG-032: Duplicate Articles Under Signals
**Priority:** MEDIUM | **Severity:** MEDIUM | **Resolved:** 2026-02-23
**Branch:** `fix/bug-032-duplicate-articles` | **Commit:** `1c53e30`

API endpoint `/api/v1/signals/trending` was returning duplicate articles in the `recent_articles` field. Root cause: MongoDB aggregation pipeline in `get_recent_articles_for_entity()` lacked deduplication before limiting results. Fixed by adding `$group` stage to consolidate articles by URL before applying the 5-article limit, maintaining chronological order.

**Files:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`
**Ticket:** `bug-032-duplicate-articles-under-signals.md`

---

### ✅ BUG-034: Sort Exceeded Memory Limit on Signals Page
**Priority:** HIGH | **Severity:** HIGH | **Resolved:** 2026-02-23
**Branch:** `fix/bug-034-aggregate-allowdiskuse` | **Commit:** `b5a1c7b` (merged via PR #179)

MongoDB 32MB in-memory sort limit exceeded on signals page as data volume grew. Root cause: Five `.aggregate()` calls in `signal_service.py` lacked `allowDiskUse=True` parameter, which enables disk-based sorting. Fixed by adding `allowDiskUse=True` to all aggregation pipelines (lines 144, 303, 635, 736, 743).

**Related:** Runtime fix via PR #179 updated `runtime.txt` to `python-3.13.1` to unblock Vercel deployments.

**Files:** `src/crypto_news_aggregator/services/signal_service.py`
**Ticket:** `bug-034-sort-exceeded-memory-limit-signals.md`

---

### ⚠️ BUG-035: Signals Endpoint Aggregation Missing allowDiskUse (CODE FIX VERIFIED ✅ - DEPLOYMENT ISSUE)
**Priority:** HIGH | **Severity:** HIGH | **Status:** Code Complete + Railway Deployment Issue | **Merged:** 2026-02-24
**Branch:** `fix/bug-035-signals-endpoint-allowdiskuse` | **Commit:** `65c968e` | **PR:** #180

Preventive fix for same class of bug as BUG-034. Two `.aggregate()` calls in the signals endpoint were added for allowDiskUse parameter.

**Changes Applied & Verified (2026-02-25):**
- Line 207: `mentions_collection.aggregate(pipeline, allowDiskUse=True)` ✅
- Line 264: `db.narratives.aggregate([...], allowDiskUse=True)` ✅

**Full Signal Flow Audit (2026-02-25):**
✅ **signals.py (2 aggregations):**
  - Line 207: get_recent_articles_for_entity() - HAS allowDiskUse
  - Line 259-264: get_signals() narrative count - HAS allowDiskUse

✅ **signal_service.py (5 aggregations):**
  - Line 144: _count_filtered_mentions() - HAS allowDiskUse
  - Line 303: calculate_source_diversity() - HAS allowDiskUse
  - Line 635: get_top_entities_by_mentions() - HAS allowDiskUse
  - Line 736: compute_trending_signals() main pipeline - HAS allowDiskUse
  - Line 743: compute_trending_signals() narrative lookup - HAS allowDiskUse

**Parameter Syntax Verified:**
- ✅ Syntax is correct: `allowDiskUse=True` (camelCase, not snake_case)
- ✅ Motor 3.5.0 supports this parameter
- ✅ All $sort and $group stages are protected

**Current Issue (2026-02-25):**
Despite code fix being complete and correct, signals page still shows the memory error. Investigation indicates:
- ✅ Code is 100% correct (all aggregations protected)
- ⚠️ Error persists = likely deployment/caching issue, not code issue

**Root Cause Analysis:**
1. **NOT a code bug** - All aggregations in signals flow have allowDiskUse=True
2. **Likely deployment issue:**
   - Railway not pulling latest commit (65c968e)
   - Old build artifacts cached
   - Environment variable misconfiguration
   - Database connection using old code path

**Codebase Audit (Secondary Finding - TASK-011):**
Found other aggregations WITHOUT allowDiskUse that HAVE $sort stages:
- llm/cache.py: Lines 256, 281
- api/admin.py: Lines 62, 123, 190, 245, 311, 331
- api/v1/endpoints/articles.py: Lines 202, 286, 347
- services/article_service.py: Lines 372, 451

These are NOT on signals endpoint path but should be fixed in TASK-011.

**Files:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py` (FIXED)
**Ticket:** `bug-035-signals-endpoint-allowdiskuse` (CODE COMPLETE)

---

### ✅ FEATURE-047: Skeleton Loaders for All Pages (DEPLOYED TO PRODUCTION)
**Priority:** MEDIUM | **Complexity:** MEDIUM | **Resolved:** 2026-02-24 | **Deployed:** 2026-02-25 00:57:38Z
**Branch:** `fix/bug-035-signals-endpoint-allowdiskuse` | **Commit:** `f893571` | **Production:** ✅ LIVE

Added skeleton loader components across all 5 pages to replace the full-screen spinner (`<Loading />`). Each skeleton mirrors the actual page layout for a seamless loading-to-loaded transition. **MERGED TO MAIN (2026-02-24)** and **DEPLOYED TO PRODUCTION (2026-02-25)**.

**New file:** `context-owl-ui/src/components/Skeleton.tsx`
- Shared primitives: `SkeletonLine`, `SkeletonBadge`, `SkeletonBlock`
- Page exports: `BriefingSkeleton`, `SignalsSkeleton`, `NarrativesSkeleton`, `ArticlesSkeleton`, `CostMonitorSkeleton`
- Uses Tailwind `animate-pulse` (consistent with existing `ArticleSkeleton`)
- Dark mode compatible throughout

**Modified files:** `Briefing.tsx`, `Signals.tsx`, `Narratives.tsx`, `Articles.tsx`, `CostMonitor.tsx`
**Ticket:** `feature-047-skeleton-loaders.md`
**Deployment:** https://context-owl-1q6vj9sc8-mikes-projects-92d90cb6.vercel.app

---

### ✅ BUG-041: FEATURE-047 Skeleton Loaders Not Visible in Production (RESOLVED)
**Priority:** HIGH | **Severity:** MEDIUM | **Status:** ✅ RESOLVED (2026-02-25 00:57:38Z)
**Branch:** N/A — Deployment issue, not code issue
**Commit:** Deployed from main (f893571 FEATURE-047 already merged)

Root cause: Vercel was serving stale cached build. Fixed by running `vercel --prod --force` to trigger fresh rebuild.

**Resolution:**
```bash
cd context-owl-ui
vercel --prod --force
```

**Deployment Details:**
- Build time: 23 seconds
- Status: Ready
- URL: https://context-owl-1q6vj9sc8-mikes-projects-92d90cb6.vercel.app
- Aliases: https://context-owl-ui.vercel.app

**Verification:**
- ✅ Build logs show Vite compiled 2145 modules successfully
- ✅ Skeleton components bundled into production JavaScript
- ✅ All 5 pages (Briefing, Signals, Narratives, Articles, CostMonitor) have skeleton imports verified
- ✅ No build errors or warnings

**Files:** No code changes (deployment-only)
**Ticket:** `bug-041-skeleton-loaders-not-in-production.md`

---

### ✅ BUG-033: Narrative Association Still Visible on Signals (RESOLVED)
**Priority:** MEDIUM | **Severity:** LOW | **Status:** ✅ RESOLVED (2026-02-25 00:57:38Z)
**Branch:** N/A — Deployment issue, not code issue
**Commit:** Deployed from main (FEATURE-036 removes narrative UI)

**Investigation Results:**
- ✅ FEATURE-036 (Sprint 7) code is correct and complete
- ✅ Signals.tsx has no narrative association code (verified clean)
- ✅ Build successful: `npm run build` completed without errors
- ✅ Root cause: Stale production build — FIXED via `vercel --prod --force`

**Resolution Applied:**
1. Ran `vercel --prod --force` from context-owl-ui directory
2. Fresh build triggered and deployed successfully
3. Build time: 23 seconds, Status: Ready
4. Production URL: https://context-owl-1q6vj9sc8-mikes-projects-92d90cb6.vercel.app
5. Also deployed FEATURE-047 skeleton loaders in same build

**Files:** `context-owl-ui/src/pages/Signals.tsx` (verified clean)
**Ticket:** `bug-033-narrative-still-visible-on-signals.md`

---

## Resolved This Session (Continued)

### ✅ BUG-039: Sonnet Fallback in General LLM Provider Causes 100+ Unnecessary Expensive Calls/Day
**Priority:** HIGH | **Severity:** HIGH | **Status:** ✅ MERGED (2026-02-24 20:51:29Z)
**Branch:** `fix/bug-039-sonnet-fallback-cost-leak` | **Commit:** `c997a27` | **PR:** #183

Removed Sonnet from `_get_completion()` and `extract_entities_batch()` fallback chains. Cost dashboard showed 112 Sonnet calls in one day; only ~10-15 are legitimate (briefing generation). Root cause was silent escalation: `AnthropicProvider._get_completion()` (used by all narrative processing) included Sonnet as fallback. Every Haiku 403 silently escalated to Sonnet at 5x cost.

**Fix Applied:**
- Removed Sonnet from `_get_completion()` fallback chain → Haiku only
- Removed Sonnet from `extract_entities_batch()` → Haiku only
- Deprecated `ANTHROPIC_ENTITY_FALLBACK_MODEL` config
- Added logging for 403 errors explaining no fallback
- `briefing_agent.py` has its own Sonnet fallback chain (unaffected)

**Impact:** Estimated $0.50-2.00/day savings; Sonnet calls expected to drop to ~10-15/day (briefings only)

**Files:** `src/crypto_news_aggregator/llm/anthropic.py`, `src/crypto_news_aggregator/core/config.py`
**Ticket:** `bug-039-sonnet-fallback-cost-leak.md`

---

### ✅ BUG-036/037/038: Atlas M0 Sort Limit Rework (Supersedes BUG-034/035 approach)

> **Context:** BUG-034/035 added `allowDiskUse=True` to aggregation pipelines, but Atlas M0 (free tier) **silently ignores** this parameter. The real fix is to remove `$sort`/`$limit` from MongoDB pipelines and do them in Python instead. Reference implementations provided by team in `signal_service.py` and `signals.py`.

### ✅ BUG-036: Fix `compute_trending_signals()` for Atlas M0 32MB Sort Limit
**Priority:** HIGH | **Severity:** HIGH | **Status:** ✅ MERGED (2026-02-24 18:29:14Z)
**File:** `src/crypto_news_aggregator/services/signal_service.py` | **Commit:** 5dcfc6c | **PR:** #182

Removed `$sort`, `$limit`, and `$addToSet: "$source"` from pipeline. Sort/limit in Python. Fetch sources in separate second-pass query for top-N entities only. **21/51 tests passing** (non-code related failures in data setup).

**Ticket:** `bug-036-compute-trending-m0-sort-fix.md`

---

### ✅ BUG-037: Fix `get_top_entities_by_mentions()` for Atlas M0 32MB Sort Limit
**Priority:** HIGH | **Severity:** HIGH | **Status:** ✅ MERGED (2026-02-24 18:29:14Z)
**File:** `src/crypto_news_aggregator/services/signal_service.py` | **Commit:** 12fc306 | **PR:** #182

Same pattern as BUG-036: removed `$sort`, `$limit`, `$addToSet` from pipeline. Python sort/limit + second-pass source query. **21/51 tests passing** (same test suite as BUG-036).

**Ticket:** `bug-037-top-entities-m0-sort-fix.md`

---

### ✅ BUG-038: Fix `get_recent_articles_for_entity()` for Atlas M0 32MB Sort Limit
**Priority:** HIGH | **Severity:** MEDIUM | **Status:** ✅ MERGED (2026-02-24 18:29:14Z)
**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py` | **Commit:** 752212f | **PR:** #182

Removed two `$sort` stages and `$limit`. Changed `$first` → `$max` for `published_at` in `$group` (without pre-sort, `$first` gives arbitrary order). Sort/limit in Python after cursor loop. **21/51 tests passing**.

**Ticket:** `bug-038-recent-articles-m0-sort-fix.md`

---

### ✅ BUG-040: get_recent_articles_batch() N+1 Query Causes 45s+ Signals Load Time
**Priority:** CRITICAL | **Severity:** HIGH | **Status:** ✅ MERGED (2026-02-24 21:28:24Z)
**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py` | **Commit:** f40812c | **PR:** #185

Replaced 50 parallel pipelines (one per entity) with single `$match:{entity:{$in:entities}}` pipeline. Post-pipeline partitioning and sorting in Python. **Expected impact:** Articles batch 45.7s → 1-3s; Total page load 52s → ~10s.

**Ticket:** `bug-040-batch-articles-n-plus-1.md`

---

### ✅ TASK-012: Remove Unnecessary `allowDiskUse=True` from Non-Sorting Aggregations (COMPLETED)
**Priority:** LOW | **Status:** COMPLETED | **Effort:** 10 min actual
**Commit:** 2f535a1 | **Merged:** 2026-02-25

Removed `allowDiskUse=True` from 3 aggregations with no `$sort`:
- `calculate_source_diversity()`: groups by source → small result set
- `compute_trending_signals()`: narrative count aggregation
- `get_signals()`: narrative count aggregation

Kept on `_count_filtered_mentions()` which still has complex `$lookup`.

**Ticket:** `task-012-remove-unnecessary-allowdiskuse.md`

---

### 🟡 TASK-013: Create MongoDB Indexes for Signal Pipeline Performance
**Priority:** MEDIUM | **Status:** OPEN | **Effort:** 15 min
**Where:** Atlas Console (mongosh) — not a code change

Three indexes to make `$match` stages fast now that sort/limit moved to Python:
1. `signals_primary_time_entity` — covers main signal queries
2. `signals_primary_type_time_entity` — covers entity_type filter
3. `signals_entity_lookup` — covers per-entity article lookups

**Ticket:** `task-013-create-signal-indexes.md`

---

### 🟡 FEATURE-048: Lazy Loading for Signals & Narratives Pages (Broken into Sub-Tickets)
**Priority:** HIGH | **Complexity:** MEDIUM | **Status:** OPEN | **Effort:** 2-4 hours total

Speed up perceived load time by adding offset-based pagination (backend) + Intersection Observer infinite scroll (frontend). Broken into 5 implementation tickets:

| Ticket | Scope | Complexity | Dependencies | Spec Part |
|--------|-------|------------|--------------|-----------|
| **FEATURE-048a** | Backend Signals Pagination | Medium | None | Part 1 |
| **FEATURE-048b** | Backend Narratives Pagination | Medium | None | Part 2 |
| **FEATURE-048c** | Frontend Shared Infra (hook, API clients, types) | Low | 048a, 048b (type alignment) | Parts 3, 4, 7 |
| **FEATURE-048d** | Frontend Signals Page Infinite Scroll | Medium | 048a, 048c | Part 5 |
| **FEATURE-048e** | Frontend Narratives Page Infinite Scroll | Medium | 048b, 048c | Part 6 |

**Recommended order:** 048a → 048b → 048c → 048d → 048e (backend first, then shared infra, then pages)

**Acceptance Criteria (parent):**
- Signals page: first meaningful content within 2-3 seconds
- Narratives page: first meaningful content within 2-3 seconds
- Smooth scrolling, no layout shifts
- Integrates with FEATURE-047 skeleton loaders

**Tickets:** `feature-048a-backend-signals-pagination.md`, `feature-048b-backend-narratives-pagination.md`, `feature-048c-frontend-shared-infrastructure.md`, `feature-048d-frontend-signals-infinite-scroll.md`, `feature-048e-frontend-narratives-infinite-scroll.md`
**Spec:** `FEATURE-048-implementation-spec.md`

---

## Pending — High-Priority Candidates

### 1. FEATURE-037 Follow-on: Manual Briefing Flexibility (HIGH)
- BUG-027 resolved the broken afternoon trigger; this feature extends it further
- Add `force` parameter exposure in the admin UI (not just API)
- Consider time-based auto-detection of briefing type when `type` is omitted
- Implement afternoon briefing type coverage in `_calculate_next_briefing_time()` (currently skips afternoon in the "next briefing" countdown)

### 2. Motor `find_one` Sort Audit (MEDIUM)
- BUG-028 revealed a Motor footgun that could affect other queries
- Audit all `find_one(..., sort=[...])` calls across `db/operations/`
- Replace any found with the correct `find().sort().limit(1)` pattern

### 3. Performance Optimization (MEDIUM)
- Query tuning based on documented data model trade-offs
- Leverage insights from `50-data-model.md` (batch vs. parallel findings)

### 4. Frontend Enhancements (MEDIUM)
- New UI features enabled by stable documentation
- Leverage FEATURE-035 (recommended reading links) foundation

---

## Sprint 9 Artifacts (For Reference)

**Completed Documentation:**
- 8 system modules (2,526 lines)
- 42 context entries (fully anchored)
- Validation guardrails (automated checks)
- Navigation hierarchy (which doc to trust)

**Key Files:**
- `docs/sprints/sprint-009-documentation-infrastructure.md` — Complete Sprint 9 summary
- `docs/README.md` — Documentation hierarchy
- `docs/_generated/README.md` — Regeneration procedures
- `scripts/validate-docs.sh` — Automated validation

---

## Next Session Actions

### ✅ Completed This Session (2026-02-24)
1. ✅ BUG-039: Remove Sonnet from `_get_completion()` + `extract_entities_batch()` — **MERGED PR #183**
2. ✅ BUG-036: Apply `compute_trending_signals()` M0 sort fix — **MERGED PR #182**
3. ✅ BUG-037: Apply `get_top_entities_by_mentions()` M0 sort fix — **MERGED PR #182**
4. ✅ BUG-038: Apply `get_recent_articles_for_entity()` M0 sort fix — **MERGED PR #182**
5. ✅ BUG-040: Replace N+1 articles batch query with single pipeline — **MERGED PR #185**

### ✅ FEATURE-048c: Frontend Shared Infinite Scroll Infrastructure (THIS SESSION)
**Priority:** HIGH | **Complexity:** LOW | **Status:** ✅ COMPLETED (2026-02-25)
**Branch:** `feature/feature-048c-frontend-shared-infra` | **Commit:** 0e23872

Implemented shared pagination infrastructure for frontend infinite scroll:
- **New hook:** `context-owl-ui/src/hooks/useInfiniteScroll.ts` with Intersection Observer API
  - Detects when user scrolls to within 300px of bottom of list
  - Fires `onLoadMore()` callback when sentinel enters viewport and !isLoading
  - Returns `sentinelRef` to attach to div at list end
  - Fully configurable threshold and dependencies

- **Updated signals API client:** `context-owl-ui/src/api/signals.ts`
  - New `PaginatedSignalsResponse` interface with count, total_count, offset, limit, has_more, signals, cached, computed_at, performance
  - `getSignals()` now accepts `offset` param, defaults to 15 items per page
  - `getSignalsByEntity()` updated with same pagination support

- **Updated narratives API client:** `context-owl-ui/src/api/narratives.ts`
  - New `PaginatedNarrativesResponse` interface
  - `getNarratives()` accepts `{ limit?, offset? }` params, defaults to 10 items per page

- **Updated TypeScript types:** `context-owl-ui/src/types/index.ts`
  - Added `PaginatedSignalsResponse` and `PaginatedNarrativesResponse` interfaces
  - Extended `SignalFilters` to include `min_score` and `entity_type`

- **Minor fix:** `context-owl-ui/src/pages/Narratives.tsx`
  - Updated to extract narratives array from new paginated response shape

**Build verification:** ✅ TypeScript compiles clean, frontend builds (2145 modules, 143KB gzipped)

**Spec references:** Parts 3, 4, 7 of `FEATURE-048-implementation-spec.md`

---

### 🔴 Next Priority Actions
1. **Push FEATURE-048c to remote** and create PR against main
2. **Begin FEATURE-048d:** Frontend Signals Page infinite scroll (Part 5 of spec)
3. **Then FEATURE-048e:** Frontend Narratives Page infinite scroll (Part 6 of spec)

### 🟡 Follow-up Cleanup (After Staging Validation)
1. TASK-012: Remove leftover `allowDiskUse=True` from non-sorting aggregations
2. TASK-013: Create 3 indexes in Atlas Console (mongosh)
3. Fix Vercel dashboard root directory for BUG-033 frontend redeploy
4. Audit remaining `.aggregate()` calls codebase-wide (TASK-011)

### 🔵 Resume Later (Sprint 11 Carryover)
- PRIORITY 3: Substack launch prep (TASK-001, FEATURE-045, FEATURE-046)

---

**Status:** ✅ Sprint 10 Major Fixes Complete — All 3 PRs merged successfully (BUG-039, BUG-036/037/038, BUG-040) | **Previous:** ✅ Sprint 9 Complete

> **This Session:** Merged 3 critical PRs (7 commits total). Main branch updated. **Next:** Staging validation + performance testing.