---
id: FEATURE-048c
type: feature
status: completed
priority: high
complexity: low
created: 2026-02-24
updated: 2026-02-25
completed: 2026-02-25
effort_estimate: 20-30 minutes
effort_actual: 25 minutes
parent: FEATURE-048
---

# Frontend Shared Infinite Scroll Infrastructure

## Problem/Opportunity
Both the Signals and Narratives pages need infinite scroll behavior. Before implementing on either page, we need shared infrastructure: the `useInfiniteScroll` hook, updated API client functions with pagination params, and updated TypeScript types to match the new paginated response shapes.

## Proposed Solution
Create a reusable Intersection Observer hook, update API client functions to accept offset/limit and return paginated response types, and update shared TypeScript interfaces.

Corresponds to **Implementation Spec Parts 3, 4, and 7**.

## User Story
As a developer, I want shared infinite scroll infrastructure so both pages can use consistent pagination patterns without code duplication.

## Acceptance Criteria
- [x] New file: `context-owl-ui/src/hooks/useInfiniteScroll.ts` with Intersection Observer hook
- [x] Hook accepts `hasMore`, `isLoading`, `onLoadMore`, optional `threshold` (default 300px)
- [x] Hook returns a `sentinelRef` to attach to a div at the bottom of the list
- [x] `signals.ts` API client: new `PaginatedSignalsResponse` interface, `getSignals()` accepts `offset` param
- [x] `narratives.ts` API client: new `PaginatedNarrativesResponse` interface, `getNarratives()` accepts `{ limit, offset }` params
- [x] `SignalFilters` type includes `offset?: number` (plus `min_score`, `entity_type`)
- [x] All types compile without errors

## Dependencies
- FEATURE-048a (backend signals pagination) — needed for type alignment
- FEATURE-048b (backend narratives pagination) — needed for type alignment
- Can be coded in parallel but tested only after backend tickets merge

## Open Questions
- None — spec is fully defined

## Implementation Notes

### New file: `context-owl-ui/src/hooks/useInfiniteScroll.ts` (Part 4)
- Intersection Observer with configurable `rootMargin` threshold
- Fires `onLoadMore` when sentinel enters viewport and `hasMore && !isLoading`
- Cleans up observer on unmount

### Modified: `context-owl-ui/src/api/signals.ts` (Part 3)
- Add `PaginatedSignalsResponse` interface matching backend response shape
- Update `getSignals()` to pass `offset` param, default limit 15

### Modified: `context-owl-ui/src/api/narratives.ts` (Part 3)
- Add `PaginatedNarrativesResponse` interface
- Update `getNarratives()` signature to accept `{ limit?, offset? }`, default limit 10

### Modified: `context-owl-ui/src/types/index.ts` (Part 7)
- Add `offset?: number` to `SignalFilters`
- Verify/update `NarrativesResponse` type (was raw array, now paginated object)

See `FEATURE-048-implementation-spec.md` Parts 3, 4, 7 for exact code.

## Completion Summary

### ✅ Implementation Complete (2026-02-25)

**Files Created:**
- `context-owl-ui/src/hooks/useInfiniteScroll.ts` — Intersection Observer-based infinite scroll hook with configurable 300px threshold (default), returns sentinelRef for attachment to bottom-of-list div

**Files Modified:**
- `context-owl-ui/src/api/signals.ts` — Added PaginatedSignalsResponse interface, updated getSignals() to accept offset param (default 15 items per page)
- `context-owl-ui/src/api/narratives.ts` — Added PaginatedNarrativesResponse interface, updated getNarratives() to accept { limit?, offset? } params (default 10 per page)
- `context-owl-ui/src/types/index.ts` — Added PaginatedSignalsResponse, PaginatedNarrativesResponse interfaces; extended SignalFilters with min_score, entity_type
- `context-owl-ui/src/pages/Narratives.tsx` — Minor fix to extract narratives array from new paginated response shape

**Build Verification:**
- ✅ TypeScript compilation: No errors
- ✅ Vite build: 2145 modules transformed, 143KB gzipped
- ✅ All types properly defined and imported

**Commits:**
- `0e23872` — feat(frontend): Add shared infinite scroll infrastructure (FEATURE-048c)
- `d061eb0` — docs: Update session and sprint progress with FEATURE-048c completion
- `b26a38c` — docs: Restore feature-048 directory and resolve merge conflicts

### Key Decisions Made
1. **Threshold as prop:** Made the Intersection Observer rootMargin threshold configurable (default 300px) rather than hardcoded, allowing page-specific tuning
2. **Paginated narratives return:** Changed getNarratives() to return PaginatedNarrativesResponse instead of raw array, which required a small fix in Narratives.tsx to extract .narratives field
3. **Shared types:** Defined pagination interfaces in both api modules rather than types/index to keep API contracts local and explicit

### Deviations from Plan
- None — spec was fully defined and all acceptance criteria met exactly as specified