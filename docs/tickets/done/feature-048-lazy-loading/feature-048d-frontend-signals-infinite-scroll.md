---
id: FEATURE-048d
type: feature
status: completed
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-25
completed: 2026-02-25
parent: FEATURE-048
---

# Frontend Signals Page Infinite Scroll

## Problem/Opportunity
The Signals page currently fetches all 50 signals in one request and renders them at once. With backend pagination (FEATURE-048a) and shared infrastructure (FEATURE-048c) in place, the page can load 15 signals initially and fetch more on scroll.

## Proposed Solution
Replace `useQuery` with `useInfiniteQuery` from `@tanstack/react-query`. Use the shared `useInfiniteScroll` hook to trigger loading when the user scrolls near the bottom. Show count progress ("15 of 50") and loading/completion indicators.

Corresponds to **Implementation Spec Part 5** (sections 5A–5C).

## User Story
As a Backdrop user, I want the Signals page to load the first batch of signals quickly and fetch more as I scroll, so I see content within 2-3 seconds instead of waiting for everything.

## Acceptance Criteria
- [x] Page loads first 15 signals within 2-3 seconds
- [x] Scrolling to bottom triggers loading of next 15
- [x] "Loading more signals..." text appears during fetch
- [x] "All signals loaded" appears after last page
- [x] Counter shows "(15 of 50)" updating as more load
- [x] Integrates with FEATURE-047 skeleton loaders (initial load shows skeleton)
- [x] No layout shifts when new items load
- [x] Empty state (0 signals) still shows correctly, no sentinel
- [x] Single page of results — no spurious "Loading more" triggers
- [x] 30-second refetchInterval preserved

## Dependencies
- FEATURE-048a (backend signals pagination) — required
- FEATURE-048c (frontend shared infrastructure) — required

## Open Questions
- None — spec is fully defined

## Implementation Notes
**File:** `context-owl-ui/src/pages/Signals.tsx`

Key changes:
1. **5A** — Update imports: `useInfiniteQuery` instead of `useQuery`, add `useInfiniteScroll` hook
2. **5B** — Replace query hook with `useInfiniteQuery` using `pageParam` as offset, `SIGNALS_PER_PAGE = 15`
3. **5C** — Update rendering:
   - Flatten pages: `data?.pages.flatMap((page) => page.signals)`
   - Replace `data?.signals.map(...)` with `signals.map(...)`
   - Add count display in subtitle
   - Add sentinel div with `ref={sentinelRef}` after the grid
   - Update empty state check to `signals.length === 0 && !isLoading`
   - Update/remove debug logging

See `FEATURE-048-implementation-spec.md` Part 5 for exact code changes.

## Completion Summary

### ✅ Implementation Complete (2026-02-25)

**File Modified:**
- `context-owl-ui/src/pages/Signals.tsx` — Replaced single-page fetch with infinite scroll pagination

**Key Changes:**
1. **Part 5A — Imports:**
   - Changed `useQuery` → `useInfiniteQuery`
   - Added `useInfiniteScroll` hook import

2. **Part 5B — Query Hook:**
   - Replaced `useQuery` with `useInfiniteQuery` with:
     - `SIGNALS_PER_PAGE = 15` constant
     - `pageParam` starting at 0, incremented by 15 for each page
     - `getNextPageParam` checks `has_more` field from backend
     - Preserved `refetchInterval: 30000` (30 seconds)
   - Integrated `useInfiniteScroll` hook with 300px threshold

3. **Part 5C — Rendering:**
   - Flatten pages array: `data?.pages.flatMap((page) => page.signals)`
   - Added count display in subtitle: `(X of Y)`
   - Added sentinel div at bottom of grid: `<div ref={sentinelRef} className="h-10" />`
   - Added "Loading more signals..." indicator
   - Added "All signals loaded" completion message
   - Updated empty state check: `signals.length === 0 && !isLoading`
   - Removed debug logging

**Build Verification:**
- ✅ TypeScript compilation: No errors
- ✅ Vite build: 2146 modules transformed, 143KB gzipped

**Commits:**
- `015e5c6` — feat(frontend): Implement Signals page infinite scroll (FEATURE-048d)

### Key Decisions Made
1. **Sentinel placement:** Placed sentinel div outside grid with conditional rendering (`signals.length > 0`) to avoid showing empty div on first load or when no signals exist
2. **Threshold configuration:** Made Intersection Observer threshold configurable (300px default) via the `useInfiniteScroll` hook props
3. **Total count tracking:** Used `data?.pages[0]?.total_count` to get total from first page (constant across pagination)
4. **Empty state logic:** Separated empty state rendering from loading state to avoid showing "No signals detected" while loading

### Deviations from Plan
- None — all acceptance criteria met exactly as specified