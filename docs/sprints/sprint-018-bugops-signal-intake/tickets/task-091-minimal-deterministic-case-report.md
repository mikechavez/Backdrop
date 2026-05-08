---
ticket_id: TASK-091
title: Minimal Deterministic Case Report
priority: medium
severity: medium
status: COMPLETE
date_created: 2026-05-08
date_completed: 2026-05-08
branch: feature/059-alert-to-case-flow
effort_estimate: small
---

# TASK-091: Minimal Deterministic Case Report

## Problem Statement

Sprint 018 needs a simple report generated from recorded case/event data. This should not be a rich incident report or LLM synthesis.

---

## Task

Create a deterministic Markdown report generator for a single BugOps case.

### Files to Create/Modify

```text
src/crypto_news_aggregator/bugops/reports.py
src/crypto_news_aggregator/bugops/store.py
tests/bugops/test_reports.py
```

### Implementation Requirements

Report must include:

```text
# Case <case_id>: <title>
Status
Severity
Created At
Updated At
Source Types
Dedupe Key
Summary
Alert Events
Observed Metrics
Known Facts
Suggested Manual Checks
```

Rules:

- Generate report only from `bug_cases` and `bug_alert_events` data.
- Do not call any LLM.
- Separate factual observed metrics from suggested checks.
- Store report string on `bug_cases.deterministic_report`.
- Keep report concise.

---

## Verification

```bash
pytest tests/bugops/test_reports.py
```

Test cases:

- Report includes case ID and severity.
- Report includes alert event metrics.
- Report does not include unsupported root-cause claims.
- Report is written back to case.

---

## Acceptance Criteria

- [x] Report generator exists.
- [x] Report is deterministic and uses only stored events/case data.
- [x] No LLM call is made.
- [x] Report is persisted to `bug_cases.deterministic_report`.

---

## Impact

Gives the operator useful case context while preserving the trace-first principle.

---

## Related Tickets

- FEATURE-057
- FEATURE-059
