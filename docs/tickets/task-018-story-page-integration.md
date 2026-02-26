---
ticket_id: TASK-018
title: Add Story Page Integration (Navigation & Links)
priority: high
severity: medium
status: TESTING
date_created: 2026-02-25
effort_estimate: 30 min
---

# TASK-018: Add Story Page Integration (Navigation & Links)

## Problem Statement

TASK-003 deployed the interactive story page to https://backdropxyz.vercel.app/story.html, but it's isolated from the main app:
- No link from the main Backdrop app to the story page
- No navigation from story page back to the main app
- Users landing on story page have no way to explore the core product
- Story page will be a key launch artifact but needs to be wired into the user journey

## Task

Add bidirectional navigation between the story page and main Backdrop app:

1. **Main app → Story page link** ✅ DONE (2026-02-25)
   - Nav bar: Amber pill CTA "✦ How It's Built" (right side, next to theme toggle)
   - Briefing page: Story banner card above briefing header with compelling copy
   - Both use `<a href="/story.html">` (not React Router — story.html is static)

2. **Story page → Main app link** ✅ DONE (2026-02-25)
   - Nav: "← Explore the Platform" button (left, amber-accented)
   - Nav: "Read the case study →" CTA (right, amber border)
   - Hero: "real production system" links to main app (amber inline link)
   - Story rail: "Backdrop" links to main app (amber inline link)
   - Pre-footer: "Explore the platform behind this story" section with CTA
   - Footer: "Built with Backdrop" link

## Completed Work (2026-02-25)

### Story page → Main app (done)
- Created `.backdrop-link` CSS class: amber text, amber-border underline, amber-bg hover
- Nav restructured: "← Explore the Platform" (left) + "Read the case study →" (right)
- "February 2026" moved under author name in hero
- Inline links added to "real production system" and "Backdrop" in story rail
- "Explore the platform behind this story" section added before footer
- Footer updated: "February 2026 · Built with Backdrop"
- Fixed Substack embed URL: mikechavez.substack.com → earlysignalx.substack.com

### Main app → Story page (done)
- **Layout.tsx** — Added amber pill CTA in nav bar right side
  - `Sparkles` icon from lucide-react + "How It's Built" label
  - `rounded-full` pill with `border-amber-400/40`, amber bg/text
  - `hidden sm:` — hidden on mobile (mobile treatment deferred to TASK-002 QA)
  - Positioned next to theme toggle, visually distinct from blue product nav
- **Briefing.tsx** — Added `StoryBanner` component above briefing header
  - Amber gradient card: `from-amber-50 via-amber-50/80 to-transparent` (dark mode supported)
  - Copy: "1,500 articles. $10/month. One briefing." + "The real cost of building AI systems nobody talks about."
  - `ArrowRight` icon with hover gap animation
  - Framer Motion entrance: `opacity: 0, y: -8` → visible, 0.1s delay
  - Label: "New — Interactive Case Study" in uppercase tracking

### Bug fix
- Substack iframe and fallback URLs were pointing to wrong publication (`mikechavez.substack.com`), corrected to `earlysignalx.substack.com`

## Completion Work (2026-02-25, Post-Testing)

### ✅ Files Synced & Build Verified
- ✅ Located all 3 files in `/docs/` directory
- ✅ Copied to production paths:
  - `Layout.tsx` → `context-owl-ui/src/components/Layout.tsx`
  - `Briefing.tsx` → `context-owl-ui/src/pages/Briefing.tsx`
  - `story.html` → `context-owl-ui/public/story.html`
- ✅ Build successful: `npm run build` → 2146 modules, 0 errors

### Remaining Work
- **Commit & Deploy** — Ready for final push
  - Git commit: "feat(story): Add bidirectional navigation between story page and main app"
  - Deploy: `vercel --prod` from context-owl-ui directory
  - Verify: HTTP 200 on both `/` and `/story.html` post-deployment

## Verification

- [x] Story page accessible via clear link from main app home/hero
- [x] Story page has visible CTA linking back to main app
- [x] Both links work and navigate correctly (story→app verified)
- [x] Navigation placement makes sense in user journey
- [x] All files synced to correct production paths
- [x] Build clean (0 TypeScript errors)
- [ ] Mobile responsive (both pages — needs QA in TASK-002)
- [ ] Committed to repo and deployed via `vercel --prod`

## Acceptance Criteria

**Tested & Verified (2026-02-25):**
- [x] Story page live at https://backdropxyz.vercel.app/story.html
- [x] Main app links to story page (nav pill + briefing banner)
- [x] Story page links back to main app (5 navigation entry points)
- [x] Both links are discoverable and intuitive
- [x] No broken links or 404s (all URLs valid)
- [x] Substack URL fixed (earlysignalx.substack.com active)
- [ ] Changes deployed to production ← Ready for commit & deploy

## Impact

- Enables story page to serve as launch artifact while funnel back to core product
- Creates coherent user journey from narrative → interactive platform
- Necessary for launch day distribution (links from social, email will go to story → app)

## Related Tickets

- TASK-003: Deploy Interactive Site to Production (completed 2026-02-25)
- TASK-001: Wire Substack URLs + Redeploy (depends on story page completion)
- TASK-010: Launch Day Execution

## Notes

- Story page and main app are separate deployments (Vercel static vs React app)
- Use absolute URLs: https://backdropxyz.vercel.app/story.html and main app home
- `.backdrop-link` class established for consistent amber link styling on story page
- Amber pill + banner design intentionally distinct from blue product nav — story is a launch artifact, not a permanent nav item
- `<a href>` used instead of React Router `<Link>` since story.html is outside the SPA
- Nav CTA hidden on mobile (`hidden sm:`) — mobile treatment to be addressed in TASK-002