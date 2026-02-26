---
ticket_id: TASK-018
title: Add Story Page Integration (Navigation & Links)
priority: high
severity: medium
status: OPEN
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

1. **Main app → Story page link**
   - Add prominent CTA or nav link from main app to story page
   - Location: Hero section, nav bar, or dedicated "Launch" section
   - Text: Something like "Read the Story" or "See How We Got Here"

2. **Story page → Main app link**
   - Add back-link or CTA at end of story page pointing to main app
   - Should encourage exploring the interactive dashboard
   - Text: Something like "Explore the Platform" or "Back to Backdrop"

## Verification

- [ ] Story page accessible via clear link from main app home/hero
- [ ] Story page has visible CTA linking back to main app
- [ ] Both links work and navigate correctly
- [ ] Navigation placement makes sense in user journey
- [ ] Mobile responsive (both pages)

## Acceptance Criteria

- [x] Story page live at https://backdropxyz.vercel.app/story.html
- [ ] Main app links to story page
- [ ] Story page links back to main app
- [ ] Both links are discoverable and intuitive
- [ ] No broken links or 404s

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
- Consider adding visual consistency (colors, branding) to link styling
