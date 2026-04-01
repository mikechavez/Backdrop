---
ticket_id: TASK-030
title: Rename GitHub Repo & Update Public-Facing Metadata
priority: P1
severity: LOW
status: OPEN
date_created: 2026-03-31
branch: n/a
effort_estimate: 15 min
---

# TASK-030: Rename GitHub Repo & Update Public-Facing Metadata

## Problem Statement

The GitHub repo is still named `crypto-news-aggregator` (or similar legacy name), but the product has been Backdrop for months. Employers checking the GitHub profile from resume/LinkedIn links will see a mismatched repo name, which undermines the professional presentation of the project.

---

## Task

1. Rename the repo to `backdrop` in GitHub Settings > General
2. Update the repo description/about field to something like: "Autonomous narrative intelligence platform — ingests 100+ articles/day, clusters narratives, and generates structured briefings via multi-signal LLM self-refine loop"
3. Add a one-liner to the top of the existing README: `# Backdrop — Autonomous Narrative Intelligence Platform`
4. Verify the old URL redirects to the new one
5. Backlog item: full README rewrite deferred to Sprint 13 (pairs with RSS feed pivot)

All steps are manual (GitHub UI + direct file edit). No Claude Code needed.

---

## Verification

- [ ] `github.com/mikechavez/backdrop` loads correctly
- [ ] Old repo URL redirects to new name
- [ ] Repo description visible on GitHub profile
- [ ] README top line says "Backdrop"

---

## Acceptance Criteria

- [ ] Repo renamed in GitHub Settings
- [ ] Repo description updated
- [ ] README has Backdrop one-liner at top
- [ ] Old URL confirmed redirecting

---

## Impact

Resume and LinkedIn both link to this repo. Employer-facing presentation is the entire point.

---

## Related Tickets

- Sprint 13 backlog: Full README rewrite (to be created during Sprint 13 planning)