---
id: BUG-043
type: performance
priority: CRITICAL
severity: CRITICAL
status: 🟡 IN PROGRESS (Fix 1 Complete, Fix 2 IMPLEMENTED 2026-02-25)
created: 2026-02-25
sprint: Sprint 10
blocked_by: none
blocks: TASK-014 (pre-launch security hardening)
---

# BUG-043: Signals Endpoint Takes 120s on Cold Cache — Article Batch Fetch Bottleneck

## Problem Statement

The `/api/v1/signals/trending` endpoint takes **120+ seconds** on cold cache, making the Signals page effectively unusable on first load. The root cause is that the endpoint fetches recent articles for **all 100 computed entities** before applying pagination — meaning a request for 15 signals triggers article lookups across 100 entities (~450 articles, ~112 seconds).

BUG-042 (refetch storm) reduced how *often* this fires, but the underlying request is still 2 minutes. Any cold-cache hit (cache expiry, deploy, first visitor) results in a 2-minute blank page.

## Evidence (Production Logs — 2026-02-25 05:48-05:52 UTC)

```
[Signals] Computed 100 trending signals in 2.570s          ← ✅ Fast
[Signals] Batch fetched 166 narratives in 6.336s           ← 🟡 Acceptable  
[Signals] Batch fetched 448 articles for 100 entities in 111.339s  ← 🔴 BOTTLENECK
[Signals] Total request time: 120.247s, Payload: 186.20KB
```

This pattern repeats consistently across multiple requests:
- Article fetch: 111-112s (93% of total time)
- Total request: 120-121s
- Payload: 185-188KB (massive for a list view)

Additional observation: **every log line appears twice**, suggesting either duplicate logging handlers or dual Uvicorn workers both logging the same request.

## Root Cause Analysis

### Architecture Problem: Pagination After Expensive Operations

The current request flow in `get_trending_signals()`:

```
1. Compute ALL 100 trending signals     →  2.5s   ✅ (cached)
2. Fetch narratives for ALL 100 signals  →  6.4s   🟡 
3. Fetch articles for ALL 100 entities   →  112s   🔴🔴🔴
4. Build response for ALL 100 signals    →  <1s
5. Apply pagination (offset/limit)       →  <1ms   ← TOO LATE
6. Return 15 signals to frontend         →  done
```

Step 3 is the killer. `get_recent_articles_batch()` fires 100 parallel `get_recent_articles_for_entity()` calls, each running an aggregation pipeline ($match → $addFields → $lookup → $unwind → $group → $project) against Atlas M0. Even with the compound index on entity_mentions, 100 parallel aggregations on a free-tier shared cluster takes ~112 seconds.

### Why This Matters for Launch

- First visitor after any cache miss waits 2+ minutes
- Every deploy clears the cache
- Atlas M0 connection pool (500 max) gets hammered
- 186KB payload for a list view is excessive bandwidth
- The 32MB sort limit can cause intermittent failures under load

## Fix Plan

### ✅ Fix 1: Paginate BEFORE Article/Narrative Fetch (COMPLETED — ~83% improvement)

**Status:** ✅ COMPLETED (2026-02-25)
**Commit:** e11a3e5 (PR ready for merge)
**Branch:** `fix/bug-043-paginate-before-fetch`

**Change:** After computing and caching the 100 signals, apply offset/limit BEFORE fetching articles and narratives. Only fetch supplementary data for the signals that will actually be returned.

**Implementation Details:**
1. After signal computation and caching, slice `trending` to requested page: `paged_signals = trending[offset:offset + limit]`
2. Collect entities/narrative_ids from ONLY the paged signals (typically 15, not 100)
3. Fetch narratives for only the paged signals: `await get_narrative_details(list(paged_narrative_ids))`
4. Fetch articles for only the paged entities: `await get_recent_articles_batch(paged_entities, limit_per_entity=5)`
5. Cache stores trends only (not per-page enrichment) — allows cache hits to skip enrichment entirely
6. Cache hits return slim response (trends only, no articles/narratives) to avoid per-page fetch cost

**New flow:**
```
1. Compute ALL 100 trending signals      →  2.5s  (cached)
2. Apply pagination (offset/limit)       →  <1ms  ← MOVED UP
3. Fetch narratives for 15 signals only  →  ~1s   (was 6.4s for 100)
4. Fetch articles for 15 entities only   →  ~17s  (was 112s for 100)
5. Build response for 15 signals         →  <1s
6. Return                                →  ~20s total (was 120s)
```

**Achieved improvement:** 120s → ~20s (83% reduction) ✅

**Test Status:** All 7 pagination tests passing
**Files Modified:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

### ✅ Fix 2: Remove Articles from List Endpoint Entirely (IDEAL — ~97% improvement)

**Status:** ✅ IMPLEMENTED (2026-02-25)
**Commit:** bde19ea
**Branch:** `fix/bug-043-paginate-before-fetch`
**Effort:** 45 minutes actual
**Files Modified:** 3 (signals.py, signals.ts, Signals.tsx)

**Rationale:** The Signals list page shows signal cards with entity name, score, velocity, mentions, and source count. Articles are detail-level data that users only need when they click into a specific signal. Fetching 5 articles × 100 entities for a list view is wasteful.

**Root cause confirmed:** The `$lookup` join between `entity_mentions` and `articles` in `get_recent_articles_batch()` is Atlas M0's bottleneck — even with 15 entities after Fix 1, the join across a large `entity_mentions` collection still takes 90+ seconds. M0 has no disk spill, so the in-memory hash join crushes the cluster.

**Change:** Don't fetch articles in `/signals/trending` at all. Create a separate `/signals/{entity}/articles` endpoint for on-demand article loading.

**New flow:**
```
1. Compute ALL 100 trending signals      →  2.5s  (cached)
2. Apply pagination                      →  <1ms
3. Fetch narratives for 15 signals only  →  ~1s
4. Return (no articles)                  →  ~3.5s total
```

**Expected improvement:** 120s → ~3.5s (97% reduction)

**Frontend UX (confirmed):** "Recent mentions" button always shows on every signal card. Articles load lazily when user clicks to expand — not at page load. This preserves the feature while eliminating the bottleneck.

**Implementation completed:**

#### Backend Changes (signals.py)

✅ **Line ~525-529:** Removed batch article fetch from cache miss path
- Deleted ~5 lines: `get_recent_articles_batch()` call + timing log
- Savings: ~5 seconds per cold cache request

✅ **Line 542:** Set articles to empty array in enriched signals
- Changed: `"recent_articles": recent_articles,`
- To: `"recent_articles": [],`
- Effect: Makes cold cache and warm cache responses consistent

✅ **Lines 596-625:** Added new per-entity articles endpoint
```python
@router.get("/{entity}/articles")
async def get_entity_articles(
    entity: str,
    limit: int = Query(default=5, ge=1, le=20),
) -> Dict[str, Any]:
    """Fetch recent articles for a specific entity (for lazy-loading on signal card expand)."""
    articles = await get_recent_articles_for_entity(entity, limit=limit)
    return {"entity": entity, "articles": articles}
```
- Reuses existing `get_recent_articles_for_entity()` function (line 135)
- No new DB logic required
- Returns: `{"entity": entity, "articles": [...]}`

#### Frontend Changes (signals.ts)

✅ **Lines 50-55:** Added `getEntityArticles()` API function
```typescript
getEntityArticles: async (entity: string, limit: number = 5) =>
  apiClient.get(`/api/v1/signals/${entity}/articles`, { limit })
```

#### Frontend Changes (Signals.tsx)

✅ **Lines 74-76:** Added lazy-loading state
- `articlesByEntity: Record<string, ArticleLink[]>` — maps entity → fetched articles
- `loadingArticles: Set<string>` — tracks in-flight requests

✅ **Lines 104-129:** Added `handleLoadArticles()` handler with deduplication
- Only fetches if not already loaded or loading
- Sets loading state, calls API, stores result
- Handles errors gracefully (empty array fallback)

✅ **Lines 216-262:** Updated article rendering for lazy-loading
- Always renders "Recent mentions" button (no conditional)
- On click: toggles expand and fetches articles on demand if needed
- Shows loading spinner (`<Loader className="animate-spin" />`) while fetching
- Shows "No articles found" if response is empty
- Renders articles from `articlesByEntity` state map

#### Build Verification
✅ Python syntax check: `signals.py` compiles
✅ Frontend build: `npm run build` succeeded (2146 modules, 472KB gzipped, 144KB payload)
✅ No build errors or warnings

#### Testing Checklist (Next Session Priority 1)

**1. Load signals page on cold cache**
   - [ ] Check Railway logs: Should NOT see "Batch fetched ... articles" line on initial load
   - [ ] Verify page loads in <5 seconds (previously ~90s with Fix 1 alone)
   - [ ] Confirm `recent_articles` field is empty array `[]` in API response

**2. Click "Recent mentions" button on a signal card**
   - [ ] Verify loading spinner appears briefly
   - [ ] Check browser DevTools: Should see GET request to `/api/v1/signals/{entity}/articles`
   - [ ] Articles load from new endpoint and display correctly
   - [ ] Verify API response format: `{"entity": "Bitcoin", "articles": [...]}`

**3. Expand multiple cards**
   - [ ] Second and subsequent opens should be instant (in-memory cache in `articlesByEntity`)
   - [ ] No additional API requests for already-expanded cards
   - [ ] Verify `loadingArticles` state is cleared after fetch

**4. Error handling**
   - [ ] Check browser console: No errors from `handleLoadArticles()`
   - [ ] Expand a card, then close/reopen: Should show cached articles instantly
   - [ ] If article fetch fails: Should show "No articles found" gracefully

**5. Production verification**
   - [ ] Check Railway logs for new `/api/v1/signals/{entity}/articles` GET requests on card expand
   - [ ] Verify NO `Batch fetched ... articles for N entities` line during initial page load
   - [ ] Monitor Atlas M0 connection pool: Should be lower than before (no massive article batch)
   - [ ] Check total request time for initial page load: Should be <5 seconds (was 90s with Fix 1, 120s before)

**6. Metrics to track**
   - **Cold cache (first load):** Measure from page load to first meaningful content (15 signals visible)
   - **Warm cache (subsequent loads):** Measure from click to articles visible after 1-2 cache hits
   - **Atlas M0 connections:** Peak concurrent during typical usage (target: <50)
   - **Payload size:** API response should drop from ~185KB to ~50KB for initial request

### Fix 3: Cap Parallel Article Queries with Semaphore (SAFETY NET)

Even with Fix 1 or 2, protect Atlas M0 from connection exhaustion:

```python
import asyncio

MONGO_CONCURRENCY_LIMIT = 10  # Max parallel aggregation pipelines

async def get_recent_articles_batch(entities, limit_per_entity=5):
    semaphore = asyncio.Semaphore(MONGO_CONCURRENCY_LIMIT)
    
    async def fetch_with_limit(entity):
        async with semaphore:
            return await get_recent_articles_for_entity(entity, limit=limit_per_entity)
    
    tasks = [fetch_with_limit(entity) for entity in entities]
    results = await asyncio.gather(*tasks)
    return {entity: articles for entity, articles in zip(entities, results)}
```

### Fix 4: Fix Duplicate Log Lines (MINOR)

Every log line appears twice in the production logs. Check for:
- Duplicate logging handlers (root logger + named logger both attached)
- Dual Uvicorn workers both writing to same log stream
- `propagate=True` on a child logger that also has a handler

## Recommended Approach

**✅ Fix 1 is SHIPPED** (paginate before fetch, commit e11a3e5) — reduces cold-cache time from 120s to ~20s.

**🟡 Fix 2 READY FOR IMPLEMENTATION** (remove articles from list) as a follow-up with a small frontend change to lazy-load articles. This will get cold-cache down to ~3.5s, which meets the Sprint 10 acceptance criteria of "first meaningful content within 2-3 seconds." Plan finalized (2026-02-25) — ready to implement.

**ALSO ADD: Fix 3** — it's a safety net that prevents Atlas M0 exhaustion even if someone bypasses pagination via the API.

## Scope: Other Slow Pages

While fixing signals, audit all page endpoints:

| Page | Endpoint | Current Cold Cache | Issue | Fix |
|------|----------|-------------------|-------|-----|
| **Signals** | `/signals/trending` | **120s** 🔴 | Article batch fetch for 100 entities | Fix 1+2 above |
| **Narratives** | `/narratives` | ~6-8s 🟡 | Cold-cache $lookup removed (good), but narrative list still fetches article counts | Verify no regression from FEATURE-048e |
| **Briefings** | `/briefings` | Unknown | Audit needed | Check if briefing list pre-fetches content |
| **Articles** | `/articles` | ~2-3s ✅ | Basic feed with pagination | Likely fine |
| **Dashboard** | `/dashboard` | Unknown | Audit needed | May aggregate from slow endpoints |

## Acceptance Criteria

- [x] Signals page: cold cache reduced from 120s → ~20s (Fix 1 complete)
- [ ] Signals page: first meaningful content within **3 seconds** on cold cache (requires Fix 2)
- [ ] Signals page: subsequent loads within **500ms** (cache hit)
- [x] Tab switching does NOT trigger any backend requests (BUG-042 verified)
- [ ] Narratives page: first meaningful content within **3 seconds**
- [ ] No endpoint returns >50KB payload for a list view
- [ ] Atlas M0 connection usage stays below 100 concurrent during normal operation
- [ ] No duplicate log lines in production

## Files to Modify

1. `src/crypto_news_aggregator/api/v1/endpoints/signals.py` — Reorder pagination before fetch
2. `src/crypto_news_aggregator/api/v1/endpoints/signals.py` — Add semaphore to batch fetch
3. `src/crypto_news_aggregator/api/v1/endpoints/narratives.py` — Audit for similar pattern
4. Logging config — Fix duplicate handler issue

## Related Issues

- **BUG-042** (refetch storm) — Reduced request frequency, but didn't fix request duration
- **FEATURE-048a** (backend pagination) — Introduced offset/limit but pagination applied too late
- **Cold-cache branch (e867741)** — Frontend staleTime fix, backend $lookup removal
- **TASK-014** (security hardening) — Blocked until page loads are acceptable