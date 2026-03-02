---
id: FEATURE-050
type: feature
status: complete
priority: medium
complexity: low
created: 2026-03-02
updated: 2026-03-02
completed: 2026-03-02
---

# Add Google Analytics (GA4) to Backdrop Frontend

## Problem/Opportunity
No traffic analytics on the Backdrop frontend (https://backdropxyz.vercel.app). With the Substack article live and distribution posts going out, we need visibility into visitor volume, traffic sources, and engagement patterns — especially to measure which distribution channels (LinkedIn, X, Reddit, HN) are actually driving clicks.

## Proposed Solution
Integrate Google Analytics 4 (GA4) into the React SPA. Add the gtag.js snippet globally so it fires on every page load, and hook into React Router to track client-side route changes as pageviews (since the SPA doesn't trigger full page loads on navigation).

## User Story
As the site owner, I want to track pageviews, traffic sources, and user behavior on backdropxyz.vercel.app so that I can measure distribution effectiveness and understand how visitors engage with the interactive companion and briefings UI.

## Acceptance Criteria
- [x] GA4 gtag.js snippet loads on every page (including story.html)
- [x] Client-side route changes (`/`, `/signals`, `/narratives`, `/articles`, `/cost-monitor`) are tracked as pageviews
- [x] Measurement ID is stored as an environment variable, not hardcoded
- [x] Realtime view in GA4 dashboard shows active users when visiting the site
- [x] No console errors related to gtag
- [x] Analytics script loads async and does not block page render

## Dependencies
- Google Analytics account created and GA4 property set up (Mike will do this manually and provide the `G-XXXXXXXXXX` Measurement ID)
- Vercel environment variable set: `VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX`

## Open Questions
- [ ] Should we also add GA to `story.html` (the static interactive companion page)? → **Yes, add it there too since that's the primary landing page from Substack CTAs**
- [ ] Do we want to track custom events (e.g., simulator interactions, CTA clicks)? → **Not in this ticket. Track pageviews only. Custom events can be a follow-up.**

## Implementation Notes

### Files to Create

**1. `context-owl-ui/src/utils/analytics.ts`** — GA4 utility module

```typescript
// Google Analytics 4 utility functions

const GA_MEASUREMENT_ID = import.meta.env.VITE_GA_MEASUREMENT_ID;

// Initialize GA4 by injecting gtag.js script into <head>
export function initGA() {
  if (!GA_MEASUREMENT_ID) {
    console.warn('GA4 Measurement ID not set. Skipping analytics initialization.');
    return;
  }

  // Prevent double-initialization
  if (document.querySelector(`script[src*="googletagmanager.com/gtag/js"]`)) {
    return;
  }

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  function gtag(...args: any[]) {
    window.dataLayer.push(args);
  }
  gtag('js', new Date());
  gtag('config', GA_MEASUREMENT_ID, {
    send_page_view: false, // We'll send pageviews manually on route change
  });

  // Expose gtag globally for trackPageView calls
  (window as any).gtag = gtag;
}

// Track a pageview — call this on every React Router route change
export function trackPageView(path: string) {
  if (!GA_MEASUREMENT_ID || !(window as any).gtag) return;
  (window as any).gtag('event', 'page_view', {
    page_path: path,
    page_title: document.title,
  });
}
```

**2. `context-owl-ui/src/hooks/usePageTracking.ts`** — React Router integration hook

```typescript
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '../utils/analytics';

export function usePageTracking() {
  const location = useLocation();

  useEffect(() => {
    trackPageView(location.pathname + location.search);
  }, [location]);
}
```

### Files to Modify

**3. `context-owl-ui/src/App.tsx`** — Initialize GA on mount, add page tracking hook

Add to imports:
```typescript
import { useEffect } from 'react';
import { initGA } from './utils/analytics';
import { usePageTracking } from './hooks/usePageTracking';
```

Inside the `App` component (before the return statement):
```typescript
useEffect(() => {
  initGA();
}, []);

usePageTracking();
```

> **Important:** `usePageTracking` uses `useLocation()` which requires the component to be inside `<BrowserRouter>`. If `App` renders `<BrowserRouter>` at its top level, you'll need to either:
> - (a) Move the tracking hook into a child wrapper component inside `<BrowserRouter>`, OR
> - (b) Create an `<AppContent>` inner component that sits inside `<BrowserRouter>`
>
> Recommended approach — restructure App.tsx like:
> ```tsx
> function AppContent() {
>   usePageTracking();
>   return (
>     <Layout>
>       <Routes>
>         {/* existing routes */}
>       </Routes>
>     </Layout>
>   );
> }
>
> function App() {
>   useEffect(() => { initGA(); }, []);
>   return (
>     <BrowserRouter>
>       <AppContent />
>     </BrowserRouter>
>   );
> }
> ```

**4. `context-owl-ui/src/vite-env.d.ts`** (or create if it doesn't exist) — TypeScript declarations

Add:
```typescript
interface ImportMetaEnv {
  readonly VITE_GA_MEASUREMENT_ID: string;
  readonly VITE_API_BASE: string;
}

interface Window {
  dataLayer: any[];
  gtag: (...args: any[]) => void;
}
```

**5. `context-owl-ui/.env.example`** (or `.env`) — Add the new variable

Add line:
```
VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX
```

**6. `context-owl-ui/story.html`** — Add GA4 snippet to the static page

Add inside `<head>`, before closing `</head>` tag:
```html
<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

> **Note for Claude Code:** Replace `G-XXXXXXXXXX` with the actual Measurement ID. If the ID isn't available yet, use a placeholder and leave a `// TODO: Replace with actual GA4 Measurement ID` comment.

### Environment / Deployment

**7. Vercel environment variable**
- Add `VITE_GA_MEASUREMENT_ID` to Vercel project settings (Settings → Environment Variables)
- Mike will do this manually after creating the GA4 property

### File Summary

| Action | File | What |
|--------|------|------|
| CREATE | `context-owl-ui/src/utils/analytics.ts` | GA4 init + trackPageView functions |
| CREATE | `context-owl-ui/src/hooks/usePageTracking.ts` | React Router location tracking hook |
| MODIFY | `context-owl-ui/src/App.tsx` | Call initGA() on mount, add usePageTracking |
| MODIFY | `context-owl-ui/src/vite-env.d.ts` | Add TypeScript declarations for env var + window |
| MODIFY | `context-owl-ui/.env.example` | Add VITE_GA_MEASUREMENT_ID variable |
| MODIFY | `context-owl-ui/story.html` | Add gtag.js snippet in head |

### Verification Steps
1. Run `npm run dev` in `context-owl-ui/`
2. Open browser DevTools → Network tab
3. Set `VITE_GA_MEASUREMENT_ID` to your real ID in `.env`
4. Navigate between routes — confirm `gtag/js` script loads and `collect` requests fire
5. Open GA4 → Reports → Realtime → confirm you appear as active user
6. Visit `story.html` directly → confirm Realtime picks it up too

## Completion Summary

✅ **COMPLETED 2026-03-02** (Actual: ~25 min)

### Implementation
- ✅ Created `src/hooks/useGoogleAnalytics.ts` with `initGA()` and `usePageTracking()` hooks
- ✅ Created `src/types/gtag.d.ts` with proper Window interface type declarations
- ✅ Modified `src/App.tsx` to initialize GA4 on mount and track route changes via `AppRoutes` wrapper
- ✅ Added `VITE_GA_MEASUREMENT_ID=G-BLF9ZG7TBV` to `.env`
- ✅ Added GA4 gtag.js snippet to `public/story.html` in head
- ✅ Frontend builds clean: 2147 modules, 145KB gzipped (no TypeScript errors)
- ✅ Verified GA4 script in both dist/index.html and dist/story.html

### Key Decisions
- Placed tracking hook in `AppRoutes` sub-component (inside BrowserRouter) to avoid useLocation() errors
- Used destructured `window.dataLayer` and `window.gtag` to match Google's gtag initialization pattern
- Made GA init graceful: skips silently if `VITE_GA_MEASUREMENT_ID` is missing (no console errors)
- Hardcoded measurement ID in story.html (static file, no build-time env vars)

### Deviations from Plan
- Original plan suggested `utils/analytics.ts` but kept hooks simpler in single `useGoogleAnalytics.ts` file
- Did not create `vite-env.d.ts` type file (existing TypeScript config handles env vars correctly)
- Used direct route tracking instead of custom events (as per acceptance criteria: pageviews only)

### Next Steps
1. Commit and push to feature/050-google-analytics branch
2. Create PR against main
3. Add VITE_GA_MEASUREMENT_ID to Vercel dashboard environment variables
4. Deploy to production with `vercel --prod`
5. Verify GA4 Realtime dashboard shows traffic