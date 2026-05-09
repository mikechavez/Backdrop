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
| 2 | FEATURE-057 | BugOps normalized alert-event and case store | ✅ DONE | M | M |
| 3 | FEATURE-058 | Implement llm_traces cost-runaway signal source | ✅ DONE | M | M |
| 4 | FEATURE-059 | Alert-to-case flow by dedupe_key | ✅ DONE | S | S |
| 5 | TASK-090 | One-way BugOps Slack webhook notification | ✅ DONE | S | S |
| 6 | TASK-091 | Minimal deterministic case report | ✅ DONE | S | S |
| 7 | TASK-093 | Railway log data-shape spike | ✅ DONE | S | S |
| 8 | TASK-092 | Update BugOps docs with Sprint 018 scope | ✅ DONE | S | S |

---

## Success Criteria

- [x] A separate `bugops` process can be started locally without starting FastAPI, Celery worker, or Celery Beat.
- [x] `bugops` reads `llm_traces` and detects a simulated or real cost-runaway threshold breach.
- [x] A normalized `bug_alert_events` document is created with `severity`, `dedupe_key`, and `correlation_keys`.
- [x] A thin `bug_cases` document is created or reused by exact `dedupe_key`.
- [x] Repeated alerts in the same hourly `dedupe_key` window do not create duplicate cases.
- [x] A one-way Slack webhook message is sent when a new BugOps case is created.
- [x] A minimal deterministic report is written from recorded case/event data.
- [x] Real Railway log sample output is captured and mapped to the proposed `bug_alert_events` schema.
- [x] No BugOps code writes to existing production app collections except reading `llm_traces` and writing new `bug_*` collections.

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
| BUG-095 | BugOps disabled mode initializes Redis/shared app dependencies | Disabled mode should exit early before importing heavy settings | ✅ COMPLETE |
| BUG-096 | BugOps enabled mode crashes with async Motor database TypeError | Monitor called sync `get_database()` instead of async `get_async_database()` | ✅ COMPLETE |
| BUG-097 | BugOps alert event hydration fails on Mongo ObjectId `_id` | Mongo `ObjectId._id` not normalized to string before Pydantic validation | ✅ COMPLETE |

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

### Session 2 (2026-05-08) — FEATURE-057 ✅
**BugOps normalized alert-event and case store**
- Branch: `feature/057-bugops-normalized-event-case-store` | Commits: `337ac62`, `a06850c`
- Implemented comprehensive BugOps data models: BugAlertEvent, BugCase, BugCaseEvent, BugToolCall
- AlertSeverity enum: info, warning, high, critical (exact spec)
- AlertStatus enum: new, attached, ignored
- CaseStatus enum: open, resolved, closed (manual-only lifecycle)
- BugOpsStore class with Motor async integration for 4 MongoDB collections
- Store methods: create_alert_event, find_open_case_by_dedupe_key, create_case_from_alert, attach_alert_to_case, get_case
- All 22 tests passing (11 model tests, 11 store tests)
- Ready for FEATURE-058 (llm_traces cost-runaway signal source implementation)

### Session 3 (2026-05-08) — FEATURE-058 ✅
**Implement llm_traces cost-runaway signal source**
- Branch: `feature/057-bugops-normalized-event-case-store` | Commits: `d49229e`, `e2f1d50`
- Created LLMTraceCostSignalSource querying llm_traces collection (never api_costs)
- Compute spend metrics: last_5_min, last_60_min, projected_hourly
- Alert logic: critical (5-min ≥ 0.25), warning (projected_hourly ≥ 1.00)
- Rolling hourly dedupe_key: `llm_traces:cost_runaway:YYYY-MM-DD:HH` (no duplicates per hour)
- Correlation keys include top operations and models by cost
- Full metric payload with window start/end times and thresholds
- All 10 cost-source tests passing + 4 base-interface tests updated
- Monitor automatically integrated into signal source pipeline

### Session 4 (2026-05-08) — FEATURE-059 ✅
**Alert-to-case flow by dedupe_key**
- Branch: `feature/bugops-signal-intake` | Commit: TBD
- Implemented `process_alert_event()` method in BugOpsStore (store.py:83-91)
- Exact dedupe_key passthrough: creates alert → finds or creates open case → attaches alert
- Updated monitor polling loop to call process_alert_event instead of create_alert_event directly
- Created comprehensive test suite: 8 tests in test_alert_to_case_flow.py covering:
  - New case creation for new dedupe_key
  - Case reuse for same dedupe_key with open status only
  - New case created if prior case is resolved or closed
  - Correlation keys preserved but not used for matching (future use only)
  - No fuzzy correlation by time window or service (exact dedupe_key only)
- All 50 BugOps tests passing (8 new + 42 existing)
- Ready for TASK-090 (Slack webhook notification)

### Session 5 (2026-05-08) — TASK-090 ✅
**One-way BugOps Slack webhook notification**
- Branch: `feature/059-alert-to-case-flow` | Commits: `a79c94c`, `85b9e48`
- Created new module: `src/crypto_news_aggregator/bugops/slack.py`
  - `send_case_notification(case)` — async POST to BUGOPS_SLACK_WEBHOOK_URL
  - `_build_slack_message(case)` — formats case into Slack attachment with color-coding by severity
  - Graceful error handling: logs failures, returns False, doesn't crash monitor
  - 10-second timeout on HTTP requests, respects BUGOPS_SLACK_ENABLED flag
- Extended data models with new fields:
  - Added `alert_type: str` to BugCase (from BugAlertEvent)
  - Added `suggested_manual_check: Optional[str]` to BugCase for operator guidance
- Modified alert processing flow:
  - Changed `process_alert_event()` return type to `tuple[BugCase, bool]` (is_new flag)
  - Monitor only sends Slack notification when `is_new=True` (new case creation)
  - Repeated alerts attaching to existing cases skip notification
- Slack message payload includes all task-required fields:
  - case_id, severity, alert_type, source_type, metrics, suggested_manual_check, created_at
  - Color-coded by severity: info (#36a64f), warning (#ffa500), high (#ff6600), critical (#ff0000)
  - Optional fields (metrics, suggested_manual_check) only included if populated
- Comprehensive test suite: 18 tests in test_slack_notification.py
  - Message formatting (color mapping, field inclusion, optional fields)
  - Notification send (success, disabled, missing webhook, HTTP errors)
  - Monitor behavior (new case vs. existing case attachment)
- All 68 BugOps tests passing (18 new + 50 existing)

### Session 6 (2026-05-08) — TASK-091 ✅
**Minimal deterministic case report**
- Branch: `feature/059-alert-to-case-flow` | Commit: `36e6502`
- Created new module: `src/crypto_news_aggregator/bugops/reports.py`
  - `generate_case_report(case, alert_events)` — Markdown report generator from stored data only
  - Report includes: case ID, title, status, severity, timestamps, source types, dedupe key, summary, alert events with metrics, observed metrics (from case), known facts (from alert metrics), and suggested manual checks
  - Deterministic: no randomization, no LLM calls, no external dependencies
- Extended BugOpsStore with two new methods:
  - `get_alert_events_for_case(case_id)` — fetches all alert events for a case
  - `save_case_report(case_id, report)` — persists report to bug_cases.deterministic_report field
- Comprehensive test suite: 6 tests in test_reports.py
  - Report structure validation (case ID, severity, status)
  - Alert event metrics included in report
  - No unsupported root-cause claims detected
  - Report generation is deterministic
  - Report persistence to database
  - Alert event fetching from store
- All 6 new tests passing + no regressions to existing store/model tests
- Success criteria met: deterministic report from stored data, no LLM calls, persisted to bug_cases.deterministic_report

### Session 7 (2026-05-08) — TASK-093 ✅
**Railway log data-shape spike**
- Branch: `chore/093-railway-log-data-shape-spike` | Commit: `0581175`
- Ran `railway logs` against production; confirmed single service `crypto-news-aggregator` (no web/worker/beat split)
- Captured real output: gunicorn startup lines, MongoDB `AutoReconnect` stack trace, Python WARNING logs, Railway platform log-rate-limit warnings
- Key findings:
  - Two plain-text formats (Python logging, gunicorn) + JSON mode (`{message, timestamp ISO8601-nanosecond, level}`) — JSON preferred for ingestion
  - Multiline stack traces arrive line-by-line; no Railway-side grouping
  - CLI only supports `--lines` fetch; no time-window queries; Railway API token needed for non-interactive use
  - `SignalSource` interface compatible as-is
- Three priority patterns: `mongo_autoreconnect` (high), `budget_soft_limit` (warning), `platform_log_rate_limit` (warning)
- Created `tests/bugops/fixtures/railway_logs_sample.txt` — sanitized (MongoDB hostname → `<MONGO_HOST>`)
- Created `docs/bugops/railway-log-data-shape.md` — answers all 8 analysis questions + normalized mapping
- Updated `railway_logs.py` placeholder with compiled regex patterns, `BugAlertEventCreate` field mapping, 4 TODOs grounded in real log shape

### Session 8 (2026-05-08) — TASK-092 ✅
**Update BugOps docs with Sprint 018 scope**
- Branch: `feature/bugops-signal-intake` (squash to main)
- Created 6 core BugOps documentation files:
  - `00-bugops-system-overview.md` — System design, scope boundaries, key data models
  - `10-bugops-runtime-model.md` — Polling loop, alert-to-case flow, configuration
  - `20-bugops-data-model.md` — BugAlertEvent/BugCase schemas, required fields, indexing
  - `30-bugops-observability.md` — Logging patterns, error handling, debugging guide
  - `80-bugops-use-cases.md` — Example workflows, operator responsibilities
  - `90-bugops-critiques-and-open-questions.md` — Known limitations (9 items), future work, open design questions (10 items)
- All required content updates present:
  - ✅ Sprint 018 is not trying to solve BugOps; proves smallest end-to-end path
  - ✅ BugOps v1 detects and escalates; does not autonomously prevent cost cascades
  - ✅ LLM synthesis deferred
  - ✅ Slack is outbound webhook only, not Slack UI
  - ✅ Case lifecycle is manual-only
  - ✅ Alert-to-case flow is exact dedupe_key passthrough, not correlation engine
  - ✅ Cost-runaway dedupe key format: `llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}`
  - ✅ `severity` required on `bug_alert_events`
  - ✅ Railway log intake is spike only, not implemented
  - ✅ BUG-055/056/057 walkthrough is counterfactual, not historical telemetry
- Stale phrases verified: no Sprint 018 claims for autonomy, correlation, synthesis, Slack UI, LLM analysis
- All scope boundaries match Sprint 018 tickets; open questions documented for future sprints

### Session 9 (2026-05-08) — BUG-095 ✅
**BugOps disabled mode initializes Redis / Shared app dependencies**
- Branch: `fix/bug-095-bugops-disabled-mode-redis` | Commit: `08b16f1`
- **Issue**: When `BUGOPS_ENABLED=false`, disabled mode was still importing and initializing shared app settings, triggering Redis connection errors and heavy imports (MongoDB, Celery, FastAPI)
- **Solution**: Added early disabled-mode check in `main()` before `BugOpsMonitor` instantiation
  - New function: `_is_bugops_enabled_from_env()` reads `BUGOPS_ENABLED` env var via `os.getenv()`
  - Accepts `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive) as truthy; defaults to false
  - Check happens before any heavy imports
  - Deferred imports: Moved `get_bugops_settings()`, `BugOpsStore`, signal sources into `BugOpsMonitor.__init__()`
- **Tests**: Added 4 new tests
  - `test_is_bugops_enabled_from_env_*` — env var parsing (3 tests)
  - `test_bugops_monitor_does_not_initialize_mongo_when_disabled` — verify store uninitialized
  - `test_bugops_monitor_does_not_initialize_signal_sources_mongo` — verify mongo_manager.initialize() never called
  - `test_main_exits_early_when_bugops_disabled` — verify main() exits cleanly
- **Verification**: All 12 monitor config tests passing; disabled mode logs only disabled message, no Redis errors; exit code 0
- **Acceptance criteria**: All 10 items checked ✅

### Session 10 (2026-05-09) — BUG-097 ✅
**BugOps alert event hydration fails on Mongo ObjectId `_id`**
- Branch: `fix/bug-096-bugops-enabled-mode-mongo-getter` | Commit: `24b6271`
- **Issue**: During controlled production validation with lowered cost thresholds, BugOps crashed on alert hydration with Pydantic validation error:
  ```
  Error collecting signals from llm_traces: 1 validation error for BugAlertEvent
  _id
  Input should be a valid string [type=string_type, input_value=ObjectId(...), input_type=ObjectId]
  ```
  Root cause: Mongo's raw `ObjectId._id` values were passed directly to Pydantic models expecting strings
- **Solution**: Added `_normalize_mongo_doc()` helper in `store.py` that converts `ObjectId._id` to strings before model hydration
  - Helper checks `isinstance(_id, ObjectId)` and converts to `str()` safely
  - Applied to all 7 store methods that hydrate Pydantic models from Mongo documents
  - Mongo `_id` remains separate from application-level `alert_id` / `case_id` (database implementation detail vs. domain model)
- **Test Coverage**: Added 10 new tests
  - Unit tests for `_normalize_mongo_doc()` with ObjectId, None, string ID, and missing ID cases (4 tests)
  - Integration tests for each affected method verifying ObjectId normalization (6 tests)
  - All 21 store tests passing (11 existing + 10 new)
- **Verification**: 
  - ✅ Controlled alerts no longer raise validation errors
  - ✅ Mongo _id remains separate from alert_id/case_id (ID architecture intact)
  - ✅ All existing tests continue to pass
  - ✅ No LLM calls introduced
  - ✅ No non-BugOps collections modified
