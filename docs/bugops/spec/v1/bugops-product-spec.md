# Product Spec: BugOps

## 1. Product Summary

BugOps is a production monitoring, triage, and debugging-assistance system for Backdrop.

Its purpose is to detect production issues, normalize them into durable bug cases, notify the operator, preserve evidence, and eventually support the full path from production failure to verified fix.

BugOps begins with deterministic signal detection and manual operator control. It does not start with autonomous remediation, LLM diagnosis, or automatic code changes.

Initial production path:

```text
llm_traces → bug_alert_event → bug_case → optional Slack alert → deterministic report
```

Sprint 018 proved this first path for LLM cost runaway detection. Runtime errors, Railway failures, worker failures, and structured app errors are planned future coverage areas, not yet fully implemented.

---

## 2. Problem

Backdrop is a production AI system with multiple moving parts:

- FastAPI backend
- Celery workers
- Redis
- MongoDB
- Railway deployment
- Vercel frontend
- LLM gateway
- trace logging
- cost controls
- scheduled processing
- briefing and narrative generation

When something breaks, the current debugging process is too manual.

The operator has to inspect Railway logs, MongoDB, `llm_traces`, service logs, test output, implementation summaries, and code changes, then reconstruct what happened.

This is slow, error-prone, and especially painful when production behaves differently from local validation.

Recent Sprint 018 rollout bugs showed the gap clearly:

- disabled mode initialized dependencies it should not have touched
- enabled mode hit async/sync Mongo getter mismatch
- runtime/import paths behaved differently in production
- production validation exposed issues that local tests did not catch

BugOps exists to reduce this production-debugging burden.

---

## 3. User

### Primary User

- Solo operator / builder of Backdrop

### Secondary Future Users

- AI coding agent
- reviewing agent
- future maintainers
- product/engineering collaborators

### Current User Needs

- know when production has a meaningful issue
- avoid manually watching logs all the time
- distinguish real issues from noise
- preserve evidence before it disappears
- know what to check next
- avoid duplicate investigation of the same issue
- eventually hand clean bug context to Claude Code

---

## 4. Goals

### Core Goals

1. Detect production signals that indicate real operational issues.
2. Normalize raw signals into structured bug alert events.
3. Group related alerts into durable bug cases.
4. Notify the operator only when a new case is created.
5. Preserve deterministic evidence for debugging.
6. Generate deterministic case reports.
7. Keep humans in control of diagnosis, fixing, and closing cases.
8. Expand signal coverage over time based on real production pain.

### Long-Term Goal

Create a closed-loop bug operations system:

```text
production failure
→ normalized case
→ evidence bundle
→ diagnosis pack
→ fix brief
→ coding agent implementation
→ verification review
→ post-fix production validation
→ case closure with evidence
```

---

## 5. Non-Goals

BugOps is not initially trying to be:

- a full observability platform
- a Datadog replacement
- a Railway log search engine
- an autonomous remediation agent
- a Slack-based incident management system
- an LLM-first diagnosis tool
- a dashboard product
- a general-purpose bug tracker
- an auto-fix / auto-merge system

Important initial constraints:

- no LLM calls in the critical alert path
- no autonomous code changes
- no automatic remediation
- no fuzzy correlation until deterministic grouping proves insufficient
- no Slack UI until manual workflows are clear

---

## 6. Current State

### Implemented in Sprint 018

Sprint 018 proved the smallest end-to-end BugOps signal path:

```text
llm_traces signal
→ normalized bug_alert_event
→ bug_case
→ one-way Slack webhook alert for new cases only
→ minimal deterministic report
```

Implemented components:

- BugOps service skeleton
- `SignalSource` seam
- `LLMTraceCostSignalSource`
- `BugAlertEvent` model
- `BugCase` model
- `BugOpsStore`
- alert-to-case flow by `dedupe_key`
- one-way Slack notification
- deterministic case report
- Railway log data-shape spike
- BugOps docs
- Railway production service setup

Current active signal source:

- `llm_traces` cost runaway detection

Current alert type:

- `cost_runaway`

Current case grouping:

- exact `dedupe_key` matching

Current notification behavior:

- Slack sends only when a new case is created
- Slack does not send for repeated alerts attached to an existing open case

Current report behavior:

- deterministic report only
- no LLM synthesis
- no unsupported causality language

---

## 7. Key Concepts

### Signal Source

A `SignalSource` is a modular source of production signals.

Examples:

- `llm_traces`
- Railway logs
- FastAPI runtime errors
- Celery task failures
- Mongo reliability errors
- worker heartbeat failures

Each source emits normalized alert events.

### Bug Alert Event

A `bug_alert_event` is a normalized record of one detected signal.

Example fields:

- `source_type`: `llm_traces`
- `alert_type`: `cost_runaway`
- `severity`: `warning`, `high`, or `critical`
- `dedupe_key`
- observed metrics
- source metadata
- `created_at`

Alert events are immutable evidence.

### Bug Case

A `bug_case` groups one or more alert events into an operator-facing case.

Cases represent things worth investigating.

A case has:

- `case_id`
- `status`
- `severity`
- `title`
- `summary`
- `dedupe_key`
- `source_types`
- `alert_ids`
- `created_at`
- `updated_at`

### Dedupe Key

A deterministic key used to decide whether an alert belongs to an existing open case.

Initial rule:

- exact `dedupe_key` match only

No fuzzy matching.

No LLM matching.

No multi-source correlation yet.

### Deterministic Report

A generated report based only on stored facts.

It includes:

- case metadata
- alert events
- observed metrics
- known facts
- suggested manual checks

It does not include unsupported root cause claims.

---

## 8. Functional Requirements

### FR1: Monitor Loop

BugOps must run as a separate production process.

It should:

- load enabled signal sources
- poll on a configured interval
- create alert events
- create or update bug cases
- optionally send Slack notifications
- log poll results
- avoid crashing on recoverable source errors

### FR2: Disabled Mode

When `BUGOPS_ENABLED=false`:

- BugOps exits cleanly
- BugOps does not initialize Mongo
- BugOps does not initialize Redis
- BugOps does not initialize Slack
- BugOps does not import unnecessary app runtime dependencies

### FR3: Alert Event Creation

For each detected signal, BugOps must create a normalized `bug_alert_event`.

Alert events should include:

- `alert_id`
- `source_type`
- `alert_type`
- `severity`
- `title`
- `summary`
- `dedupe_key`
- `correlation_keys`
- metric payload
- source metadata
- `created_at`

### FR4: Alert-to-Case Flow

For each alert event:

1. Store the alert event.
2. Look for an open case with the same `dedupe_key`.
3. If no open case exists, create a new case.
4. If an open case exists, attach the alert to that case.
5. Return whether the case is new.

### FR5: Slack Notification

When Slack is enabled:

- send only for new cases
- do not send for repeated alerts attached to the same open case
- include core case fields
- include observed metrics
- include suggested manual check
- handle webhook failure without crashing

When Slack is disabled:

- send nothing
- continue normal case creation

### FR6: Deterministic Case Report

BugOps must generate a deterministic report for a case.

Report includes:

- case ID
- status
- severity
- source types
- dedupe key
- created / updated timestamps
- summary
- alert events
- observed metrics
- known facts
- suggested manual checks

Report must not include unsupported causality phrases such as:

- caused by
- due to
- root cause
- leads to
- is responsible for

### FR7: Heartbeat Logging

BugOps must log poll completion.

Example:

```text
BugOps poll complete: sources=1 alerts=0 cases_created=0 cases_updated=0 duration_ms=123
```

### FR8: Persisted Heartbeat

BugOps should persist heartbeat status so silent monitor failure is detectable.

Suggested collection:

```text
bug_heartbeats
```

Suggested fields:

- service
- last_poll_at
- status
- sources_checked
- alerts_found
- cases_created
- duration_ms
- error_message

### FR9: Idempotency Guardrails

BugOps should prevent duplicate open cases for the same `dedupe_key`.

Initial approach:

- one production replica
- documented one-replica assumption
- Mongo-level uniqueness or upsert safety where straightforward

### FR10: Runtime Failure Detection

BugOps should expand beyond LLM cost monitoring to detect runtime failures.

Initial runtime source:

- minimal Railway log detector

Target patterns:

- startup crashes
- Python tracebacks
- `ModuleNotFoundError`
- `NameError`
- `TypeError`
- ObjectId serialization/hydration errors
- Mongo `AutoReconnect`
- Redis connection failures
- Slack notification failures
- Railway platform log-rate-limit warnings

---

## 9. Non-Functional Requirements

### Reliability

BugOps should fail safely.

- Source failure should not crash the whole monitor.
- Slack failure should not crash the monitor.
- One bad alert should not block future polling.
- Disabled mode should be clean and dependency-light.

### Cost

BugOps should be cheap to run.

- No LLM in critical path.
- Poll interval configurable.
- Minimal memory footprint.
- One Railway replica.
- No expensive background processing.

### Safety

BugOps should not modify production application data.

Allowed writes:

- `bug_alert_events`
- `bug_cases`
- `bug_case_reports`
- `bug_heartbeats`
- future `bug_case_events` if needed

BugOps should not write to:

- `articles`
- `narratives`
- `briefings`
- `api_costs`
- `llm_traces`
- production pipeline collections

### Observability

BugOps itself must be observable.

Minimum:

- startup logs
- enabled/disabled state logs
- poll-complete logs
- source error logs
- Slack success/failure logs
- persisted heartbeat

### Maintainability

BugOps should remain modular.

New signal sources should plug into the `SignalSource` seam without changing the core alert-to-case flow.

---

## 10. Data Model

### `bug_alert_events`

Purpose:

Store normalized production signals.

Important fields:

- `alert_id`
- `source_type`
- `alert_type`
- `severity`
- `title`
- `summary`
- `dedupe_key`
- `correlation_keys`
- `metric`
- `source_metadata`
- `case_id`
- `created_at`

### `bug_cases`

Purpose:

Store durable operator-facing cases.

Important fields:

- `case_id`
- `status`
- `severity`
- `title`
- `summary`
- `dedupe_key`
- `source_types`
- `alert_ids`
- `created_at`
- `updated_at`
- `resolved_at`
- `closed_at`

Current lifecycle:

```text
open → resolved → closed
```

### `bug_case_reports`

Purpose:

Store generated deterministic reports.

Important fields:

- `report_id`
- `case_id`
- `report_text`
- `generated_at`
- `report_type`

### `bug_heartbeats`

Purpose:

Show whether BugOps is alive and polling.

Important fields:

- service
- last_poll_at
- status
- sources_checked
- alerts_found
- cases_created
- duration_ms
- error_message

---

## 11. Architecture

### Process

BugOps runs as a separate Railway service.

Production start command:

```bash
PYTHONPATH=/app/src python -m crypto_news_aggregator.bugops.monitor
```

Local command:

```bash
PYTHONPATH=src python -m crypto_news_aggregator.bugops.monitor
```

### Core Modules

Suggested existing / future structure:

```text
src/crypto_news_aggregator/bugops/
  config.py
  monitor.py
  models.py
  store.py
  slack.py
  reports.py
  signal_sources/
    base.py
    llm_traces.py
    railway_logs.py
    app_runtime.py
    worker_failures.py
    mongo_reliability.py
```

### Flow

1. Monitor starts.
2. Config is loaded.
3. If disabled, exit cleanly.
4. Signal sources are initialized.
5. Monitor polls each source.
6. Sources emit alert events.
7. Store creates alert events.
8. Store creates or updates cases.
9. Slack sends only for new cases.
10. Reports can be generated deterministically.
11. Heartbeat is logged and persisted.

---

## 12. Roadmap

### Sprint 018 — Signal Intake Foundation

Prove first end-to-end path:

```text
llm_traces → bug_alert_event → bug_case → Slack/report
```

Status:

- Done

### Sprint 019 — Production Hardening

Make BugOps safe and trustworthy enough to leave running.

Scope:

- heartbeat logs
- persisted heartbeat
- Redis/startup noise cleanup
- Slack production validation
- idempotency guardrails
- short operator runbook

### Sprint 020 — Runtime Failure Detection

Expand beyond LLM cost monitoring.

Scope:

- minimal Railway runtime error detector
- startup crash detection
- Python exception detection
- Mongo/Redis failure patterns
- Slack failure pattern detection
- platform log-rate-limit warnings

### Sprint 021 — Structured App and Worker Error Signals

Add cleaner first-class signals.

Scope:

- FastAPI exception middleware
- Celery task failure hooks
- Mongo reliability instrumentation
- worker/beat liveness checks
- retry storm detection

### Sprint 022 — Diagnosis Packs

Make cases actionable.

Scope:

- evidence bundle
- related traces
- related logs
- known facts
- unknowns
- suggested checks
- safe commands / queries

### Sprint 023 — Manual Case Workflow

Make cases easy to operate manually.

Scope:

- list open cases
- view report
- resolve case
- close case
- add note
- attach validation evidence

### Sprint 024 — Slack Operator UI

Add lightweight Slack controls.

Scope:

- acknowledge
- resolve
- close
- generate diagnosis pack
- link to case/report

### Sprint 025 — LLM Case Synthesis

Add cautious AI interpretation over deterministic evidence.

Scope:

- summarize diagnosis pack
- suggest hypotheses
- suggest checks
- cite evidence
- label uncertainty

### Sprint 026 — Fix Brief Generation

Turn cases into agent-ready fix briefs.

Scope:

- problem statement
- evidence
- suspected files
- constraints
- tests
- validation plan
- rollback notes

### Sprint 027 — Coding Agent Verification Harness

Review Claude Code fixes against the ticket and evidence.

Scope:

- ticket/fix brief
- git diff
- implementation summary
- test output
- verdict
- concerns
- follow-up prompt

### Sprint 028 — Closed-Loop BugOps Validation

Verify that shipped fixes actually resolved the production issue.

Scope:

- post-fix monitoring
- alert pattern stopped
- metrics returned to baseline
- case closed with evidence

---

## 13. Success Metrics

### Short-Term Success

BugOps is successful after Sprint 019 if:

- it runs continuously in production
- it emits heartbeat logs
- it does not create confusing startup noise
- it does not duplicate open cases
- Slack behavior is validated
- it can detect and case LLM cost runaway
- reports are deterministic and useful

### Medium-Term Success

BugOps is successful after Sprint 020–022 if:

- it detects runtime failures beyond LLM cost
- it catches startup/runtime issues that would otherwise require manual log watching
- cases contain enough evidence to start debugging quickly
- diagnosis packs reduce manual investigation time
- alerts are useful enough to keep enabled

### Long-Term Success

BugOps is successful if:

- production failures become durable cases
- evidence is preserved automatically
- the operator spends less time reconstructing what happened
- Claude Code receives better bug context
- fixes can be validated against the original production signal

---

## 14. Risks

### Risk: BugOps becomes too broad

Mitigation:

Add signal sources incrementally. Do not build a full observability platform.

### Risk: Alert noise

Mitigation:

Start with narrow, high-confidence patterns. Notify only on new cases.

### Risk: LLM hallucination

Mitigation:

Keep deterministic facts separate from LLM synthesis. Do not add LLM interpretation until diagnosis packs exist.

### Risk: Duplicate cases

Mitigation:

Use deterministic `dedupe_key` logic and Mongo-level guardrails.

### Risk: Railway logs are messy

Mitigation:

Use Railway logs only for narrow runtime failure patterns. Add structured app signals later.

### Risk: The system becomes more interesting than useful

Mitigation:

Only expand when real production pain justifies the next layer.

---

## 15. Open Questions

1. Should Railway logs be the primary Sprint 020 source, or only a startup-crash safety net?
2. Which structured signal should come first: FastAPI errors, Celery failures, or Mongo reliability?
3. How much case lifecycle is needed before Slack UI?
4. Are diagnosis packs enough before LLM synthesis?
5. When should BugOps integrate with Claude Code?
6. Should `bug_case_events` and `bug_tool_calls` remain in the model if unused?
7. Should fix brief generation be part of BugOps or a separate tooling track?

---

## 16. Product Principle

BugOps should not try to be smart before it is useful.

The order is:

1. detect real signals
2. preserve evidence
3. create cases
4. notify the operator
5. make cases actionable
6. support fixes
7. validate resolution

Deterministic evidence comes first.

LLM synthesis comes later.

Automation comes after manual workflow pain is understood.

