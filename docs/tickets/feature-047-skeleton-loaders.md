---
id: FEATURE-047
type: feature
status: backlog
priority: medium
complexity: medium
created: 2026-02-23
updated: 2026-02-23
---

# Skeleton Loaders for All Pages

## Problem/Opportunity
Currently, most pages show a basic "Loading..." text or blank state while fetching data from the API. The Narratives page has skeleton loaders but only for the overflow case (20+ stories in a single narrative). Every page should have proper shimmer skeleton loaders during initial data fetch to improve perceived performance and visual polish.

## Proposed Solution
Create a reusable `SkeletonLoader` component system and implement page-specific skeleton layouts for all 5 routes. Each skeleton should mirror the actual content layout so the transition from loading → loaded feels seamless.

## User Story
As a user, I want to see animated placeholder content while pages load so that the app feels fast and responsive, and I understand what kind of content is about to appear.

## Acceptance Criteria
- [ ] **Briefing page** (`/`): Skeleton for briefing title, narrative text block, insights list, and recommendations section
- [ ] **Signals page** (`/signals`): Skeleton signal cards with placeholder for entity name, velocity badge, type, sources, and article list
- [ ] **Narratives page** (`/narratives`): Skeleton narrative cards with placeholder for title, description, entity tags, and article count. Existing 20+ story skeleton should be preserved or integrated
- [ ] **Articles page** (`/articles`): Skeleton article cards with placeholder for title, source, date, and sentiment badge
- [ ] **Cost Monitor page** (`/cost-monitor`): Skeleton for stat cards, chart area, and model breakdown table
- [ ] All skeletons use consistent shimmer animation (Framer Motion or CSS animation)
- [ ] Skeleton layout matches actual content layout (no jarring shift on load)
- [ ] Loading state transitions smoothly to loaded content (no flash)
- [ ] Dark mode compatible

## Dependencies
- None (existing Narratives skeleton can be used as reference)

## Open Questions
- [ ] Use Framer Motion for shimmer (already discussed as desired for animations) or pure CSS keyframes? Framer is more flexible but adds bundle size if not already included.
- [ ] Should skeleton show on every page navigation, or only on initial load? (Recommendation: show on initial load and hard refresh; use cached data for subsequent navigations)

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
- Actual complexity:
- Key decisions made:
- Deviations from plan: