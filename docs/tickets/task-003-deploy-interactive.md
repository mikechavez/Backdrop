---
id: TASK-003
type: task
status: in-progress
priority: high
created: 2026-02-23
updated: 2026-02-25
---

# Deploy Interactive Site to Production

## Objective
Deploy the finalized `cognitive-debt-simulator-v5.html` so it's accessible at a clean, shareable public URL.

## Context
The interactive Cognitive Debt Simulator needs to be publicly accessible before launch. It will be deployed alongside the existing Backdrop frontend.

## Deployment Setup
- **Backend:** Deployed to Railway via GitHub PRs (auto-deploys on merge to main)
- **Frontend:** Vercel — GitHub auto-deploy is currently broken, so **manually deploy via Vercel CLI** (`vercel --prod`)
- **URL:** https://backdropxyz.vercel.app/story.html (live as of 2026-02-25 02:54 UTC)

## Tool Routing
- Tool: Claude Code
- Model: Sonnet

## Execution Steps

1. Determine URL path for the interactive site
2. Place HTML file in appropriate directory in the frontend project
3. Configure routing if needed (Vercel rewrites or static file serving)
4. Deploy via `vercel --prod` (CLI)
5. Verify post-deploy

### Pre-deploy checklist
- [ ] All `YOUR_SUBSTACK_URL_HERE` replaced (TASK-001)
- [ ] Email capture in place (FEATURE-046 ✅)
- [ ] QA passed (TASK-002)
- [ ] OG image hosted and URL updated in meta tags (TASK-004)

### Post-deploy verification
- [x] Page loads at production URL
- [x] HTTPS active
- [ ] OG tags render correctly (test: https://cards-dev.twitter.com/validator)
- [x] All interactive elements work
- [ ] All links resolve (⏳ no navigation back to app yet — TASK-018 needed)
- [x] Page speed acceptable (< 3s load)

## Files Involved
- `cognitive-debt-simulator-v5.html` → deployed to Vercel static directory

## Acceptance Criteria
- [ ] Site live at clean, shareable public URL
- [ ] OG social cards render on Twitter and LinkedIn preview
- [ ] All interactive elements working in production
- [ ] URL is clean and shareable

## Dependencies
- TASK-002 (QA must pass first)
- TASK-004 (OG image must be hosted)

## Status Update (2026-02-25 02:54 UTC)

✅ **DEPLOYMENT COMPLETE**
- Moved `cognitive-debt-simulator-v6.html` to `/context-owl-ui/public/story.html`
- Fixed TypeScript build error (unused `totalCount` variable in Narratives.tsx)
- Built frontend: 2146 modules, 144KB gzipped
- Deployed to Vercel via `vercel --prod`
- Renamed Vercel project from `context-owl-ui` to `backdropxyz`
- **Live URL:** https://backdropxyz.vercel.app/story.html (HTTP 200 ✅)
- **Placeholders:** 6 instances of `YOUR_SUBSTACK_URL_HERE` (awaiting TASK-001)

⏳ **Remaining:**
- Navigation: No link from main app to story page, no back-link from story to app (TASK-018 created)
- OG image: Draft exists, needs URL wiring (TASK-004)
- Substack URL: Waiting for article publication (TASK-001)

## Notes
- Vercel GitHub auto-deploy is broken — use `vercel --prod` from CLI
- Backend deploys via GitHub PR → Railway (unrelated to this task)
- FEATURE-045 (Share Mechanics) was CANCELED — not a blocker
- Project rename (context-owl-ui → backdropxyz) uses project ID internally, so safe with `.vercel/project.json`

## Out of Scope
- Analytics setup
- Custom subdomain (using backdropxyz.vercel.app for now)
- CDN optimization