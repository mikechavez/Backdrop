# TASK-094: Sprint 018 Closeout and End-to-End Validation

## Goal

Validate that Sprint 018 proves the smallest end-to-end BugOps signal path while preserving seams for future signal sources.

## Required Validation Path

Prove this path works:

llm_traces signal
→ normalized bug_alert_event
→ bug_case
→ one-way Slack webhook alert for new case only
→ minimal deterministic report

## Validation Checklist

1. BugOps monitor starts independently of FastAPI, Celery worker, and Celery Beat.
2. Existing app health behavior is unaffected.
3. BugOps can read `llm_traces`.
4. BugOps creates `bug_alert_events` with:
   - severity
   - source_type
   - dedupe_key
   - correlation_keys
   - metric payload
5. BugOps creates one open `bug_case`.
6. Repeated alert in the same UTC hour attaches to the existing open case by exact `dedupe_key`.
7. Repeated alert does not send a duplicate Slack notification.
8. Slack sends one-way notification when a new case is created.
9. Slack disabled/missing/failed webhook does not crash the monitor.
10. Deterministic report is generated from stored case/event data only.
11. No LLM calls are made by BugOps.
12. Railway log data-shape spike produced sanitized sample output and documented conclusions.
13. No production app collections are written except new `bug_*` collections.
14. No autonomous remediation, shutdown, deploy, env var mutation, or Slack UI was added.

## Required Closeout Report

Produce a concise Markdown report with:

- Files changed
- New environment variables
- New commands
- Tests added
- Tests run
- Manual validation steps
- Manual validation results
- Mongo collections written
- Slack behavior observed
- Railway deployment instructions
- Known limitations
- Deferred work
- Recommended Sprint 019 direction

## Code Review Checks

Search and confirm:

- No correlation engine was implemented.
- Slack is one-way only.
- No LLM calls were added.
- No Celery/Beat dependency was introduced.
- Cost source reads `llm_traces`, not `api_costs`.
- Store writes only to `bug_*` collections.
- No broad Mongo query/admin tooling was added.
- No autonomous remediation behavior exists.
- No secrets or webhook URLs are committed.

## Output

Create or update:

docs/bugops/sprint-018-closeout.md