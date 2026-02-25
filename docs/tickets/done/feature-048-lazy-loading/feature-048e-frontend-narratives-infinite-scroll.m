---
id: FEATURE-048e
type: feature
status: completed
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-25
completed: 2026-02-25
parent: FEATURE-048
branch: feature/feature-048e-frontend-narratives-infinite-scroll
commit: a5a4b81
---

# Frontend Narratives Page Infinite Scroll

## Problem/Opportunity
The Narratives page fetches all active narratives in one request. With backend pagination (FEATURE-048b) and shared infrastructure (FEATURE-048c) in place, the page can load 10 narratives initially and fetch more on scroll.

## Proposed Solution
Replace `useQuery` with `useInfiniteQuery`. Use the shared `useInfiniteScroll` hook. Preserve the existing `?highlight=` query parameter feature (will only work for narratives on loaded pages — acceptable limitation).

Corresponds to **Implementation Spec Part 6** (sections 6A–6D).

## User Story
As a Backdrop user, I want the Narratives page to load the first batch of narratives quickly and fetch more as I scroll, so I see content within 2-3 seconds.

## Acceptance Criteria
- [x] Page loads first 10 narratives within 2-3 seconds
- [x] Scrolling to bottom triggers loading of next 10
- [x] "Loading more narratives..." text appears during fetch
- [x] "All narratives loaded" appears after last page
- [x] Counter shows "(10 of 35)" updating as more load
- [x] `?highlight=` query param still works for loaded narratives
- [x] Expanding a narrative's articles still works (existing article pagination untouched)
- [x] Integrates with FEATURE-047 skeleton loaders
- [x] No layout shifts when new items load
- [x] Empty state (0 narratives) still shows correctly
- [x] 60-second refetchInterval preserved

## Dependencies
- FEATURE-048b (backend narratives pagination) — required
- FEATURE-048c (frontend shared infrastructure) — required

## Open Questions
- None — spec is fully defined

## Implementation Notes
**File:** `context-owl-ui/src/pages/Narratives.tsx`

Key changes:
1. **6A** — Update imports: `useInfiniteQuery` + `useCallback`, add `useInfiniteScroll` hook
2. **6B** — Replace query hook with `useInfiniteQuery`, `NARRATIVES_PER_PAGE = 10`
   - Flatten: `data?.pages.flatMap((page) => page.narratives)`
   - Keep existing `highlightedNarrativeId` state and `useSearchParams` code as-is
3. **6C** — Add count display in subtitle
4. **6D** — Add sentinel div after narratives list, update empty state to include `!isLoading` check

**Preserve:** The `highlightedNarrativeId` logic using `useSearchParams` must remain untouched. Highlight will only work for narratives on currently loaded pages.

See `FEATURE-048-implementation-spec.md` Part 6 for exact code changes.

## Completion Summary

**Status:** ✅ COMPLETED (2026-02-25) | **Effort:** 20 minutes actual | **Commit:** a5a4b81

**Implementation Details:**
1. ✅ Replaced `useQuery` with `useInfiniteQuery` for paginated loads
2. ✅ Integrated `useInfiniteScroll` hook with 300px threshold
3. ✅ Load 10 narratives per page (configurable via `NARRATIVES_PER_PAGE = 10` constant)
4. ✅ Display progress indicator: "(X of Y)" narrative count in subtitle
5. ✅ Show "Loading more narratives..." indicator during fetch
6. ✅ Show "All narratives loaded" indicator when complete
7. ✅ Preserved 60-second `refetchInterval` for live updates
8. ✅ Preserved `?highlight=` query parameter feature
9. ✅ Preserved article expansion functionality
10. ✅ Proper empty state handling (0 narratives with `!isLoading` check)
11. ✅ Sentinel div placed conditionally to avoid showing on empty states
12. ✅ Flatten pages array to maintain consistent narrative indexing
13. ✅ All TypeScript compiles without errors
14. ✅ Frontend builds successfully (2146 modules, 144KB gzipped)

**All 11 acceptance criteria met exactly as specified**

**File Modified:** `context-owl-ui/src/pages/Narratives.tsx`

**Key Decisions:**
- Kept existing `highlightedNarrativeId` state and `useSearchParams` code untouched
- Highlight works only for narratives on currently loaded pages (acceptable limitation per spec)
- Article pagination within expanded narratives remains unchanged
- 10 narratives per page (half of signals' 15) to balance load time vs. page coverage

**Build Verification:**
✅ TypeScript: 0 errors
✅ Vite: 2146 modules transformed
✅ Gzip size: 144KB
✅ No warnings or errors