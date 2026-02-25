---
id: FEATURE-048b
type: feature
status: open
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
parent: FEATURE-048
---

# Backend Narratives Pagination

## Problem/Opportunity
The `/api/v1/narratives/active` endpoint returns all active narratives as a raw array. Like signals, the full payload blocks frontend rendering. Adding pagination here enables incremental loading on the Narratives page.

## Proposed Solution
Add offset-based pagination to the active narratives endpoint. Wrap the response in a `PaginatedNarrativesResponse` model (breaking change from raw array to object). Cache the full narrative list and paginate from cache on subsequent requests.

Corresponds to **Implementation Spec Part 2** (sections 2A–2H).

**IMPORTANT:** The `/active` endpoint has its own inline aggregation pipeline — do NOT modify `db/operations/narratives.py`.

## User Story
As a Backdrop user, I want the narratives API to support pagination so the frontend can load narratives incrementally.

## Acceptance Criteria
- [ ] New `PaginatedNarrativesResponse` Pydantic model with `narratives`, `total_count`, `offset`, `limit`, `has_more`
- [ ] Endpoint response_model changed from `List[NarrativeResponse]` to `PaginatedNarrativesResponse`
- [ ] `limit` default changed from 50→10, `offset` param added (default 0)
- [ ] Cache key bumped to v2, excludes offset/limit
- [ ] Cache hit returns paginated slice with correct metadata
- [ ] Pipeline `$limit` changed to 200 (fetch full set for caching)
- [ ] Empty result returns `PaginatedNarrativesResponse` with `total_count: 0`
- [ ] `GET /api/v1/narratives/active` returns 10 narratives with pagination metadata
- [ ] `GET /api/v1/narratives/active?offset=10` returns next page
- [ ] Existing `lifecycle_state` filter still works
- [ ] Article pagination within narratives is NOT touched

## Dependencies
- None (can be implemented independently, parallel with FEATURE-048a)

## Open Questions
- None — spec is fully defined

## Implementation Notes
**File:** `src/crypto_news_aggregator/api/v1/endpoints/narratives.py`

Key changes:
1. **2A** — Add `PaginatedNarrativesResponse` model after `NarrativeResponse`
2. **2B** — Add `offset` param, change `limit` default 50→10
3. **2C** — Cache key `narratives:active:v2:...` excludes offset/limit
4. **2D** — Cache hit returns paginated `PaginatedNarrativesResponse`
5. **2E** — Pipeline `$limit` → 200 (full set for caching)
6. **2F** — Cache full list, return paginated slice
7. **2G** — Empty result returns proper paginated response (not `[]`)
8. **2H** — Verify no other callers affected (`grep -rn "get_active_narratives"`)

See `FEATURE-048-implementation-spec.md` Part 2 for exact code changes.

## Completion Summary
- **Status:** ✅ COMPLETED (2026-02-24)
- **Actual complexity:** MEDIUM (as expected)
- **Effort:** 30-45 minutes actual
- **Commit:** 50e0f32
- **Branch:** `feature/feature-048b-backend-narratives-pagination`

### What Was Implemented
1. ✅ Added `PaginatedNarrativesResponse` Pydantic model with pagination metadata
2. ✅ Updated `/api/v1/narratives/active` endpoint response model
3. ✅ Changed default limit from 50 → 10, added `offset` parameter
4. ✅ Bumped cache key to v2 (excludes offset/limit for efficient caching)
5. ✅ Implemented cache hit pagination (slice from full cached result)
6. ✅ Changed pipeline `$limit` to 200 (fetch full set for caching)
7. ✅ Updated empty result handling to return proper `PaginatedNarrativesResponse`
8. ✅ Added 10 comprehensive pagination tests (100% passing)

### Testing
- **Test file:** `tests/api/test_narratives_active_pagination.py`
- **Test count:** 10 tests
- **Pass rate:** 10/10 (100%) ✅
- **Coverage:** Default pagination, multi-page navigation, custom limits, lifecycle filters, has_more flag, consistency checks, parameter validation

### Key Decisions
- Used default limit of 10 (matching FEATURE-048a signals limit) for consistent UX
- Cache full narrative list (up to 200) to support all pagination pages from single cache hit
- Kept lifecycle_state filter working while adding pagination (orthogonal features)
- Did NOT modify article pagination within narratives (nested pagination untouched)

### Deviations from Plan
- None — implementation followed spec exactly