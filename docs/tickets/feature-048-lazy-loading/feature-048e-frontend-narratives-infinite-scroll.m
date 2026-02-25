---
id: FEATURE-048e
type: feature
status: open
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
parent: FEATURE-048
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
- [ ] Page loads first 10 narratives within 2-3 seconds
- [ ] Scrolling to bottom triggers loading of next 10
- [ ] "Loading more narratives..." text appears during fetch
- [ ] "All narratives loaded" appears after last page
- [ ] Counter shows "(10 of 35)" updating as more load
- [ ] `?highlight=` query param still works for loaded narratives
- [ ] Expanding a narrative's articles still works (existing article pagination untouched)
- [ ] Integrates with FEATURE-047 skeleton loaders
- [ ] No layout shifts when new items load
- [ ] Empty state (0 narratives) still shows correctly
- [ ] 60-second refetchInterval preserved

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
- Actual complexity:
- Key decisions made:
- Deviations from plan: