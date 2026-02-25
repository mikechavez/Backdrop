---
id: FEATURE-048d
type: feature
status: open
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
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
- [ ] Page loads first 15 signals within 2-3 seconds
- [ ] Scrolling to bottom triggers loading of next 15
- [ ] "Loading more signals..." text appears during fetch
- [ ] "All signals loaded" appears after last page
- [ ] Counter shows "(15 of 50)" updating as more load
- [ ] Integrates with FEATURE-047 skeleton loaders (initial load shows skeleton)
- [ ] No layout shifts when new items load
- [ ] Empty state (0 signals) still shows correctly, no sentinel
- [ ] Single page of results — no spurious "Loading more" triggers
- [ ] 30-second refetchInterval preserved

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
- Actual complexity:
- Key decisions made:
- Deviations from plan: