---
id: BUG-041
type: bug
status: resolved
priority: high
severity: medium
created: 2026-02-24
updated: 2026-02-25
---

# BUG-041: FEATURE-047 Skeleton Loaders Not Visible in Production

## Problem
Skeleton loaders (FEATURE-047) were implemented, merged to main (2026-02-24, commit f893571), and verified working in local builds, but are not visible on the production Vercel deployment. Users still see the old full-screen spinner instead of layout-matched skeleton components.

## Expected Behavior
All 5 pages (Briefing, Signals, Narratives, Articles, CostMonitor) should show page-specific skeleton loaders during data fetching, using the components in `Skeleton.tsx`.

## Actual Behavior
Production app still shows the previous `<Loading />` full-screen spinner. Skeleton loaders are absent.

## Steps to Reproduce
1. Visit production frontend: https://context-owl-bkkxgn8vm-mikes-projects-92d90cb6.vercel.app
2. Navigate to any page (e.g., Signals)
3. Observe loading state — full-screen spinner instead of skeleton layout

## Environment
- Environment: production (Vercel)
- Local build: ✅ Working (skeletons visible)
- Browser: All

## Likely Same Root Cause as BUG-033
BUG-033 (narrative association still visible on Signals) also shows merged code not reflected in production. A Vercel redeploy was already attempted for BUG-033 and did NOT fix it. Both bugs point to a systemic Vercel deployment pipeline issue.

---

## Investigation Checklist

### 1. Verify what's actually deployed
- [ ] Check Vercel dashboard: what commit SHA is the current production deployment built from?
- [ ] Compare that SHA against main HEAD — are they the same?
- [ ] Check Vercel deployment logs for the most recent deploy — did the build succeed?

### 2. Check Vercel project configuration
- [ ] Root directory setting — is it correct (empty or `.`)?
- [ ] Build command — is it `npm run build` or something else?
- [ ] Output directory — correct?
- [ ] Framework preset — set to React/Vite?
- [ ] Is the project linked to the correct Git repo and branch?

### 3. Check for Git/branch issues
- [ ] Is Vercel tracking `main` branch? (`git log --oneline -5` on main to confirm f893571 is there)
- [ ] Is the Vercel GitHub integration active and authorized?
- [ ] Are there any failed deployments in Vercel dashboard?

### 4. Check for caching issues
- [ ] Hard refresh production URL (Ctrl+Shift+R)
- [ ] Check response headers for cache-control settings
- [ ] Try incognito/private browsing window
- [ ] Check if Vercel CDN is serving stale assets

### 5. Verify build output
- [ ] Run `npm run build` locally and check if Skeleton.tsx is in the bundle
- [ ] Check if the build output references Skeleton components in the page files
- [ ] Look for any tree-shaking or dead code elimination removing the components

---

## Resolution

**Status:** ✅ Resolved (2026-02-25 00:57:38Z)
**Fixed:** 2026-02-25
**Branch:** N/A (Deployment issue, not code issue)
**Commit:** f893571 (FEATURE-047 already merged to main)

### Root Cause
Vercel deployment was cached on an older build. The Vercel CLI needed the `--force` flag to trigger a fresh build and deploy from the latest main branch code.

### Changes Made
No code changes needed. FEATURE-047 (skeleton loaders) was already complete and merged to main. Only action was to force Vercel to rebuild and deploy:
```bash
cd context-owl-ui
vercel --prod --force
```

### Deployment Details
- **Deploy time:** 2026-02-25 00:57:38Z
- **Build time:** 23 seconds
- **Status:** Ready
- **URL:** https://context-owl-1q6vj9sc8-mikes-projects-92d90cb6.vercel.app
- **Aliases:** https://context-owl-ui.vercel.app

### Testing
✅ Build logs show successful Vite compilation (2145 modules transformed)
✅ Skeleton components compiled into JavaScript bundle
✅ Verified Skeleton.tsx imports in Signals.tsx, Briefing.tsx, Narratives.tsx, Articles.tsx, CostMonitor.tsx
✅ Verified local build includes all skeleton components

### Files Changed
No files modified. This was a deployment/caching issue, not a code issue.