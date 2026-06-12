# Product Spec: BugOps

---

**Note:** This is a real product spec written for a production feature I built inside Backdrop, a multi-service AI pipeline I developed and operate independently. The primary user is an internal operator persona: the person responsible for keeping the system reliable in production. In the current implementation, I am that operator, which made the feedback loop unusually tight and grounded the product in real operational pain. The system described here is running in production.

---

## 1. Product Summary

BugOps is a production monitoring, triage, and debugging-assistance system for a multi-service AI pipeline.

Its purpose is to detect production issues, normalize them into durable bug cases, notify the operator, preserve evidence, and support the full path from production failure to verified fix.

BugOps begins with deterministic signal detection and manual operator control. It does not start with autonomous remediation, LLM diagnosis, or automatic code changes.

Initial production path:

```text
llm_traces → bug_alert_event → bug_case → optional alert → deterministic report
```

---

## 2. Why This Matters for AI Systems

Production AI systems have a reliability problem that traditional monitoring does not fully address.

When a service crashes, the signal is clear. When an LLM pipeline degrades, the signal is often subtle: outputs become less grounded, costs drift upward, generated summaries stop passing validation, or evidence stops flowing into downstream generation steps. By the time the failure is obvious, the evidence is gone.

AI systems also carry a specific trust risk: generated artifacts can become inputs to subsequent generation. If a degraded output quietly propagates through the pipeline, the system compounds the error rather than surfacing it. Standard alerting does not catch this because there is no exception to catch.

BugOps is designed around this reality. It treats production signals as evidence, not just alerts. It preserves that evidence before it disappears. It keeps deterministic facts separate from LLM interpretation until the evidence layer is solid. And it keeps humans in the loop on diagnosis and resolution until the system has earned enough trust to support more automation.

The same pattern applies to any AI-native product operating at scale: evidence first, trust boundaries enforced, automation only after the manual workflow is understood.

---

## 3. Problem

The system is a production AI pipeline with multiple moving parts:

- FastAPI backend
- Celery workers
- Redis
- MongoDB
- Cloud deployment
- Frontend
- LLM gateway
- trace logging
- cost controls
- scheduled processing
- briefing and narrative generation

When something breaks, the debugging process is too manual.

The operator has to inspect deployment logs, MongoDB, LLM traces, service logs, test output, implementation summaries, and code changes, then reconstruct what happened.

This is slow, error-prone, and especially painful when production behaves differently from local validation.

Recent rollout issues showed the gap clearly:

- disabled mode initialized dependencies it should not have touched
- enabled mode hit async/sync database getter mismatches
- runtime and import paths behaved differently in production
- production validation exposed issues that local tests did not catch

BugOps exists to reduce this production-debugging burden.

---

## 4. User

### Primary User

- Solo operator and builder of the system

### Secondary Future Users

- AI coding agent
- reviewing agent
- future maintainers
- product and engineering collaborators

### Current User Needs

- know when production has a meaningful issue
- avoid manually watching logs all the time
- distinguish real issues from noise
- preserve evidence before it disappears
- know what to check next
- avoid duplicate investigation of the same issue
- eventually hand clean bug context to a coding agent

---

## 5. Goals

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

## 6. Non-Goals

BugOps is not initially trying to be:

- a full observability platform
- a Datadog replacement
- a log search engine
- an autonomous remediation agent
- an incident management system
- an LLM-first diagnosis tool
- a dashboard product
- a general-purpose bug tracker
- an auto-fix / auto-merge system

Important initial constraints:

- no LLM calls in the critical alert path
- no autonomous code changes
- no automatic remediation
- no fuzzy correlation until deterministic grouping proves insufficient
- no operator UI until manual workflows are clear

---

## 7. Current State

### Implemented

The smallest end-to-end BugOps signal path is proven and running in production:

```text
llm_traces signal
→ normalized bug_alert_event
→ bug_case
→ one-way alert for new cases only
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
- one-way notifications
- deterministic case report
- persisted heartbeat

Current active signal source:

- LLM cost runaway detection

Current case grouping:

- exact `dedupe_key` matching only

Current notification behavior:

- sends only when a new case is created
- does not send for repeated alerts attached to an existing open case

Current report behavior:

- deterministic report only
- no LLM synthesis
- no unsupported causality language

---

## 8. Key Concepts

### Signal Source

A `SignalSource` is a modular source of production signals.

Examples:

- LLM traces
- deployment logs
- FastAPI runtime errors
- worker task failures
- database reliability errors
- worker heartbeat failures

Each source emits normalized alert events.

### Bug Alert Event

A `bug_alert_event` is a normalized record of one detected signal.

Example fields:

- `source_type`
- `alert_type`
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

No fuzzy matching. No LLM matching. No multi-source correlation yet.

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

## 9. Functional Requirements

### FR1: Monitor Loop

BugOps must run as a separate production process.

It should:

- load enabled signal sources
- poll on a configured interval
- create alert events
- create or update bug cases
- optionally send notifications
- log poll results
- avoid crashing on recoverable source errors

### FR2: Disabled Mode

When disabled:

- BugOps exits cleanly
- BugOps does not initialize database connections
- BugOps does not initialize messaging integrations
- BugOps does not import unnecessary runtime dependencies

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

### FR5: Notifications

When notifications are enabled:

- send only for new cases
- do not send for repeated alerts attached to the same open case
- include core case fields
- include observed metrics
- include suggested manual check
- handle notification failure without crashing

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

Fields:

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
- database-level uniqueness or upsert safety where straightforward

### FR10: Runtime Failure Detection

BugOps should expand beyond LLM cost monitoring to detect runtime failures.

Target patterns:

- startup crashes
- Python tracebacks
- import and name errors
- database connection failures
- messaging integration failures
- platform log-rate-limit warnings

---

## 10. Non-Functional Requirements

### Reliability

BugOps should fail safely.

- Source failure should not crash the whole monitor.
- Notification failure should not crash the monitor.
- One bad alert should not block future polling.
- Disabled mode should be clean and dependency-light.

### Cost

BugOps should be cheap to run.

- No LLM in critical path.
- Poll interval configurable.
- Minimal memory footprint.
- Single replica.
- No expensive background processing.

### Safety

BugOps should not modify production application data.

Allowed writes:

- `bug_alert_events`
- `bug_cases`
- `bug_case_reports`
- `bug_heartbeats`

BugOps should not write to production pipeline collections.

### Observability

BugOps itself must be observable.

Minimum:

- startup logs
- enabled/disabled state logs
- poll-complete logs
- source error logs
- notification success/failure logs
- persisted heartbeat

### Maintainability

BugOps should remain modular.

New signal sources should plug into the `SignalSource` seam without changing the core alert-to-case flow.

---

## 11. Data Model

### `bug_alert_events`

Purpose: Store normalized production signals.

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

Purpose: Store durable operator-facing cases.

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

Purpose: Store generated deterministic reports.

Important fields:

- `report_id`
- `case_id`
- `report_text`
- `generated_at`
- `report_type`

### `bug_heartbeats`

Purpose: Show whether BugOps is alive and polling.

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

## 12. Architecture

### Process

BugOps runs as a separate service alongside the main application.

### Core Modules

```text
bugops/
  config.py
  monitor.py
  models.py
  store.py
  notifications.py
  reports.py
  signal_sources/
    base.py
    llm_traces.py
    runtime_logs.py
    app_runtime.py
    worker_failures.py
    db_reliability.py
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
9. Notifications send only for new cases.
10. Reports can be generated deterministically.
11. Heartbeat is logged and persisted.

---

## 13. Roadmap

### Phase 1 — Signal Intake Foundation

Prove first end-to-end path:

```text
llm_traces → bug_alert_event → bug_case → notification/report
```

Status: Done.

### Phase 2 — Production Hardening

Make BugOps safe and trustworthy enough to leave running.

Scope:

- heartbeat logs
- persisted heartbeat
- startup noise cleanup
- notification production validation
- idempotency guardrails
- short operator runbook

### Phase 3 — Runtime Failure Detection

Expand beyond LLM cost monitoring.

Scope:

- minimal runtime log detector
- startup crash detection
- Python exception detection
- database and cache failure patterns
- notification failure pattern detection
- platform log-rate-limit warnings

### Phase 4 — Structured App and Worker Error Signals

Add cleaner first-class signals.

Scope:

- exception middleware
- task failure hooks
- database reliability instrumentation
- worker liveness checks
- retry storm detection

### Phase 5 — Diagnosis Packs

Make cases actionable.

Scope:

- evidence bundle
- related traces and logs
- known facts and unknowns
- suggested checks
- safe queries and commands

### Phase 6 — Manual Case Workflow

Make cases easy to operate manually.

Scope:

- list open cases
- view report
- resolve case
- close case
- add note
- attach validation evidence

### Phase 7 — LLM Case Synthesis

Add cautious AI interpretation over deterministic evidence.

Scope:

- summarize diagnosis pack
- suggest hypotheses
- suggest checks
- cite evidence
- label uncertainty

### Phase 8 — Fix Brief Generation

Turn cases into agent-ready fix briefs.

Scope:

- problem statement
- evidence
- suspected files
- constraints
- tests
- validation plan
- rollback notes

### Phase 9 — Coding Agent Verification Harness

Review agent-generated fixes against the ticket and evidence.

Scope:

- ticket and fix brief
- code diff
- implementation summary
- test output
- verdict and concerns
- follow-up prompt

### Phase 10 — Closed-Loop Validation

Verify that shipped fixes actually resolved the production issue.

Scope:

- post-fix monitoring
- alert pattern stopped
- metrics returned to baseline
- case closed with evidence

---

## 14. Success Metrics

### Primary Outcome

Reduce time spent reconstructing production failures from 30–60 minutes of manual log inspection to under 10 minutes per meaningful incident.

### Short-Term

BugOps is successful after Phase 2 if:

- it runs continuously in production
- it emits heartbeat logs
- it does not create confusing startup noise
- it does not duplicate open cases
- notification behavior is validated
- it can detect and case LLM cost runaway
- reports are deterministic and useful

### Medium-Term

BugOps is successful after Phases 3 through 5 if:

- it detects runtime failures beyond LLM cost
- it catches issues that would otherwise require manual log watching
- cases contain enough evidence to start debugging quickly
- diagnosis packs reduce manual investigation time
- alerts are useful enough to keep enabled

### Long-Term

BugOps is successful if:

- production failures become durable cases
- evidence is preserved automatically
- the operator spends less time reconstructing what happened
- a coding agent receives better bug context
- fixes can be validated against the original production signal

---

## 15. Risks

### Risk: BugOps becomes too broad

Mitigation: Add signal sources incrementally. Do not build a full observability platform.

### Risk: Alert noise

Mitigation: Start with narrow, high-confidence patterns. Notify only on new cases.

### Risk: LLM hallucination

Mitigation: Keep deterministic facts separate from LLM synthesis. Do not add LLM interpretation until diagnosis packs exist.

### Risk: Duplicate cases

Mitigation: Use deterministic `dedupe_key` logic and database-level guardrails.

### Risk: Log sources are messy

Mitigation: Use deployment logs only for narrow runtime failure patterns. Add structured app signals later.

### Risk: The system becomes more interesting than useful

Mitigation: Only expand when real production pain justifies the next layer.

---

## 16. Open Questions

1. Should deployment logs be the primary Phase 3 source, or only a startup-crash safety net?
2. Which structured signal should come first: application errors, worker failures, or database reliability?
3. How much case lifecycle is needed before adding an operator UI?
4. Are diagnosis packs enough before LLM synthesis?
5. When should BugOps integrate directly with a coding agent?
6. Should fix brief generation be part of BugOps or a separate tooling track?

---

## 17. Tradeoffs

### Deterministic detection before LLM diagnosis

Chose to build evidence collection and case grouping entirely without LLM calls before adding any AI interpretation. A false root cause claim in an alert erodes trust in the whole system faster than a missing hypothesis. Evidence first; synthesis only after the deterministic layer is solid.

### Exact dedupe matching before fuzzy correlation

Chose exact `dedupe_key` matching over semantic or fuzzy grouping. Fuzzy matching can silently merge unrelated cases, making it harder to isolate the real failure. The cost is occasional duplicate cases for the same underlying issue. That is a manageable operator burden; invisible case merges are not.

### Separate monitoring process over inline alerting

Chose to run BugOps as a separate process rather than embedding alerts inside the main pipeline. Inline alerting creates coupling between the monitoring system and the system being monitored — a bad alert path can affect production throughput. Separation keeps the failure modes isolated.

### Narrow signal coverage over broad instrumentation

Chose to expand signal sources only when real production pain justifies it, rather than instrumenting everything upfront. Broad instrumentation creates alert noise that operators learn to ignore. High-confidence signals on a narrow surface are more useful than comprehensive coverage that no one trusts.

---

## 18. Product Principle

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
