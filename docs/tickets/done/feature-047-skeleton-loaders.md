---
id: FEATURE-047
type: feature
status: completed
priority: medium
complexity: medium
created: 2026-02-23
updated: 2026-02-23
branch: fix/bug-035-signals-endpoint-allowdiskuse
---

# Skeleton Loaders for All Pages

## Problem/Opportunity
Currently, most pages show a basic "Loading..." text or blank state while fetching data from the API. The Narratives page has skeleton loaders but only for the overflow case (20+ stories in a single narrative). Every page should have proper shimmer skeleton loaders during initial data fetch to improve perceived performance and visual polish.

## Proposed Solution
Create a reusable `SkeletonLoader` component system and implement page-specific skeleton layouts for all 5 routes. Each skeleton should mirror the actual content layout so the transition from loading → loaded feels seamless.

## User Story
As a user, I want to see animated placeholder content while pages load so that the app feels fast and responsive, and I understand what kind of content is about to appear.

## Acceptance Criteria
- [x] **Briefing page** (`/`): Skeleton for briefing title, narrative text block, insights list, and recommendations section
- [x] **Signals page** (`/signals`): Skeleton signal cards with placeholder for entity name, velocity badge, type, sources, and article list
- [x] **Narratives page** (`/narratives`): Skeleton narrative cards with placeholder for title, description, entity tags, and article count. Existing 20+ story skeleton preserved (ArticleSkeleton unchanged)
- [x] **Articles page** (`/articles`): Skeleton article table rows with placeholder for title, source, date, and entity badges
- [x] **Cost Monitor page** (`/cost-monitor`): Skeleton for stat cards, chart area, and model breakdown table
- [x] All skeletons use consistent animation (Tailwind `animate-pulse` — matches existing `ArticleSkeleton` convention)
- [x] Skeleton layout matches actual content layout (no jarring shift on load)
- [x] Loading state transitions smoothly to loaded content (no flash)
- [x] Dark mode compatible (`dark:bg-gray-700` pattern throughout)

## Dependencies
- None (existing Narratives skeleton can be used as reference)

## Open Questions
- [x] Use Framer Motion or pure CSS keyframes? → Used Tailwind `animate-pulse` to match existing `ArticleSkeleton` convention. No new dependencies.
- [x] Show on every page navigation or only initial load? → React Query caching handles this naturally: skeletons show on initial load and hard refresh; subsequent navigations use cached data.

## Implementation Notes

### Reusable skeleton primitives
Create in `context-owl-ui/src/components/Skeleton.tsx`:
```typescript
// Base building blocks
export const SkeletonLine = ({ width, height }) => (...)   // Text line placeholder
export const SkeletonCard = ({ children }) => (...)          // Card container
export const SkeletonBadge = () => (...)                     // Small pill placeholder
export const SkeletonChart = ({ height }) => (...)           // Chart area placeholder
```

### Page-specific skeletons
Each page component replaces its loading state:
```typescript
// Before:
if (loading) return <div>Loading...</div>;

// After:
if (loading) return <BriefingSkeleton />;
```

### Files to create/modify
**New files:**
- `context-owl-ui/src/components/Skeleton.tsx` — Reusable skeleton primitives + shimmer animation

**Modified files:**
- `context-owl-ui/src/pages/Briefing.tsx` — Add `BriefingSkeleton`
- `context-owl-ui/src/pages/Signals.tsx` — Add `SignalsSkeleton`
- `context-owl-ui/src/pages/Narratives.tsx` — Integrate with existing skeleton or replace
- `context-owl-ui/src/pages/Articles.tsx` — Add `ArticlesSkeleton`
- `context-owl-ui/src/pages/CostMonitor.tsx` — Add `CostMonitorSkeleton`

### Shimmer animation (CSS approach)
```css
@keyframes shimmer {
  0% { background-position: -200px 0; }
  100% { background-position: calc(200px + 100%) 0; }
}

.skeleton {
  background: linear-gradient(90deg, #1a1a2e 25%, #2a2a4e 50%, #1a1a2e 75%);
  background-size: 200px 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}
```

### Estimated effort
- Skeleton primitives: 30 min
- Per-page skeleton: 20-30 min each × 5 pages
- Testing + dark mode: 30 min
- **Total: ~3-4 hours**

## Completion Summary
- **Actual complexity:** Low-medium — 1 new file, 5 page edits, ~90 minutes
- **Key decisions made:**
  - Used Tailwind `animate-pulse` instead of Framer Motion shimmer — consistent with existing `ArticleSkeleton`, no new deps
  - All skeleton components live in a single `Skeleton.tsx` file (not split per-page) — simpler, avoids file bloat
  - Articles page uses a table-row skeleton (mirrors the actual table layout) rather than card skeletons
  - CostMonitor skeleton uses block placeholders for chart/table areas — avoids replicating complex internal layout
- **Deviations from plan:** None. All 5 pages updated as specified.
- **New file:** `context-owl-ui/src/components/Skeleton.tsx` — primitives + 5 page exports
- **Modified files:** `Briefing.tsx`, `Signals.tsx`, `Narratives.tsx`, `Articles.tsx`, `CostMonitor.tsx`

## Merge Status (2026-02-24)
- **Commit:** `f893571` (feat(ui): FEATURE-047 - Add skeleton loaders for all pages)
- **Branch:** `fix/bug-035-signals-endpoint-allowdiskuse`
- **Status:** ✅ MERGED TO MAIN
- **Associated changes:** Committed alongside Railway deployment fix (NumPy 2.4.2)