---
id: TASK-003
type: task
status: backlog
priority: high
created: 2026-02-23
updated: 2026-02-23
---

# Deploy Interactive Site to backdrop.markets

## Objective
Deploy the finalized `cognitive-debt-simulator-v5.html` to the same Vercel project as Backdrop so it's accessible at a clean URL on the same domain.

## Context
The interactive Cognitive Debt Simulator needs to be publicly accessible before launch. It will live on the same domain as Backdrop (backdrop.markets) for brand cohesion and simpler infrastructure.

## Tool Routing
- Tool: Claude Code
- Model: Sonnet

## Execution Steps

1. Determine URL path (e.g., `backdrop.markets/story` or `backdrop.markets/cognitive-debt`)
2. Place HTML file in appropriate directory in Vercel project
3. Configure routing if needed (Vercel rewrites or static file serving)
4. Deploy to production
5. Verify post-deploy

### Pre-deploy checklist
- [ ] All `YOUR_SUBSTACK_URL_HERE` replaced (TASK-001)
- [ ] Share buttons working (FEATURE-045)
- [ ] Email capture in place (FEATURE-046)
- [ ] QA passed (TASK-002)
- [ ] OG image hosted and URL updated in meta tags

### Post-deploy verification
- [ ] Page loads at production URL
- [ ] HTTPS active
- [ ] OG tags render correctly (test: https://cards-dev.twitter.com/validator)
- [ ] All interactive elements work
- [ ] All links resolve
- [ ] Page speed acceptable (< 3s load)

## Files Involved
- `cognitive-debt-simulator-v5.html` → deployed to Vercel static directory

## Acceptance Criteria
- [ ] Site live at public URL on backdrop.markets
- [ ] OG social cards render on Twitter and LinkedIn preview
- [ ] All interactive elements working in production
- [ ] URL is clean and shareable

## Dependencies
- TASK-002 (QA must pass first)
- TASK-004 (OG image must be hosted)

## Out of Scope
- Analytics setup
- Custom subdomain
- CDN optimization
