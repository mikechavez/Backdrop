---
id: BUG-053
type: bug
status: completed
priority: low
severity: low
created: 2026-02-25
updated: 2026-02-25
---

# UI Text Cleanup - Narratives & Signals Pages

## Problem
UI pages contained inconsistent and misleading text:
1. Narratives page showed "Page 1 of 1" in articles dropdown (pagination text for non-paginated list)
2. Narratives page showed "(30 of 200)" in subtitle with incorrect description
3. Signals page description didn't clearly describe the content ("Top entities showing unusual activity" was vague)

## Expected Behavior
- Remove pagination indicators from articles list (uses "Load More" button instead)
- Update subtitle text to accurately describe the content
- Clear, consistent messaging across pages

## Actual Behavior
- "Page 1 of 1" displayed in articles dropdown row
- "(30 of 200)" displayed in narratives page subtitle
- Signals page description was ambiguous

## Steps to Reproduce
1. Navigate to Narratives page
2. Expand article dropdown on any narrative
3. Observe "Page 1 of 1" text in header row
4. Observe "(30 of 200)" in page subtitle
5. Navigate to Signals page
6. Read the subtitle description

## Environment
- Environment: production
- Browser/Client: All browsers
- User impact: low (cosmetic only)

## Resolution

**Status:** Completed
**Fixed:** 2026-02-25
**Branch:** fix/task-016-observability-clamps
**Commit:** To be created

### Root Cause
- Pagination UI code was carried over from backend pagination implementation
- Articles use "Load More" pattern, not traditional pagination
- Old subtitle text was copied from a different context

### Changes Made
1. **Narratives.tsx** (lines 387-397):
   - Removed "Page X of Y" pagination indicator
   - Kept only "Showing X of Y Articles" badge for user feedback
   - Removed unused `currentPage` and `totalPages` variables (lines 169-170)

2. **Narratives.tsx** (line 123-124):
   - Changed "Clustered stories and trending topics in the crypto space"
   - To: "Top stories and trending topics in the crypto space"
   - Removed "(30 of 200)" count display from subtitle

3. **Signals.tsx** (line 142):
   - Changed "Top entities showing unusual activity in the last 24 hours"
   - To: "Most talked-about keywords in the last 24 hours"
   - Clearer, more user-friendly description

### Testing
- Frontend build: `npm run build` (verified 2146 modules, 144KB gzipped)
- Manual verification on both Narratives and Signals pages
- No regression in article loading or display

### Files Changed
- `context-owl-ui/src/pages/Narratives.tsx`
- `context-owl-ui/src/pages/Signals.tsx`
