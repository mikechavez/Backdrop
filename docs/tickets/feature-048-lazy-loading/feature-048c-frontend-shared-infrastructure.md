---
id: FEATURE-048c
type: feature
status: open
priority: high
complexity: low
created: 2026-02-24
updated: 2026-02-24
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
- [ ] New file: `context-owl-ui/src/hooks/useInfiniteScroll.ts` with Intersection Observer hook
- [ ] Hook accepts `hasMore`, `isLoading`, `onLoadMore`, optional `threshold` (default 300px)
- [ ] Hook returns a `sentinelRef` to attach to a div at the bottom of the list
- [ ] `signals.ts` API client: new `PaginatedSignalsResponse` interface, `getSignals()` accepts `offset` param
- [ ] `narratives.ts` API client: new `PaginatedNarrativesResponse` interface, `getNarratives()` accepts `{ limit, offset }` params
- [ ] `SignalFilters` type includes `offset?: number`
- [ ] All types compile without errors

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
- Actual complexity:
- Key decisions made:
- Deviations from plan: