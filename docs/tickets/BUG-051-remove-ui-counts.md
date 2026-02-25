# BUG-051: Remove Internal Counts from Signals UI (ADR-012 Phase 4)

**Priority:** Medium
**Status:** ✅ COMPLETE - 2026-02-25

## Goal

Remove internal metric displays from the Signals UI to improve user experience and reduce visual clutter. As part of ADR-012 Phase 4, clean up the UI by removing count badges that display internal system metrics.

## Implementation Complete

**Branch:** `fix/bug-051-remove-ui-counts`
**Commit:** `05fb2d3`
**Files Modified:**
- `context-owl-ui/src/pages/Signals.tsx`

## What Was Done

✅ Removed header count display:
- Removed "(X of Y)" pagination display from the Signals page header
- Removed unused `totalCount` variable
- Simplified header description to: "Top entities showing unusual activity in the last 24 hours"

✅ Removed source count display:
- Removed "X sources" metric from individual signal cards
- Cleaned up the sources row from the card content display

## Code Changes

**Header section (lines 141-148 → 141-143):**
- Before: `Top entities showing unusual activity in the last 24 hours ({signals.length} of {totalCount})`
- After: `Top entities showing unusual activity in the last 24 hours`

**Signal card section (removed ~6 lines):**
- Removed entire "Sources: X sources" display row from card content

**Variable cleanup:**
- Removed `const totalCount = data?.pages[0]?.total_count ?? 0;`

## Frontend Build Verification

✅ Build successful:
- 2146 modules transformed
- 144KB gzipped (no size increase)
- TypeScript: 0 errors
- No breaking changes to component functionality

## Acceptance ✅

- ✅ Header count "(X of Y)" removed
- ✅ Source count "X sources" removed from cards
- ✅ Unused variables cleaned up
- ✅ Frontend builds without errors
- ✅ No impact on data fetching or caching logic
- ✅ Cleaner, less cluttered UI

## User Impact

**Before:**
- Signals page header showed: "Top entities... (15 of 142)"
- Each signal card displayed: "Sources: 23 sources"

**After:**
- Signals page header shows: "Top entities..."
- No source count badges on cards
- Cleaner visual presentation

## Architecture

**Integration points:**
- Frontend-only change - no API modifications
- Does not affect Redux/React Query cache
- Does not affect article fetching or rendering
- Compatible with existing infinite scroll implementation

## Testing

Verified:
- ✅ TypeScript compilation
- ✅ Frontend build successful
- ✅ Component renders without errors
- ✅ Infinite scroll still functional
- ✅ Article expansion still works
- ✅ Velocity indicators still display

## ADR-012 Progress

This completes Phase 4 of the signals stabilization:
- ✅ Phase 1: 7-day hard cutoff (BUG-045)
- ✅ Phase 2: Redis cache (FEATURE-049)
- ✅ Phase 3: Cache warming (TASK-015)
- ✅ Phase 4: UI cleanup (BUG-051)
- ⏳ Phase 5: Observability + clamps (TASK-016)

## Next Steps

1. Merge PR to main
2. Deploy to production (Railway)
3. Monitor user feedback on cleaner UI
4. Proceed to TASK-016 (final Phase 5)
