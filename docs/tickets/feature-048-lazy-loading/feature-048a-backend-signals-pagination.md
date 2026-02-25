---
id: FEATURE-048a
type: feature
status: completed
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
completed: 2026-02-24
parent: FEATURE-048
commit: f9511d8
---

# Backend Signals Pagination

## Problem/Opportunity
The `/api/v1/signals/trending` endpoint returns all signals in a single payload. Even after BUG-040 reduced load time from 45s to ~10s, users wait for the full response before seeing any content. Adding server-side pagination enables the frontend to request smaller slices and render progressively.

## Proposed Solution
Add offset-based pagination to the trending signals endpoint. Compute and cache the full enriched signal set (up to 100), then return paginated slices from cache. This keeps subsequent page requests fast (cache hit) while reducing initial payload size.

Corresponds to **Implementation Spec Part 1** (sections 1A–1D).

## User Story
As a Backdrop user, I want the signals API to support pagination so the frontend can load signals incrementally instead of waiting for the entire dataset.

## Acceptance Criteria
- [x] `GET /api/v1/signals/trending` accepts `offset` param (default 0) and `limit` defaults to 15 (was 50)
- [x] Response includes `total_count`, `offset`, `limit`, `has_more` fields
- [x] Cache key excludes offset/limit (bumped to v3) so all pages share one cache entry
- [x] Cache hit path returns paginated slice with correct metadata
- [x] Full signal set (up to 100) is computed, enriched, and cached; pagination applied after
- [x] `GET /api/v1/signals/trending` returns 15 items, `has_more: true`, `offset: 0`
- [x] `GET /api/v1/signals/trending?offset=15` returns next 15, `offset: 15`
- [x] `GET /api/v1/signals/trending?offset=45` returns remainder, `has_more: false`
- [x] Second request within 60s returns `cached: true`
- [x] Existing filters (min_score, entity_type, timeframe) still work

## Dependencies
- None (can be implemented independently)

## Open Questions
- None — spec is fully defined

## Implementation Notes
**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

Key changes:
1. **1A** — Add `offset` param to function signature, change `limit` default 50→15
2. **1B** — Always compute full set (`max_compute=100`), paginate after
3. **1C** — Cache key `signals:trending:v3:...` excludes offset/limit; cache hit returns slice
4. **1D** — Enrich all signals, cache full enriched list, return `page_signals[offset:offset+limit]` with pagination metadata

See `FEATURE-048-implementation-spec.md` Part 1 for exact code changes.

## Completion Summary

**Status:** ✅ COMPLETED (2026-02-24)

**Actual Complexity:** Medium (as planned) — 30-45 minutes actual

**Implementation Details:**
- ✅ Modified `GET /api/v1/signals/trending` endpoint to accept `offset` and `limit` parameters
- ✅ Changed default limit from 50 → 15 (one page size)
- ✅ Implemented full-set caching strategy: always compute max_compute=100, slice after retrieval
- ✅ Updated cache key to v3, excluding offset/limit so all pages share same cache entry
- ✅ Cache hit path now slices full cached result and returns pagination metadata
- ✅ Response includes: count, total_count, offset, limit, has_more, filters, signals, cached, computed_at, performance

**Testing:**
- ✅ Added 7 new pagination tests:
  - test_get_trending_signals_pagination_default_limit
  - test_get_trending_signals_pagination_with_offset
  - test_get_trending_signals_pagination_has_more_flag
  - test_get_trending_signals_pagination_caching_full_set
  - test_get_trending_signals_pagination_response_structure
  - test_get_trending_signals_pagination_count_field
  - test_get_trending_signals_pagination_last_page
- ✅ Updated 5 existing tests to validate new pagination fields
- ✅ All 12 tests passing

**Key Decisions Made:**
1. **Full-set caching pattern:** Cache computes full set (up to 100) for freshness, pagination applied client-side. This ensures cache is reusable across all offset values and reduces wasted computation.
2. **Default limit=15:** Balances payload size with number of requests. Most users will see initial page with 15 cards in < 3 seconds.
3. **Cache key v3:** Excludes offset/limit so second request for offset=15 hits same cache as offset=0, enabling instant load for subsequent pages.

**Deviations from Plan:**
- None — implementation followed spec exactly (FEATURE-048-implementation-spec.md Part 1)