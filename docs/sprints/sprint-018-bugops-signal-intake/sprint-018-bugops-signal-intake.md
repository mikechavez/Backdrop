# Sprint 018 — BugOps Signal Intake Foundation

**Status:** In Progress
**Started:** 2026-05-08
**Target:** Prove the smallest end-to-end BugOps signal path while preserving the seam for future signal sources.

---

## Sprint Principle

**Sprint 018 is not trying to solve BugOps. It is trying to prove the smallest end-to-end signal path while preserving the seam for additional signal sources.**

This sprint builds the foundation for a deterministic runtime reliability harness. It does **not** build an autonomous bug fixer, a general Railway log monitor, a dashboard, Slack UI, LLM synthesis, or remediation automation.

---

## Sprint Goal

Build the first working BugOps signal pipeline as a separate monitor process: read one structured source (`llm_traces`), normalize a cost-runaway signal into `bug_alert_events`, create a thin `bug_cases` record, send a one-way Slack webhook notification, and generate a minimal deterministic case report.

Also validate the `SignalSource` interface against a real sample of Railway log output so future Railway log ingestion does not require rewriting the intake layer.

---

## Scope Boundary

### In Scope

- Separate BugOps monitor process/service, added to `Procfile` as `bugops`.
- Thin `SignalSource` interface.
- `LLMTraceCostSignalSource` implementation for cost-runaway alerts using `llm_traces`.
- `RailwayLogSignalSource` placeholder/stub only.
- Railway log data-shape spike using real `railway logs` output captured locally.
- Normalized `bug_alert_events` schema with `source_type`, `alert_type`, `severity`, `dedupe_key`, and `correlation_keys`.
- Thin `bug_cases` schema.
- Alert-to-case passthrough by `dedupe_key`, not a multi-source correlation engine.
- One-way Slack webhook notification using `BUGOPS_SLACK_WEBHOOK_URL`.
- Minimal deterministic case report from stored event/case data.
- Manual-only case lifecycle.

### Out of Scope

- Full Railway log ingestion.
- Railway log streaming/drain/sidecar.
- Sentry-quality fingerprinting or stack trace grouping.
- Multi-source case correlation engine.
- Slack UI, slash commands, buttons, modals, acknowledgement, or resolution actions.
- BugOps dashboard.
- LLM synthesis, Q&A, ticket drafting, or agent reasoning.
- Autonomous shutdown, deploys, env var changes, database writes to production app collections, or remediation.
- Scheduled briefing freshness monitor.
- Retry storm monitor.
- Design Review BugOps.

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| 1 | FEATURE-056 | BugOps service skeleton and SignalSource seam | ✅ DONE | M | M |
| 2 | FEATURE-057 | BugOps normalized alert-event and case store | 🔲 OPEN | M | |
| 3 | FEATURE-058 | Implement llm_traces cost-runaway signal source | 🔲 OPEN | M | |
| 4 | FEATURE-059 | Alert-to-case flow by dedupe_key | 🔲 OPEN | S | |
| 5 | TASK-090 | One-way BugOps Slack webhook notification | 🔲 OPEN | S | |
| 6 | TASK-091 | Minimal deterministic case report | 🔲 OPEN | S | |
| 7 | TASK-093 | Railway log data-shape spike | 🔲 OPEN | S | |
| 8 | TASK-092 | Update BugOps docs with Sprint 018 scope | 🔲 OPEN | S | |

---

## Success Criteria

- [ ] A separate `bugops` process can be started locally without starting FastAPI, Celery worker, or Celery Beat.
- [ ] `bugops` reads `llm_traces` and detects a simulated or real cost-runaway threshold breach.
- [ ] A normalized `bug_alert_events` document is created with `severity`, `dedupe_key`, and `correlation_keys`.
- [ ] A thin `bug_cases` document is created or reused by exact `dedupe_key`.
- [ ] Repeated alerts in the same hourly `dedupe_key` window do not create duplicate cases.
- [ ] A one-way Slack webhook message is sent when a new BugOps case is created.
- [ ] A minimal deterministic report is written from recorded case/event data.
- [ ] Real Railway log sample output is captured and mapped to the proposed `bug_alert_events` schema.
- [ ] No BugOps code writes to existing production app collections except reading `llm_traces` and writing new `bug_*` collections.

---

## Key Decisions

| Decision | Rationale |
|---|---|
| BugOps v1 is deterministic harness first, LLM later | Avoid premature autonomy and keep v1 shippable. |
| `llm_traces` is first signal source, not the core abstraction | The intake layer must support Railway logs later. |
| No correlation engine in Sprint 018 | With one live source, correlation would be speculative. Build the seam only. |
| Alert-to-case is exact `dedupe_key` passthrough | Simple enough to ship; preserves future correlation fields. |
| Cost-runaway `dedupe_key` is hourly | Avoid one perpetual cost case while grouping repeated checks in the same incident window. |
| Cases are manual-only lifecycle in Sprint 018 | No Slack UI/API/dashboard exists for ack/resolve/close yet. |
| Slack is outbound webhook only | Interactive Slack UI is a later feature. |
| BugOps monitor runs separately from Celery Beat | It must not depend on the scheduler it may later monitor. |

---

## Agent Safety Notes

- Do **not** implement remediation or shutdown behavior.
- Do **not** add LLM calls.
- Do **not** modify production app collections such as `articles`, `narratives`, `daily_briefings`, `llm_traces`, or `api_costs`.
- Do **not** build a dashboard or frontend route in this sprint.
- Do **not** implement Slack commands/buttons.
- Do **not** implement multi-source fuzzy correlation.
- Do **not** use Celery/Beat for BugOps monitor scheduling.

---

## Implementation Notes

Expected package layout:

```text
src/crypto_news_aggregator/bugops/
  __init__.py
  config.py
  monitor.py
  models.py
  store.py
  signal_sources/
    __init__.py
    base.py
    llm_traces.py
    railway_logs.py      # placeholder/stub only
  slack.py
  reports.py
```

Expected tests:

```text
tests/bugops/
  test_signal_source_base.py
  test_bugops_store.py
  test_llm_traces_cost_source.py
  test_alert_to_case_flow.py
  test_slack_notification.py
  test_reports.py
```

---

## Discovered Work

_Tickets created mid-sprint for issues found during implementation._

| Ticket | Title | Reason | Status |
|---|---|---|---|
| | | | |

---

## Session Log

### Session 1 (2026-05-08) — FEATURE-056 ✅
**BugOps service skeleton and SignalSource seam**
- Branch: `feature/056-bugops-signal-intake` | Commit: `f028537`
- Created BugOps package with independent monitor entrypoint
- Implemented SignalSource Protocol interface and wired signal sources into polling loop
- Added config settings to Settings class (6 BugOps config fields)
- Updated Procfile with bugops process entry
- Created comprehensive tests (10 tests, all passing)
- Monitor exits cleanly when disabled, no Celery/FastAPI dependencies
- Placeholder signal sources for LLMTraces and RailwayLogs ready for future implementation
