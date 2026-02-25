---
id: BUG-033
type: bug
status: backlog
priority: medium
severity: low
created: 2026-02-23
updated: 2026-02-23
---

# Narrative Association Still Visible on Signals Page

## Problem
FEATURE-036 (Sprint 7, commit deployed ~2026-02-06) was supposed to remove the "Part of: [Narrative]" buttons from signal cards on the Signals page, keeping only the "Emerging" badge for new signals. However, some signals still display narrative association UI elements.

## Expected Behavior
Signal cards should show **no** narrative association section. The only narrative-related UI should be the "🆕 Emerging" badge for signals where `is_emerging: true`. All "Part of:" buttons linking to narratives should be gone.

**Expected rendering (per FEATURE-036 spec):**
```
Signal Card
├─ Entity name & velocity badge
├─ Type: Cryptocurrency
├─ Sources: 3 sources
├─ Last Updated: 2 hours ago
├─ ─────────────────────────
├─ 🆕 Emerging (only if is_emerging)
└─ ▶ Recent mentions (3)
```

## Actual Behavior
Some signals still show they are "part of a narrative" — either through "Part of:" text, narrative theme buttons, or some other narrative-linked UI element.

## Steps to Reproduce
1. Navigate to `/signals`
2. Scroll through signal cards
3. Observe signals that still display narrative association information

## Investigation Required

### Check: Was FEATURE-036 code fully deployed?
```bash
# In the frontend codebase, search for any remaining narrative references in Signals.tsx
rg -n "Part of" context-owl-ui/src/pages/Signals.tsx
rg -n "narrative" context-owl-ui/src/pages/Signals.tsx
rg -n "formatTheme\|getThemeColor" context-owl-ui/src/pages/Signals.tsx
```

### FEATURE-036 implementation reference
**File:** `context-owl-ui/src/pages/Signals.tsx` (lines 197-219 were the target)

**What should have been removed:**
```typescript
// THIS ENTIRE BRANCH should be gone:
) : signal.narratives && signal.narratives.length > 0 ? (
    <div>
      <span className="...">Part of:</span>
      <div className="flex flex-wrap gap-1">
        {signal.narratives.map((narrative) => (
          <button ... >
            {formatTheme(narrative.theme)}
          </button>
        ))}
      </div>
    </div>
) : null}
```

**What should remain:**
```typescript
{signal.is_emerging && (
  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-dark-border">
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-yellow-700 ...">
        🆕 Emerging
      </span>
      <span className="text-xs text-gray-500 ...">Not yet part of any narrative</span>
    </div>
  </div>
)}
```

### Likely causes
1. **Incomplete removal** — the `signal.narratives` conditional branch wasn't fully removed
2. **Deployment issue** — FEATURE-036 code wasn't included in the production build
3. **Different component** — narrative info is being rendered from a different component or route

## Environment
- Environment: production
- Browser/Client: Web
- User impact: low — cosmetic inconsistency, was explicitly requested to be removed

---

## Resolution

**Status:** Investigation Complete — Awaiting Vercel Dashboard Fix
**Root Cause Identified:** 2026-02-23
**Branch:** N/A (Deployment issue, not code issue)
**Commit:** N/A

### Root Cause
✅ **Confirmed:** FEATURE-036 code removal was correct and complete. Signals.tsx contains no narrative association code (verified 2026-02-23).

**Issue:** Stale production build. Vercel project has incorrect root directory configured in dashboard settings, preventing redeploy via CLI.

**Evidence:**
```bash
# Verified clean (2026-02-23)
rg -n "Part of\|formatTheme\|getThemeColor\|signal\.narratives" context-owl-ui/src/pages/Signals.tsx
# Result: 0 hits ✅

# Build successful
npm run build
# dist/index.html built successfully ✅

# Vercel auth successful
vercel login
# Logged in successfully ✅

# Deployment blocked by dashboard misconfiguration
vercel --prod --yes
# Error: The provided path "~/dev-projects/crypto-news-aggregator/context-owl-ui/context-owl-ui" does not exist
# Cause: Root Directory setting in Vercel dashboard is wrong
```

### Changes Made
**No code changes needed.** FEATURE-036 already removed all narrative association UI from signal cards.

### Deployment Instructions
To redeploy the frontend with the correct code:

1. **Open Vercel Dashboard:**
   - Go to: https://vercel.com/mikes-projects-92d90cb6/context-owl-ui/settings

2. **Fix Root Directory Setting:**
   - Find the "Root Directory" field in project settings
   - Clear the current value (should be empty or just `.`)
   - Click Save

3. **Redeploy:**
   ```bash
   cd context-owl-ui
   vercel --prod --yes
   ```

4. **Verify Production:**
   - Check the production URL (output from `vercel --prod`)
   - Navigate to `/signals`
   - Confirm: No "Part of:" text on signal cards
   - Confirm: Only "🆕 Emerging" badge for emerging signals
   - Confirm: "▶ Recent mentions" section still present

### Testing
- [ ] No signal card displays "Part of:" text or narrative theme buttons
- [x] `is_emerging` badge shows correctly for emerging signals (FEATURE-036 confirmed)
- [x] `rg "Part of" Signals.tsx` returns 0 hits ✅ (verified 2026-02-23)
- [ ] Production build verified on `/signals` after redeploy
- [ ] Vercel deployment completes successfully (once dashboard is fixed)

### Files Changed
**None** — Investigation confirmed FEATURE-036 implementation was correct.
- `context-owl-ui/src/pages/Signals.tsx` — Already correct (verified clean)