---
id: BUG-042
type: performance
priority: HIGH
severity: HIGH
status: ✅ COMPLETED
created: 2026-02-25
updated: 2026-02-25
effort: 15 minutes actual
completed: 2026-02-25 (FEATURE-048d/048e staleTime regression fixed)
---

# BUG-042: useInfiniteQuery Refetch Storm (FEATURE-048d/048e Regression)

## Problem Statement

FEATURE-048d (Signals infinite scroll) and FEATURE-048e (Narratives infinite scroll) replaced the original `useQuery` calls with new `useInfiniteQuery` calls, but hardcoded `staleTime: 0`. This overwrote the cold-cache performance branch's `staleTime: 25s/55s` fix. Combined with React Query's default `refetchOnWindowFocus: true`, every tab switch triggers refetches of ALL loaded infinite query pages, creating request storms that overwhelm Atlas M0 (intermittent signal failures, slow loads).

## Root Cause Analysis

### The Regression
- **FEATURE-048d/048e Changes:** Both pages replaced `useQuery` with `useInfiniteQuery`
- **Problem:** New `useInfiniteQuery` options explicitly set `staleTime: 0`
- **Effect:** Combined with `refetchOnWindowFocus: true` (React Query default), tab focus → refetch all loaded pages
- **Pattern:** User loads 3 pages of signals (45 items), switches tabs, returns → fetches all 45 items again
- **Scale:** On Atlas M0 with many users, this creates cascading refetch storms that trigger intermittent errors
- **Why it matters:** The cold-cache branch (e867741) had already fixed this with `staleTime: 25s/55s`, but FEATURE-048d/048e overwrite was lost on merge

## Solution Implemented

### Fix: Restore Cache Configuration + Disable Window Focus Refetch ✅
**Changed in:**
- `context-owl-ui/src/pages/Signals.tsx` (line 90-91)
- `context-owl-ui/src/pages/Narratives.tsx` (line 80-81)

**Before:**
```typescript
useInfiniteQuery({
  // ... config
  staleTime: 0, // REGRESSION: Always consider data stale
  // Missing: refetchOnWindowFocus not configured (defaults to true)
})
```

**After:**
```typescript
// Signals.tsx
useInfiniteQuery({
  // ... config
  staleTime: 25000, // Restored: Consider fresh for 25 seconds (5s buffer before 30s refetchInterval)
  refetchOnWindowFocus: false, // Prevent refetch storms on tab focus
})

// Narratives.tsx
useInfiniteQuery({
  // ... config
  staleTime: 55000, // Restored: Consider fresh for 55 seconds (5s buffer before 60s refetchInterval)
  refetchOnWindowFocus: false, // Prevent refetch storms on tab focus
})
```

**Why this fixes it:**
1. **staleTime restoration:** React Query now respects the backend cache TTL (25s/55s buffers)
2. **refetchOnWindowFocus: false:** Tab switches no longer trigger automatic refetches
3. **Result:** Repeated visits within cache window use cached data; tab focus doesn't invalidate
4. **Intentional resets:** `refetchInterval` (30s/60s) still works for live updates

## Impact Analysis

### Expected Improvements

| Scenario | Before (Regression) | After (Fixed) | Improvement |
|----------|------------|---------|-------------|
| **Tab focus** | Refetch all loaded pages | Cache hit | ~90% reduction in API calls |
| **Within 25-55s window** | Always recomputes | Cache serves request | 100% reduction in backend work |
| **Atlas M0 load** | Refetch storms cause errors | Distributed load (1 per 25-60s) | Prevents intermittent failures |
| **User experience** | Flickering, slow interactions | Smooth, instant cached display | Dramatic UX improvement |

### Behavioral Changes

- **User-Facing:** Tab switches no longer cause page flicker or slow reloads
- **Breaking Changes:** None. Query behavior unchanged, just more intelligent caching
- **Test Impact:** Existing tests unchanged (React Query caching behavior is transparent to tests)

## Verification

### Build Status
```bash
cd context-owl-ui && npm run build
# ✅ 2146 modules transformed, 143-144KB gzipped
# ✅ TypeScript: 0 errors
# ✅ No breaking changes
```

### Testing
- No test changes needed (cache behavior is transparent to existing tests)
- Manual verification: Tab switch → no page refetch, page stays smooth
- Load testing: Multiple tab switches should not trigger request storms

## Files Modified

1. **context-owl-ui/src/pages/Signals.tsx** — Lines 90-91: Add `staleTime: 25000` + `refetchOnWindowFocus: false`
2. **context-owl-ui/src/pages/Narratives.tsx** — Lines 80-81: Add `staleTime: 55000` + `refetchOnWindowFocus: false`

## Branch & Commit

- **Branch:** `fix/signals-narratives-cold-cache-performance`
- **Commit:** 1dbc98b (BUG-042 fix)
- **Status:** ✅ COMPLETE AND COMMITTED

## Related Issues

- **FEATURE-048d/048e:** Frontend infinite scroll (caused the regression by setting staleTime: 0)
- **Cold-cache branch (e867741):** Had correct staleTime config that was overwritten on merge
- **TASK-014:** Pre-launch security hardening (next priority after this fix)

## Next Steps

1. ✅ Commit pushed to `fix/signals-narratives-cold-cache-performance`
2. Create PR against `main`
3. Deploy to production and monitor for reduced refetch storms
4. Verify tab switches no longer cause intermittent signal failures

## Implementation Notes

This fix corrects a merge regression where FEATURE-048d/048e's new `useInfiniteQuery` calls overwrote the cold-cache performance branch's cache configuration. The solution is minimal (2 lines per file) because:

1. The cold-cache branch already identified the correct `staleTime` values (25s/55s)
2. Only needed to re-apply those values to the new `useInfiniteQuery` options
3. Added `refetchOnWindowFocus: false` to prevent React Query's default behavior on window focus

This is a pure React Query configuration fix — no backend changes needed.
