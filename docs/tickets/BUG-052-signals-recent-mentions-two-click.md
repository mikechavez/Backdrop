---
id: BUG-052
type: bug
status: completed
priority: medium
severity: medium
created: 2026-02-25
updated: 2026-02-25
---

# "Recent Mentions" Button Requires Two Clicks (BUG-052)

## Problem
The "Recent mentions" button on Signals cards required two clicks to expand and show articles. First click fetched the data but didn't expand the UI. Second click opened the expanded section.

## Expected Behavior
- Single click should immediately expand the "Recent mentions" section
- Articles should load in the background without blocking the UI
- Hover state should provide clear visual feedback

## Actual Behavior
- First click: Button fetches articles but section doesn't expand (user sees nothing)
- Second click: Section expands and articles are now visible
- Hover state had minimal visual feedback

## Steps to Reproduce
1. Navigate to Signals page
2. Click "▶ Recent mentions" button on any signal card
3. Observe that section does not expand immediately
4. Click again to see section expand with articles

## Environment
- Environment: production
- Browser/Client: All browsers
- User impact: medium (confusing UX, two clicks required)

---

## Resolution

**Status:** ✅ COMPLETED
**Fixed:** 2026-02-25
**Branch:** fix/task-016-observability-clamps
**Commit:** 25f1558

### Root Cause
Button click handler was `async` and used `await handleLoadArticles()` before setting expanded state. This meant:
- Expanded state was only set AFTER articles finished loading
- UI couldn't expand until fetch completed
- Users had to click again once articles were ready

**Code location:** `context-owl-ui/src/pages/Signals.tsx`, line 207

### Changes Made
1. **Removed async/await blocker**
   - Changed `onClick={async () => {` to `onClick={() => {`
   - Changed `await handleLoadArticles()` to `handleLoadArticles()` (non-blocking)
   - Now articles fetch in background while UI expands immediately

2. **Enhanced hover UX**
   - Added hover background: `hover:bg-blue-50 dark:hover:bg-blue-900/20`
   - Added padding and rounded corners: `px-2 py-1 rounded`
   - Added smooth transition: `transition-colors`
   - Added explicit cursor: `cursor-pointer`

**Result:** Single-click expansion with background article loading + improved hover feedback

### Testing
- ✅ Frontend build passes: 2146 modules, 144KB gzipped
- ✅ TypeScript: 0 errors
- ✅ No breaking changes
- ✅ Hover state visually distinct

### Files Changed
- `context-owl-ui/src/pages/Signals.tsx` (4 insertions, 4 deletions)
