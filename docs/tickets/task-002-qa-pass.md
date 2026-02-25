---
id: TASK-002
type: task
status: backlog
priority: high
created: 2026-02-23
updated: 2026-02-23
---

# Mobile/Desktop QA + Fix Broken Animations

## Objective
Full QA pass on the interactive Cognitive Debt Simulator after all code modifications (TASK-001, FEATURE-045, FEATURE-046) are complete. Fix any bugs found.

## Context
The interactive site has never been tested on mobile. Multiple code changes are being made in a compressed timeframe. QA must catch issues before public launch.

## Tool Routing
- Tool: Claude Code
- Model: Sonnet

## Execution Steps

### Desktop (Chrome, Firefox, Safari)
- [ ] All sections render correctly
- [ ] Scroll-triggered reveal animations fire
- [ ] Cognitive Debt Graph canvas draws correctly
- [ ] Sliders work (autonomy, scope, verify)
- [ ] "Apply Context Engineering" button works
- [ ] Routing mini-game: all 8 tasks render
- [ ] Routing mini-game: scoring works correctly
- [ ] Share/copy buttons appear after scoring
- [ ] All Substack links clickable
- [ ] Subscribe embed loads
- [ ] Nav bar blur effect works on scroll
- [ ] No console errors

### Mobile (iOS Safari, Android Chrome)
- [ ] Hero fits viewport, no horizontal overflow
- [ ] Text readable without zooming
- [ ] Sliders draggable on touch (no scroll conflict)
- [ ] Canvas graph renders at correct responsive size
- [ ] Routing game buttons tappable (min 44px touch target)
- [ ] Share buttons work on mobile browsers
- [ ] Nav doesn't overlap content
- [ ] No horizontal scroll anywhere

### Known Risk Areas
- Canvas `#graphCanvas` may need responsive width/height
- Routing game button grid may overflow narrow screens
- Fixed nav may overlap hero on short viewports
- Slider touch events may conflict with page scroll
- Substack iframe may render white on dark background

## Files Involved
- `cognitive-debt-simulator-v5.html` (fix bugs only — no new features)

## Acceptance Criteria
- [ ] Zero console errors on all tested browsers
- [ ] All interactive elements functional on mobile + desktop
- [ ] No layout overflow or broken elements
- [ ] Performance acceptable (no scroll jank)

## Dependencies
- TASK-001 (placeholders replaced)
- FEATURE-045 (share buttons added)
- FEATURE-046 (email capture added)

## Out of Scope
- New features or redesign
- Performance optimization beyond obvious fixes
- Cross-browser testing beyond Chrome/Firefox/Safari
