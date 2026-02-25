---
id: FEATURE-048
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
---

# FEATURE-048: Lazy Loading for Signals & Narratives Pages

## Problem/Opportunity
The Signals and Narratives pages load all data upfront before rendering any content. Even after BUG-040's N+1 fix (45s → ~10s), the user still waits for the full payload before seeing meaningful content. Lazy loading (or a similar technique) would show above-the-fold content immediately and progressively load the rest, dramatically improving perceived performance.

## Proposed Solution
Evaluate and implement the best performance technique for each page. Options include:

1. **Lazy loading / infinite scroll** — Load first N items, fetch more on scroll
2. **Pagination** — Server-side page-based loading with cursor/offset
3. **Virtualized lists** — Render only visible DOM elements (react-window / react-virtuoso)
4. **Progressive hydration** — Load skeleton → trending entities first → articles second
5. **Combination approach** — e.g., paginated API + virtualized rendering

The right approach depends on data volume and UX goals. Signals page has ~50 entities with 5 articles each; Narratives page has variable-length narrative lists.

## User Story
As a user, I want the Signals and Narratives pages to show content quickly so that I can start reading without waiting for all data to load.

## Acceptance Criteria
- [ ] Signals page shows first meaningful content within 2-3 seconds
- [ ] Narratives page shows first meaningful content within 2-3 seconds
- [ ] Scrolling through full content is smooth (no jank or layout shifts)
- [ ] Skeleton loaders (FEATURE-047) integrate cleanly with progressive loading
- [ ] No regressions in data accuracy or ordering
- [ ] Mobile performance acceptable

## Dependencies
- ✅ BUG-040 (N+1 query fix) — MERGED
- ✅ BUG-036/037/038 (Atlas M0 sort rework) — MERGED
- ✅ FEATURE-047 (skeleton loaders) — MERGED
- TASK-012 (allowDiskUse cleanup) — should complete first for clean codebase

## Open Questions
- [ ] What's the current measured page load time post-BUG-040 fixes? (Need staging validation)
- [ ] Should Signals use infinite scroll or pagination? (UX decision)
- [ ] Does the API need new endpoints (e.g., paginated trending) or can we handle client-side?
- [ ] What's the target entity count — will it grow beyond 50?

## Implementation Notes
<!-- Fill in during development -->

## Completion Summary
<!-- Fill in after completion -->
- Actual complexity:
- Key decisions made:
- Deviations from plan: