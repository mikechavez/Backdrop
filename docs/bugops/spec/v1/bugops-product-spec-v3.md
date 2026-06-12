# Product Spec: BugOps

---

**Note:** This is a real product spec for a production feature I built inside Backdrop, a multi-service AI pipeline I developed and operate independently. The primary user is an internal operator persona: the person responsible for keeping the system reliable in production. In the current implementation, I am that operator, which made the feedback loop unusually tight and grounded the product in real production operating needs. The system described here is running in production.

---

## 1. Product Summary

BugOps is a production monitoring, triage, and debugging-assistance system for a multi-service AI pipeline.

Its purpose is to detect production issues, normalize them into durable bug cases, notify the operator, preserve evidence, and support the full path from production failure to verified fix. BugOps turns production failures from scattered, ephemeral signals into durable, operator-facing cases with preserved evidence, reducing the time required to understand and act on incidents.

BugOps begins with deterministic signal detection and manual operator control. It does not start with autonomous remediation, LLM diagnosis, or automatic code changes.

**Status: The first end-to-end path is implemented and running in production.**

Initial production path:

```
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

The system is a production AI pipeline with multiple moving parts: FastAPI backend, Celery workers, Redis, MongoDB, cloud deployment, frontend, LLM gateway, trace logging, cost controls, scheduled processing, and generation pipelines.

When something breaks, the debugging process is too manual.

The operator has to inspect deployment logs, MongoDB, LLM traces, service logs, test output, implementation summaries, and code changes, then reconstruct what happened. This is slow, error-prone, and especially painful when production behaves differently from local validation.

Recent rollout issues showed the gap clearly:

- disabled mode initialized dependencies it should not have touched
- enabled mode hit async/sync database getter mismatches
- runtime and import paths behaved differently in production
- production validation exposed issues that local tests did not catch

BugOps exists to reduce this production-debugging burden.

---

## 4. User and Workflow

### Primary User

The person responsible for keeping the system reliable in production.

### Before BugOps

The operator manually checks deployment logs, LLM traces, MongoDB, service logs, and recent code changes — spending 30–60 minutes reconstructing what happened, often after the evidence has already rotated out.

### After BugOps

A case notification arrives only when a meaningful new issue is detected. The operator opens the deterministic report, sees the alert event, the observed metrics, and the suggested checks. Investigation starts in under 10 minutes with evidence already preserved.

### Validation Beyond the Current Operator

Because the initial operator is also the builder, the first version benefits from an unusually tight feedback loop but has a known validation limitation: it reflects one production environment and one operator's debugging habits.

Before generalizing BugOps to additional operators or teams, the next validation step would be to conduct structured interviews with other AI system operators and builders about recent production incidents, compare their debugging workflows against the BugOps case model, and test whether the case reports preserve the evidence they would need to begin investigation.

The key question is whether BugOps reduces context reconstruction for operators who did not build the underlying system and cannot rely on implicit knowledge of how it works.

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

## 5. Current State

The smallest end-to-end BugOps signal path is proven and running in production:

```
llm_traces signal
→ normalized bug_alert_event
→ bug_case
→ one-way alert for new cases only
→ minimal deterministic report
```

Implemented: BugOps service, SignalSource seam, LLMTraceCostSignalSource, BugAlertEvent model, BugCase model, BugOpsStore, alert-to-case flow by dedupe_key, one-way notifications, deterministic case report, persisted heartbeat.

Current active signal source: LLM cost runaway detection.

Current case grouping: exact dedupe_key matching only.

Notification behavior: sends only when a new case is created; does not send for repeated alerts on an existing open case.

Report behavior: deterministic only; no LLM synthesis; no unsupported causality language.

---

## 6. Goals

### Core Goals

1. Detect production signals that indicate real operational issues.
2. Normalize raw signals into structured bug alert events.
3. Group related alerts into durable bug cases.
4. Notify the operator only when a new case is created.
5. Preserve deterministic evidence for debugging.
6. Generate deterministic case reports.
7. Keep humans in control of diagnosis, fixing, and closing cases.
8. Expand signal coverage over time based on real production operating experience.

### Long-Term Goal

Create a closed-loop bug operations system:

```
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

## 7. Non-Goals

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

## 8. Key Concepts

### Signal Source

A SignalSource is a modular source of production signals. Each source emits normalized alert events.

Examples: LLM traces, deployment logs, FastAPI runtime errors, worker task failures, database reliability errors, worker heartbeat failures.

### Bug Alert Event

A bug_alert_event is a normalized record of one detected signal. Alert events are immutable evidence.

Fields: source_type, alert_type, severity (warning/high/critical), dedupe_key, observed metrics, source metadata, created_at.

### Bug Case

A bug_case groups one or more alert events into an operator-facing case. Cases represent things worth investigating.

Fields: case_id, status, severity, title, summary, dedupe_key, source_types, alert_ids, created_at, updated_at.

### Dedupe Key

A deterministic key used to decide whether an alert belongs to an existing open case. Exact match only. No fuzzy matching. No LLM matching. No multi-source correlation yet.

### Deterministic Report

A report based only on stored facts. Includes case metadata, alert events, observed metrics, known facts, and suggested manual checks. Does not include unsupported root cause claims.

---

## 9. Functional Requirements

**FR1: Monitor Loop** — Run as a separate production process. Load signal sources, poll on a configured interval, create alert events, create or update cases, optionally send notifications, log poll results, avoid crashing on recoverable source errors.

**FR2: Disabled Mode** — Exit cleanly without initializing database connections, messaging integrations, or unnecessary runtime dependencies.

**FR3: Alert Event Creation** — For each detected signal, create a normalized bug_alert_event with: alert_id, source_type, alert_type, severity, title, summary, dedupe_key, correlation_keys, metric payload, source metadata, created_at.

**FR4: Alert-to-Case Flow** — Store alert event. Find open case with matching dedupe_key. If none, create new case. If found, attach alert to existing case. Return whether case is new.

**FR5: Notifications** — Send only for new cases. Do not send for repeated alerts on an existing open case. Include core case fields, observed metrics, and suggested manual check. Handle notification failure without crashing.

**FR6: Deterministic Case Report** — Generate report from stored facts only. Must not include causality phrases: caused by, due to, root cause, leads to, is responsible for.

**FR7: Heartbeat Logging** — Log poll completion: sources checked, alerts found, cases created/updated, duration.

**FR8: Persisted Heartbeat** — Persist heartbeat status so silent monitor failure is detectable.

**FR9: Idempotency Guardrails** — Prevent duplicate open cases for the same dedupe_key via single replica and database-level guardrails.

**FR10: Runtime Failure Detection** — Expand to detect startup crashes, Python tracebacks, import errors, database connection failures, messaging failures, and platform log-rate-limit warnings.

---

## 10. Non-Functional Requirements

**Reliability** — Source failure, notification failure, and individual bad alerts must not crash the monitor or block future polling.

**Cost** — No LLM in critical path. Configurable poll interval. Minimal memory footprint. Single replica.

**Safety** — BugOps writes only to its own collections. Does not write to production pipeline collections.

**Observability** — Startup logs, enabled/disabled state logs, poll-complete logs, source error logs, notification success/failure logs, persisted heartbeat.

**Maintainability** — New signal sources plug into the SignalSource seam without changing the core alert-to-case flow.

---

## 11. Architecture

BugOps runs as a separate service alongside the main application.

Flow:

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

## 12. Roadmap

**Phase 1 — Signal Intake Foundation** — Prove first end-to-end path. Status: Done.

**Phase 2 — Production Hardening and Runtime Coverage** — Heartbeat logs, persisted heartbeat, startup noise cleanup, notification validation, idempotency guardrails, runtime failure detection, operator runbook.

**Phase 3 — Diagnosis Packs and Manual Case Workflow** — Evidence bundle, related traces and logs, known facts and unknowns, suggested checks. List open cases, view report, resolve, close, add note, attach validation evidence.

**Phase 4 — LLM Synthesis, Fix Briefs, and Closed-Loop Validation** — Summarize diagnosis pack, suggest hypotheses, cite evidence, label uncertainty. Turn cases into agent-ready fix briefs. Post-fix monitoring and case closure with evidence.

---

## 13. Success Metrics

### Primary Outcome

Reduce production failure reconstruction time from an estimated 30–60 minutes of manual log, trace, database, and deployment inspection to under 10 minutes per meaningful incident.

### Measurement Plan

For each meaningful production issue, record:

- time from first production signal to operator awareness
- time from awareness to first credible understanding of the issue
- whether the case preserved enough evidence to begin debugging without additional log archaeology
- whether the alert was useful, noisy, duplicate, or missing key context
- whether the issue required manual investigation outside the BugOps case report

### Short-Term Success

BugOps is successful after Phase 2 if:

- it runs continuously in production
- it emits and persists heartbeat status
- it creates no duplicate open cases for the same deterministic dedupe_key
- new-case notifications are useful enough to keep enabled
- deterministic reports provide enough context to begin investigation
- LLM cost runaway detection is captured as a durable case

### Medium-Term Success

BugOps is successful in the medium term if:

- it detects runtime failures beyond LLM cost drift
- it captures issues that would otherwise require manual log watching
- target: 90% of meaningful incidents produce a case with preserved evidence
- diagnosis packs reduce the number of systems the operator must inspect manually
- alert noise remains low enough that the operator continues to trust the system

### Product Impact

BugOps should increase the amount of production surface area one operator can safely manage. The goal is not only to save minutes during incidents, but to make production operations legible enough to review, hand off, and scale.

---

## 14. Risks

**BugOps becomes too broad** — Add signal sources incrementally; do not build a full observability platform.

**Alert noise** — Start with narrow, high-confidence patterns; notify only on new cases.

**LLM hallucination** — Keep deterministic facts separate from LLM synthesis; do not add interpretation until diagnosis packs exist.

**Duplicate cases** — Deterministic dedupe_key logic and database-level guardrails.

**Log sources are messy** — Use deployment logs only for narrow runtime failure patterns; add structured app signals later.

**The system becomes more interesting than useful** — Only expand when real production operating experience justifies the next layer.

---

## 15. Tradeoffs

**Deterministic detection before LLM diagnosis** — A false root cause claim in an alert erodes trust in the whole system faster than a missing hypothesis. Evidence first; synthesis only after the deterministic layer is solid.

**Exact dedupe matching before fuzzy correlation** — Fuzzy matching can silently merge unrelated cases. The cost is occasional duplicate cases for the same underlying issue. That is a manageable operator burden; invisible case merges are not.

**Separate monitoring process over inline alerting** — Inline alerting creates coupling between the monitoring system and the system being monitored. Separation keeps the failure modes isolated.

**Narrow signal coverage over broad instrumentation** — Broad instrumentation creates alert noise that operators learn to ignore. High-confidence signals on a narrow surface are more useful than comprehensive coverage that no one trusts.

---

## 16. Open Questions and Current Leanings

1. **Should deployment logs be the primary Phase 2 source, or only a startup-crash safety net?** Current leaning: use deployment logs narrowly for startup crashes and obvious runtime failures, then move toward structured app and worker signals. Deployment logs are useful for coverage but too noisy to become the primary long-term signal source.

2. **Which structured signal should come first: application errors, worker failures, or database reliability?** Current leaning: application errors first, because they are closest to user-visible production failures and can produce cleaner case evidence than platform logs.

3. **How much case lifecycle is needed before adding an operator UI?** Current leaning: keep lifecycle minimal until repeated friction appears in the manual workflow. The trigger for adding a UI is operational drag in resolving, reviewing, or closing cases, not a feature roadmap milestone. The initial lifecycle of open → resolved → closed is enough until manual operation shows that notes, filtering, case views, or assignment would materially improve the operator workflow.

4. **Are diagnosis packs enough before LLM synthesis?** Current leaning: yes. Diagnosis packs should exist before LLM synthesis so that any AI interpretation is grounded in deterministic evidence rather than raw, scattered logs.

5. **When should BugOps integrate directly with a coding agent?** Current leaning: only after case reports and diagnosis packs consistently produce enough context for a human operator to begin debugging. Agent handoff should follow proven human handoff.

6. **Should fix brief generation be part of BugOps or a separate tooling track?** Current leaning: BugOps should own the evidence and case context; fix brief generation can be a downstream capability once the evidence model is stable.

---

## 17. Product Principle

BugOps should not try to be smart before it is useful.

The order is:

1. detect real signals
2. preserve evidence
3. create cases
4. notify the operator
5. make cases actionable
6. support fixes
7. validate resolution

Deterministic evidence comes first. LLM synthesis comes later. Automation comes after manual workflow friction is understood.
