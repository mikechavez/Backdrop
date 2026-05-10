---
ticket_id: TASK-096
title: Add Sprint 019 Verification Queries
priority: medium
severity: medium
status: OPEN
date_created: 2026-05-10
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

- [ ] Create the verification markdown file.
- [ ] Include only read-only Mongo queries unless a section is explicitly marked as manual remediation and requires approval.
- [ ] Include warnings not to run refresh tasks or briefing generation against production unless approved.
- [ ] Include expected results for each query.
- [ ] Include a section for post-deploy checks.
- [ ] Include a section for rollback checks.
- [ ] Include cost checks using `llm_traces.timestamp`, `llm_traces.operation`, and `llm_traces.cost`.

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

- [ ] Markdown file exists at the expected path.
- [ ] `git diff` shows only the verification markdown file.

### Manual Verification

- [ ] Review the document and confirm every query is read-only.
- [ ] Confirm expected results are documented.
- [ ] Confirm no production mutation command is included outside a clearly marked, approval-required section.

---

## Acceptance Criteria

- [ ] Verification document includes invalid published briefing query.
- [ ] Verification document includes trusted-summary eligibility query.
- [ ] Verification document includes recent activity narrative query.
- [ ] Verification document includes narrative refresh backlog query.
- [ ] Verification document includes LLM cost by operation query.
- [ ] Verification document includes explicit warnings against unapproved production writes and refresh jobs.
- [ ] No application code is changed.

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

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
