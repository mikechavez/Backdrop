---
ticket_id: TASK-013
title: Update Production URL References in Documentation
priority: LOW
severity: N/A
status: OPEN
date_created: 2026-02-23
branch: chore/task-013-update-production-urls
effort_estimate: 15 minutes
---

# TASK-013: Update Production URL References in Documentation

## Problem Statement

Documentation files reference `backdrop.markets` as the production URL, but the actual production endpoints are:

- **Backend API:** `https://context-owl-production.up.railway.app`
- **Frontend:** `https://context-owl-bkkxgn8vm-mikes-projects-92d90cb6.vercel.app`

`backdrop.markets` may be a planned custom domain but is not currently live. All docs with curl commands, verification steps, or hosting references need to use the correct URLs.

---

## Task

### 1. Find all references

```bash
# Search all docs and scripts for stale domain references
rg -rn "backdrop\.markets" docs/ scripts/ src/ context-owl-ui/
```

### 2. Replace with correct URLs

- API/backend references → `https://context-owl-production.up.railway.app`
- Frontend references → Vercel deployment URL
- If `backdrop.markets` is a planned custom domain, add a note clarifying it's not yet configured

### 3. Update Key Assets section in session-start.md

```markdown
# Before
- Hosting: Vercel — same domain as Backdrop (backdrop.markets)

# After
- Backend API: Railway — https://context-owl-production.up.railway.app
- Frontend: Vercel — https://context-owl-bkkxgn8vm-mikes-projects-92d90cb6.vercel.app
```

### 4. Document API access pattern

If there are authentication requirements, CORS restrictions, or specific headers needed to call the Railway API, document them in the relevant docs (likely `session-start.md` or a new `10-infrastructure.md` if one exists).

---

## Verification

```bash
# Confirm no stale references remain
rg -rn "backdrop\.markets" docs/ scripts/ src/ context-owl-ui/
# Should return 0 results (or only in historical/changelog context)

# Confirm API is reachable
curl -s https://context-owl-production.up.railway.app/api/v1/signals/trending | head -5
```

---

## Files Likely Affected

- `docs/session-start.md` — Key Assets section
- `docs/current-sprint.md` — Any verification steps
- Any ticket docs with curl commands
- `scripts/test_anthropic_api.sh` — If it references the domain
- `README.md` — If it exists and references hosting

---

## Related Tickets

- BUG-034, BUG-035: Already use correct Railway URL in verification steps