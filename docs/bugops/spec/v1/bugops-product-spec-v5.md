# Product Spec: BugOps

---

**Note:** This is a real product spec for a production feature I built inside Backdrop, a multi-service AI pipeline I developed and operate independently.

The primary user is an internal operator persona: the person responsible for keeping the system reliable in production. In the current implementation, I am that operator, which created an unusually tight feedback loop between observing production incidents, identifying workflow friction, and shipping improvements.

I chose this spec because it reflects how I approach product development: start with a real operational problem, define a narrow first version, establish clear trust boundaries, and expand automation only after the manual workflow is understood.

The system described here is running in production.

---

---

## 1. Product Summary

BugOps helps an operator understand production bugs faster.

It watches for meaningful production issues, turns them into bug cases, preserves the evidence, and alerts the operator when there is something new to investigate.

Instead of starting from scattered logs, traces, database records, deployment history, and recent code changes, the operator starts from a case report that shows what happened, where the signal came from, what metrics were observed, and what to check next.

The operational goal is to reduce the time required to understand a meaningful production issue from 30–60 minutes to under 10 minutes.

The product goal is to let one operator safely manage more production surface area without spending more time reconstructing what happened.

BugOps starts with deterministic signal detection and manual operator control. It does not start with autonomous remediation, LLM diagnosis, or automatic code changes.

**Status: The first end-to-end path is implemented and running in production.**

Initial production path:

```text
llm_traces → bug_alert_event → bug_case → optional alert → deterministic report
```

---

## 2. User and Problem

### Primary User

The primary user is the production operator responsible for keeping the system reliable in production.

Their job is not simply to fix bugs. Their job is to know whether the system is healthy, identify meaningful failures, preserve enough evidence to understand them, coordinate fixes, and verify that production behavior has actually improved afterward.

In the current implementation, I am this operator.

### Problem

Backdrop is a production AI pipeline with multiple moving parts: FastAPI backend, Celery workers, Redis, MongoDB, cloud deployment, frontend, LLM gateway, trace logging, cost controls, scheduled processing, and generation pipelines.

When something breaks, the operator must reconstruct context before debugging can begin.

The evidence needed to understand a production incident is often scattered across deployment logs, MongoDB records, LLM traces, service logs, test results, implementation summaries, and recent code changes. Reconstructing that context is slow, repetitive, and error-prone, especially when production behavior differs from local validation.

The problem is not simply identifying that a failure occurred. The problem is preserving enough evidence to understand what happened before that evidence disappears.

Recent production incidents exposed this gap:

- a disabled service path still tried to start parts of the system it should have skipped
- a database access pattern worked in one environment but failed in production
- code that passed local validation broke when deployed because production resolved imports and runtime paths differently
- production checks surfaced issues that local tests had missed

In each case, the failure itself was only part of the work. The larger burden was reconstructing the context required to investigate it.

### Before BugOps

The operator manually checked deployment logs, LLM traces, MongoDB, service logs, and recent code changes, often spending 30–60 minutes reconstructing what happened.

### After BugOps

A case notification arrives when a meaningful new issue is detected. The operator opens the deterministic report and sees the alert event, observed metrics, source metadata, alert history, and suggested manual checks.

Investigation starts with preserved evidence instead of context reconstruction.

### Validation Beyond the Current Operator

The initial version benefits from an unusually tight feedback loop because the builder and operator are currently the same person. This accelerated iteration and made it possible to validate the core workflow against real production incidents, but it also limits external validation.

The next validation step is to conduct structured interviews with other AI system operators and builders about recent production incidents, compare their debugging workflows against the BugOps case model, and evaluate whether the preserved evidence would have been sufficient to begin investigation.

The goal is to validate the underlying product assumption: that preserving evidence and normalizing incidents into durable cases reduces context reconstruction for operators who did not build the system themselves.

### Secondary Future Users

- AI coding agent
- reviewing agent
- future maintainers
- product and engineering collaborators

### Current User Needs

- know when production has a meaningful issue
- avoid manually watching logs
- distinguish real issues from noise
- preserve evidence before it disappears
- know what to check next
- avoid duplicate investigation of the same issue
- eventually hand clean bug context to a coding agent

---

## 3. Why This Matters for AI Systems

Production AI systems do not only fail through crashes. They also fail through degradation.

Outputs become less grounded. Costs drift upward. Generated summaries stop passing validation. Evidence stops flowing into downstream generation steps. The system may still be running, but the quality or reliability of its output has changed.

That creates a different operating problem from traditional monitoring. By the time the failure is obvious, the evidence needed to understand it may already be gone.

AI systems also carry a specific trust risk: generated artifacts can become inputs to later generation. If degraded output quietly propagates through the pipeline, the system can compound the error instead of surfacing it.

BugOps is designed around that reality. It treats production signals as evidence, not just alerts. It preserves deterministic facts before they disappear, keeps those facts separate from LLM interpretation, and keeps humans in control of diagnosis and resolution until the system has earned more automation.

The same pattern applies to any AI-native product operating at scale: evidence first, trust boundaries enforced, automation only after the manual workflow is understood.

---

## 4. Current State

The first end-to-end BugOps workflow is implemented and running in production.

The current version validates the core product assumption: a production signal can be detected, normalized into an alert event, grouped into a durable case, sent as a one-way notification, and turned into a deterministic report without using an LLM in the alert path.

Current production path:

```text
llm_traces signal
→ normalized bug_alert_event
→ bug_case
→ one-way alert for new cases only
→ deterministic report
```

What is currently implemented:

- BugOps service
- SignalSource seam
- LLMTraceCostSignalSource
- BugAlertEvent model
- BugCase model
- BugOpsStore
- alert-to-case flow using dedupe_key
- one-way notifications
- deterministic case report
- persisted heartbeat

Current behavior:

- BugOps currently watches LLM trace data for cost runaway patterns.
- When it finds a matching signal, it creates a normalized alert event.
- If there is no open case with the same dedupe key, it creates a new bug case and sends a notification.
- If there is already an open case with the same dedupe key, it attaches the new alert to that case and does not send another notification.
- Case grouping is exact-match only. There is no fuzzy matching, LLM matching, or multi-source correlation yet.
- Reports are deterministic only. They summarize stored facts and do not include LLM synthesis or unsupported root-cause claims.

What remains unproven:

- whether the same case model works across runtime errors, worker failures, database failures, and deployment failures
- whether diagnosis packs reduce investigation time beyond the first signal source
- whether another operator could use the preserved evidence without needing the builder’s context
- when the workflow has enough repeated friction to justify an operator UI

---

## 5. Example Case

A cost runaway pattern appears in LLM trace data for a specific operation.

Before BugOps, the operator would need to inspect traces, logs, deployment history, database records, and recent code changes to understand whether the issue was real, repeated, and worth investigating.

With BugOps, the signal is turned into a normalized alert event with observed metrics, source metadata, severity, and a deterministic dedupe key used to group repeat alerts for the same issue.

BugOps checks whether an open case already exists for that dedupe key.

If no matching case exists, BugOps creates a new case and sends a notification. If a matching case already exists, BugOps attaches the alert to that case and does not send another notification.

The operator opens the deterministic report and sees:

- what signal was detected
- which operation was affected
- what metrics were observed
- when the issue first appeared
- whether related alerts have already been attached
- what manual checks to run next

The operator starts investigation from a preserved evidence bundle instead of manually reconstructing context from scattered systems.

---

## 6. Goals

### Core Goals

1. Detect production signals that indicate real operational issues.
2. Normalize raw signals into structured bug alert events.
3. Group related alerts into durable bug cases.
4. Notify the operator only when a new case is created.
5. Preserve deterministic evidence for investigation.
6. Generate deterministic case reports.
7. Keep humans in control of diagnosis, fixing, and closing cases.
8. Expand signal coverage over time based on real production operating experience.

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

---

## 10. Non-Functional Requirements

**Reliability** — Source failure, notification failure, and individual bad alerts must not crash the monitor or block future polling.

**Cost** — No LLM in critical path. Configurable poll interval. Minimal memory footprint. Single replica.

**Safety** — BugOps writes only to its own collections. Does not write to production pipeline collections.

**Observability** — Startup logs, enabled/disabled state logs, poll-complete logs, source error logs, notification success/failure logs, persisted heartbeat.

**Maintainability** — New signal sources plug into the SignalSource seam without changing the core alert-to-case flow.

---

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

---

## 12. Roadmap

**Phase 1 — Prove the Core Workflow**  
Status: Done.

Prove that BugOps can detect a real production signal, normalize it into an alert event, group it into a durable case, notify the operator, and generate a deterministic report.

**Phase 2 — Make the Workflow Reliable Enough to Trust**  
Add heartbeat logs, persisted heartbeat status, startup noise cleanup, notification validation, idempotency guardrails, runtime failure detection, and an operator runbook.

**Phase 3 — Make Investigation Easier**  
Build diagnosis packs that collect related traces, logs, known facts, unknowns, and suggested checks. Add the minimal case lifecycle needed to support real operation: list open cases, view report, resolve, close, add note, and attach validation evidence.

**Phase 4 — Expand Automation Responsibly**  
Add LLM synthesis only after the deterministic evidence layer is reliable. Use synthesis to summarize diagnosis packs, suggest hypotheses, cite evidence, and label uncertainty. Once human handoff works reliably, turn cases into agent-ready fix briefs and support post-fix validation.

---

## 13. Success Metrics

### Primary Outcome

Increase the amount of production surface area one operator can safely manage.

Reducing reconstruction time is the operational metric. The business outcome it enables is operational leverage: an operator who spends 30–60 minutes reconstructing context for every meaningful incident cannot safely take on additional systems, hand off debugging work, or delegate implementation to a coding agent.

BugOps exists to make production issues legible enough that investigation can begin from preserved evidence rather than manual context reconstruction.

### Primary Metric

Reduce the time required to understand a meaningful production issue from an estimated 30–60 minutes to under 10 minutes.

A production issue is considered understood when the operator has enough evidence to form a credible explanation of what happened and identify the next investigation step.

### Measurement Plan

For each meaningful production issue, record:

- time from first production signal to operator awareness
- time from awareness to first credible understanding of the issue
- whether the case preserved enough evidence to begin investigation immediately
- whether the alert was useful, noisy, duplicate, or missing key context
- whether investigation required significant manual log, trace, or database exploration outside the case report
- whether the case could be handed to another human or coding agent with enough context to continue investigation

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

The goal is not only to save time during incidents.

The goal is to make production operations legible enough to review, hand off, and scale.

Success means operators can manage more system complexity, collaborate more effectively, and eventually delegate portions of investigation and implementation without losing confidence in the underlying evidence.

---

## 14. Risks

**BugOps becomes too broad** — Add signal sources incrementally; do not build a full observability platform.

**Alert noise** — Start with narrow, high-confidence patterns; notify only on new cases.

**LLM hallucination** — Keep deterministic facts separate from LLM synthesis; do not add interpretation until diagnosis packs exist.

**Duplicate cases** — Deterministic dedupe_key logic and database-level guardrails.

**Log sources are messy** — Use deployment logs only for narrow runtime failure patterns; add structured app signals later.

**The system becomes more interesting than useful** — Only expand when real production operating experience justifies the next layer.

---

---

## 15. Tradeoffs

**Deterministic detection before LLM diagnosis** — A false root cause claim in an alert erodes trust in the whole system faster than a missing hypothesis. Evidence first; synthesis only after the deterministic layer is solid.

**Exact dedupe matching before fuzzy correlation** — Fuzzy matching can silently merge unrelated cases. The cost is occasional duplicate cases for the same underlying issue. That is a manageable operator burden; invisible case merges are not.

**Separate monitoring process over inline alerting** — Inline alerting creates coupling between the monitoring system and the system being monitored. Separation keeps the failure modes isolated.

**Narrow signal coverage over broad instrumentation** — Broad instrumentation creates alert noise that operators learn to ignore. High-confidence signals on a narrow surface are more useful than comprehensive coverage that no one trusts.

---

---

## 16. Open Questions and Current Leanings

1. **Should deployment logs be the primary Phase 2 source, or only a startup-crash safety net?**  
   Current leaning: use deployment logs narrowly for startup crashes and obvious runtime failures, then move toward structured app and worker signals. Deployment logs provide coverage, but they are too noisy to become the primary long-term signal source.

2. **Which structured signal should come first: application errors, worker failures, or database reliability?**  
   Current leaning: application errors first, because they are closest to user-visible production failures and can produce cleaner case evidence than platform logs.

3. **How much case lifecycle is needed before adding an operator UI?**  
   Current leaning: keep lifecycle minimal until repeated friction appears in the manual workflow. The trigger for adding a UI is operational drag in resolving, reviewing, or closing cases, not a feature roadmap milestone.

4. **Are diagnosis packs enough before LLM synthesis?**  
   Current leaning: yes. Diagnosis packs should exist before LLM synthesis so that any AI interpretation is grounded in deterministic evidence rather than raw, scattered logs.

5. **When should BugOps integrate directly with a coding agent?**  
   Current leaning: only after case reports and diagnosis packs consistently produce enough context for a human operator to begin debugging. Agent handoff should follow proven human handoff.

6. **Should fix brief generation be part of BugOps or a separate tooling track?**  
   Current leaning: BugOps should own the evidence and case context. Fix brief generation can be downstream once the evidence model is stable.

---

## 17. Product Principle

BugOps should not try to be smart before it is useful.

The principle is:

1. context before conclusions
2. evidence before interpretation
3. manual workflow before automation

That means BugOps should first make production failures legible. It should detect real signals, preserve the evidence, create durable cases, notify the operator, and make investigation easier.

Only after that workflow is reliable should BugOps add diagnosis, synthesis, agent handoff, or automated remediation.

The goal is not to make the system appear intelligent. The goal is to make production operations more trustworthy, reviewable, and scalable.
