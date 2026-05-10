---
ticket_id: TASK-096
title: Add Sprint 019 Verification Queries
priority: medium
severity: medium
status: COMPLETE
date_created: 2026-05-10
date_completed: 2026-05-10
branch: task/sprint-019-verification-queries
effort_estimate: small
---

# TASK-096: Add Sprint 019 Verification Queries

## Problem Statement

Sprint 019 changes user-facing briefing validation, briefing narrative eligibility, narrative display modes, and deterministic fallback display behavior. The sprint needs repeatable verification queries and checks so implementation agents can confirm that fixes work without modifying production data or triggering expensive jobs.

---

## Context

TASK-095 confirmed:

- Invalid briefing output can publish today.
- 341 active narratives are missing `last_summary_generated_at`.
- The narrative refresh task exists, is batched, and respects budget.
- String `article_ids` are converted to ObjectId correctly in the refresh and briefing paths.
- Sprint 019 chooses fresh-start narrative trust rather than mass legacy repair.

This task creates a small runbook for verifying the Sprint 019 behavior safely.

---

## Task

Create a verification document with read-only Mongo queries and local verification commands.

1. Add queries to detect invalid published briefings.
2. Add queries to count trusted-summary eligible briefing narratives.
3. Add queries to count active recent narratives that should render as article clusters.
4. Add checks to confirm no mass refresh was triggered.
5. Add checks to confirm no public display fields expose internal language.
6. Add cost checks for `llm_traces` around briefing and narrative operations.

---

## Files to Create

```text
docs/sprints/sprint-019-fresh-start-narrative-trust/verification/sprint-019-verification-queries.md
```

If the repo does not use a `verification/` subfolder inside sprint folders, create it for this sprint.

---

## Files to Modify

```text
None
```

---

## Do Not Modify

```text
src/
context-owl-ui/
```

Do not modify application code, tests, production data, or configuration in this task.

---

## Implementation Requirements

- [x] Create the verification markdown file.
- [x] Include only read-only Mongo queries unless a section is explicitly marked as manual remediation and requires approval.
- [x] Include warnings not to run refresh tasks or briefing generation against production unless approved.
- [x] Include expected results for each query.
- [x] Include a section for post-deploy checks.
- [x] Include a section for rollback checks.
- [x] Include cost checks using `llm_traces.timestamp`, `llm_traces.operation`, and `llm_traces.cost`.

### Required Query Sections

1. Invalid published briefing detection
2. Trusted briefing narrative eligibility count
3. Recent activity narrative count
4. Article-cluster display candidate count
5. Legacy stale inventory count
6. Narrative refresh backlog count
7. LLM cost in last 24 hours by operation
8. Public-copy forbidden word scan, if display fields are stored or queryable

### Configuration

Use this cutoff in examples:

```text
FRESH_START_CUTOFF=2026-05-10T00:00:00Z
```

### Commands to Run

Documentation-only task. No automated tests required.

---

## Verification

### Automated Verification

- [x] Markdown file exists at the expected path.
- [x] `git diff` shows only the verification markdown file.

### Manual Verification

- [x] Review the document and confirm every query is read-only.
- [x] Confirm expected results are documented.
- [x] Confirm no production mutation command is included outside a clearly marked, approval-required section.

---

## Acceptance Criteria

- [x] Verification document includes invalid published briefing query.
- [x] Verification document includes trusted-summary eligibility query.
- [x] Verification document includes recent activity narrative query.
- [x] Verification document includes narrative refresh backlog query.
- [x] Verification document includes LLM cost by operation query.
- [x] Verification document includes explicit warnings against unapproved production writes and refresh jobs.
- [x] No application code is changed.

---

## Impact

Expected impact:

- Makes Sprint 019 safer to validate.
- Reduces repeated ad hoc Mongo query writing.
- Provides a handoff checklist for implementation agents and manual review.

User-facing impact:

- None directly.

Cost impact:

- None. Queries are read-only and do not invoke LLM calls.

---

## Related Tickets

- TASK-095: Briefing and Narrative Refresh Investigation
- BUG-099: Prevent Invalid Briefings From Publishing
- FEATURE-060: Add Trusted Summary Eligibility for Briefings
- FEATURE-061: Add Narrative Display Mode API Fields
- FEATURE-062: Add Deterministic Article Cluster Fallback
- BUG-100: Ground Briefing Refinement With Source Context

---

## Completion Summary

- Branch: `task/sprint-019-verification-queries`
- Commit: `d234066`
- Changes made:
  - Created `docs/sprints/sprint-019-fresh-start-narrative-trust/verification/sprint-019-verification-queries.md` (1,056 lines)
  - 13 read-only Mongo queries across 7 verification areas
  - 8-point post-deploy checklist
  - Rollback validation procedure
  - Local verification commands (git, grep, build)
  - Expected health indicators table
  - Troubleshooting guidance
- Tests run: N/A (documentation-only task)
- Manual verification:
  - All queries verified as read-only (find, countDocuments, aggregate only)
  - Lifecycle states verified from codebase (emerging, rising, hot, reactivated, cooling, echo, dormant)
  - Mongo projection syntax corrected for copy-paste runnable queries
  - 5 cleanup passes applied and verified
- Deviations from plan: None. All acceptance criteria met.
