# BugOps Core System Architecture

---

## Purpose

This document defines the permanent architecture of BugOps. It records decisions that are expensive to reverse. It is not a sprint plan or implementation blueprint.

---

## What Is BugOps

BugOps is an incident management and investigation system for Backdrop. It monitors production health, detects failures, collects evidence, generates triage investigations, and produces structured implementation work for human review and coding-agent execution.

BugOps does not remediate failures autonomously. BugOps does not manage implementation workflow, sprint planning, or task tracking.

BugOps owns:

```
Production Signals → Operational Context → Actionable Work
```

BugOps does not own: log storage, notification delivery infrastructure, deployment systems, project management, or source system execution.

---

## What BugOps Is Becoming

BugOps is a closed-loop operational learning system. Detection, evidence, triage, and validation are not independent features — they are stages in a single feedback loop that improves over time.

The pipeline:

```
Failure
→ Evidence
→ Triage
→ Ticket
→ Validation
→ Learning
```

Each stage produces a durable artifact. The accumulation of those artifacts — Evidence Packs, Investigations, Tickets, Validation Results — is the system's long-term asset. Individual investigations are today's opinion. The corpus is permanent institutional memory.

---

## Architecture Principles

These principles are permanent. They function as tiebreakers for future design decisions.

1. Deterministic before LLM
2. Evidence before interpretation
3. Outcome monitoring before component monitoring
4. Operational cases before tickets
5. Human approval before code changes
6. False positives are worse than slower detection
7. Absence of output is not failure unless output was expected
8. Existing infrastructure before new infrastructure
9. Evidence Packs may be partial, but they must never be ambiguous
10. No claim without evidence reference
11. Investigations are triage artifacts, not root-cause determinations. Their purpose is to reduce time-to-understanding and time-to-fix.

---

## Architectural Non-Goals

BugOps is not a log management platform, a project management platform, a ticket management platform, a workflow engine, a dashboard platform, a replacement for Sentry, or a replacement for PagerDuty.

BugOps does not perform root-cause analysis. It performs operational triage: identifying likely causes, prioritizing investigation steps, reducing the search space, and pointing toward fix areas.

---

## Top-Level Object

BugCase is the single operational container in BugOps.

A BugCase represents a production problem requiring investigation and potential remediation. Architecturally, BugCase fulfills the role commonly referred to in other systems as an incident.

BugOps does not introduce a separate Incident object. There is no two-tier Signal → Incident → Case model. One container exists. It grows over time.

BugCase may be renamed in the future if terminology becomes a meaningful constraint. That is a terminology decision, not an architecture decision.

---

## End-State Lifecycle

```
Signal
→ BugCase
→ Evidence Pack
→ Investigation
→ Ticket Draft
→ Human Approval
→ Coding Agent Handoff
→ Validation
→ Resolved
```

BugCase lifecycle states:

```
Open → Notified → Investigating → Ticket Generated → Human Approval → Fix In Progress → Validating → Resolved
```

This is the end-state lifecycle. Individual sprints may implement a smaller subset of states until the later pipeline stages exist.

Operator actions: acknowledge, mute, snooze, close, reopen.

Resolved cases may reopen if recovery conditions fail after resolution.

---

## Dependency Graph

BugOps owns a single hand-maintained DependencyGraph. It is the authoritative operational dependency map for outcome freshness detection, cascade suppression, blast radius, and investigation context.

The graph represents operational outcome dependencies, not service topology. It is not a full architecture map of every service, worker, queue, or collection.

The graph is deterministic and version-controlled. It is not inferred dynamically.

First version:

```
scheduler → ingestion → articles → signals → narratives → briefings
```

The graph supports two traversal directions:

**Upstream traversal** is used for cascade suppression. If a downstream detector fires while an upstream BugCase is already open, the downstream signal attaches to the upstream BugCase instead of creating a new one.

**Downstream traversal** is used for blast radius. If a BugCase originates at ingestion, the potential blast radius includes articles, signals, narratives, and briefings.

DependencyGraph is a shared architecture primitive. It is not an extension seam and is not pluggable. It evolves through deliberate versioning.

---

## BugCase Data Model

Each BugCase contains:

- `bugcase_id`
- `severity`
- `status`
- `dedupe_key`
- `root_subsystem`
- `affected_subsystems`
- `first_seen_at`
- `last_seen_at`
- `observation_count`
- `blast_radius`
- `recovery_candidate_at`
- `resolution_type`
- `confidence` *(optional — meaningful only when richer correlation exists)*
- `correlation_reason` *(optional — meaningful only when richer correlation exists)*

**root_subsystem** is the subsystem believed closest to the originating failure.

**affected_subsystems** is the set of downstream subsystems impacted by the BugCase.

**correlation_reason** records why signals were grouped into this BugCase. Optional until richer correlation logic exists. Do not invent values in deterministic-only sprints.

**confidence** records estimated certainty of root cause attribution. Optional until richer correlation logic exists. Do not invent values in deterministic-only sprints.

**recovery_candidate_at** records when recovery was first observed. It is internal metadata, not an operator-facing state.

**resolution_type** records how a BugCase was ultimately resolved. Supports future learning and threshold tuning. Possible values: `real_issue`, `false_positive`, `duplicate`, `operator_error`, `expected_idle`. Not required in Sprint 020.

---

## Severity Model

Severity is assigned deterministically at detection time and may be escalated as impact grows.

**Critical:** scheduler unavailable, worker unavailable, database unavailable, multiple critical subsystems degraded.

**High:** article ingestion stalled, briefing generation stalled, narrative refresh stalled.

**Medium:** repeated runtime exceptions, partial subsystem degradation.

**Low:** single runtime exception, non-impacting failures.

---

## Cascade Suppression

BugOps implements deterministic upstream-wins cascade suppression.

When a detector fires, BugOps checks for open BugCases associated with upstream dependency nodes using the DependencyGraph.

If an upstream BugCase exists: the signal is attached to the upstream BugCase, `affected_subsystems` metadata is updated, no new BugCase is created, and no new Slack notification is sent.

If no upstream BugCase exists: normal idempotency rules apply.

Sprint 020 does not implement retroactive case merging, absorption, or root-cause reassignment. Those capabilities are deferred.

---

## Idempotency

Freshness detectors use stable dedupe keys in the format:

```
detector_type:root_subsystem
```

Examples: `article_freshness:articles`, `signal_freshness:signals`, `narrative_freshness:narratives`, `briefing_freshness:briefings`.

Dedupe is evaluated only against open BugCases. Resolved or closed cases with the same dedupe key do not suppress new cases.

If an open BugCase exists with the same dedupe key, BugOps attaches the new observation, updates `last_seen_at` and `observation_count`, and sends no new notification.

Processing order:

1. Check for open upstream BugCase. Attach if found.
2. Check for open BugCase with same dedupe key. Attach if found.
3. Otherwise create new BugCase and notify.

---

## Time Authority

BugOps uses internal persistence timestamps as the authoritative measure of system activity.

For most artifacts, this means `inserted_at`: the moment an artifact was successfully persisted to the database.

`published_at` is never authoritative for freshness decisions. It is an external timestamp and cannot be trusted.

`fetched_at` may be used as diagnostic context but is not the primary freshness signal.

`detected_at` records when BugOps observed a condition. It is used for BugOps case metadata, not source freshness.

All freshness comparisons include a configurable clock tolerance buffer to avoid boundary-condition false positives. Default: 60 seconds.

---

## Idle vs Broken Detection

Absence of output is only a failure when there is positive evidence that output was expected. This is one of the primary false-positive controls in BugOps and is elevated as a permanent architecture principle.

The rule is not:
```
no output → failure
```

The rule is:
```
expected output + no output → failure
```

Each freshness detector must explicitly define:

- last successful output
- expected input or activity
- failure condition
- legitimate idle condition
- recovery condition

---

## Recovery Model

BugOps defines recovery based on outcome recovery, not component health.

A subsystem is considered recovered when the expected artifact is being successfully produced again, measured by the same freshness authority used for failure detection.

Recovery is not immediate. After a healthy signal is observed, the BugCase enters a recovery-candidate period tracked by `recovery_candidate_at`. The subsystem must remain healthy for a configurable Recovery Window before automatic resolution occurs.

Recovery Window duration is configuration, not architecture.

BugCase resolves as a unit. Partial resolution is not supported. Individual `affected_subsystems` recovery is tracked as metadata but does not close the case.

---

## Pipeline Seams

BugOps produces a durable artifact at every major pipeline stage. Each artifact persists independently. Artifacts remain attached to the BugCase after the BugCase resolves or closes. Raw evidence may expire according to retention policy, but durable summaries and references remain.

### Seam 1: BugCase → Evidence Pack

- **Input:** eligible open BugCase
- **Output:** Evidence Pack attached to the BugCase
- **Owner:** EvidenceCollector
- **Trigger:** configurable settling window after BugCase creation, or immediate collection for critical runtime failures
- **Invariant:** evidence collection is deterministic and produces a durable artifact. Evidence Packs may be partial but must never be ambiguous. Missing sources are recorded explicitly with reason and timestamp.

### Seam 2: Evidence Pack → Investigation

- **Input:** completed Evidence Pack
- **Output:** Investigation attached to the BugCase
- **Owner:** InvestigationProvider
- **Trigger:** Evidence Pack completion, subject to cost controls and eligibility rules
- **Invariant:** Investigation interprets evidence. It does not replace evidence. The Evidence Pack remains inspectable independently. Every claim in an Investigation must reference a specific evidence item. Investigations are triage artifacts, not root-cause determinations.

### Seam 3: Investigation → Ticket Draft

- **Input:** completed Investigation
- **Output:** one or more Ticket Drafts
- **Owner:** TicketWriter
- **Trigger:** human promotion, or explicit automation rule
- **Invariant:** Ticket Drafts are proposed implementation work. They are not approved work. Human approval is required before coding-agent execution.

### Seam 4: Ticket Draft → Validation

- **Input:** approved Ticket Draft and implementation result
- **Output:** Validation Run
- **Owner:** ValidationRunner
- **Trigger:** human validation request, or coding-agent handoff completion report
- **Invariant:** Validation determines whether operational recovery is stable enough to resolve or reopen the BugCase.

---

## Investigation Consumer Hierarchy

Investigations serve two consumers in priority order.

**Primary consumer: Human operator**

Sections 1–7 of the Investigation are optimized for a human operator performing triage. The operator should be able to read sections 1–7 and know what to check next, in what order, without opening Railway, MongoDB, or any external tool.

**Secondary consumer: TicketWriter (coding agent)**

Sections 8–10 of the Investigation are optimized for TicketWriter consumption. These sections provide the probable fix areas, file guidance, and unknowns that allow TicketWriter to generate a self-contained Ticket Draft without re-reading the Evidence Pack.

This hierarchy is permanent. Optimizing sections 8–10 at the expense of sections 1–7 is an architecture violation.

---

## Investigation Structure

Every Investigation must contain these ten sections in order:

1. **Incident Summary** — what broke, when, and for how long
2. **Impact** — which subsystems and outputs are affected
3. **What Is Broken** — observed failure signals with evidence references
4. **What Is Not Broken** — confirmed healthy signals and what they eliminate
5. **Recent Changes** — deploy context, configuration changes, anything that changed near incident time
6. **Evidence Timeline** — chronological ordering of key observations
7. **Recommended Investigation Order** — ordered checklist with estimated time per step
8. **Hypotheses** — ranked by decision efficiency, each with supporting evidence, contradicting evidence, and evidence references
9. **Potential Fix Areas** — probable files, components, and do-not-modify zones
10. **Unknowns and Missing Evidence** — explicitly named gaps, not omitted

Sections 1–7 serve the human operator. Sections 8–10 serve the TicketWriter.

The recommended investigation order encodes triage strategy. Steps are ordered by time-to-confirm, not by confidence. The fastest check to perform comes first, regardless of prior probability.

---

## Investigation Quality Standard

**Success criterion:**

A person unfamiliar with the incident can reach the likely fix area substantially faster using the Investigation than without it.

**Automatic failure modes:**

1. **Unsupported claim** — any hypothesis asserted without an evidence reference. Unknown is allowed. Invented is not.

2. **Missed obvious evidence** — a conclusion that ignores a directly relevant data point present in the Evidence Pack. Example: asserting a scheduler hypothesis while deploy context shows a scheduler restart two minutes before failure without citing it.

3. **No actionable next step** — analysis that lists possible causes without providing an investigation order.

4. **Wrong subsystem** — pointing toward a component that healthy signals in the Evidence Pack eliminate as a primary cause.

An Investigation that fails any of these four checks is not a partial success. It is a failed Investigation.

---

## Failure Taxonomy

Investigations use a controlled vocabulary for failure classification. This vocabulary supports future corpus analysis.

```
scheduler_missed_execution
worker_execution_failure
database_unavailable
external_source_idle
deployment_regression
config_error
unknown
```

Additional categories may be added as the corpus reveals gaps. Do not expand this vocabulary without a documented reason.

---

## Evidence Pack Truncation Policy

When an Evidence Pack exceeds size limits, evidence sections are truncated in this order. Higher-priority sections are preserved first.

```
1. BugCase metadata              ← never truncated
2. Deterministic freshness metrics  ← never truncated
3. Health and system state       ← never truncated
4. Recent deploy context         ← never truncated
5. Collection errors             ← never truncated
6. Related BugCases              ← truncated last among structured data
7. Log excerpts                  ← truncated first
```

Logs are trimmed before any structured evidence is removed. Structured evidence is compact and high-signal. Logs are noisy and large.

When truncation occurs, it must be recorded explicitly:

```
lines_fetched: 347
lines_stored: 200
truncated: true
```

---

## Closed-Loop Learning

BugOps accumulates a corpus of operational knowledge as a side effect of normal operation:

```
BugCase
→ Evidence Pack
→ Investigation
→ Ticket
→ Validation Result
```

This corpus is the long-term strategic asset of BugOps. It enables future capabilities including investigation quality improvement, threshold tuning, retrieval-augmented investigation, hypothesis accuracy measurement, and identification of recurring failure patterns.

No Sprint 021 or Sprint 022 feature requires the corpus directly. The corpus is built correctly by building Sprint 021 and Sprint 022 correctly. Preserve it by making every artifact durable and every outcome recorded.

---

## Extension Seams

The following components are intentionally replaceable. Each defines an interface contract. Implementations may change without rewriting the core pipeline.

- **SignalSource** — adds new detectors without changing the monitor loop.
- **EvidenceCollector** — collects evidence for a BugCase. Can evolve from simple deterministic snapshots to richer context gathering.
- **InvestigationProvider** — turns Evidence Packs into Investigations. Can swap models, prompts, retrieval strategies, or deterministic modes.
- **TicketWriter** — turns Investigations into Ticket Drafts. Owns content generation.
- **TicketExporter** — exports approved Ticket Drafts to an external workflow. Decoupled from content generation. Current implementation: repository markdown. Future: GitHub, Linear, or other targets.
- **NotificationChannel** — sends operator-facing updates. Current implementation: Slack.
- **ValidationRunner** — checks recovery or post-fix outcome. Expected to evolve significantly.

---

## Monitoring Topology

BugOps runs as a separate process, independent from FastAPI, Celery Worker, and Celery Beat. This is a Sprint 018 architectural decision.

Each SignalSource runs independently inside the BugOps polling loop. A failure in one detector logs the error, records the failed detector run, and does not stop the monitor or prevent other detectors from running.

Detector execution is observable through structured logs or lightweight run records including: `detector_name`, `run_started_at`, `run_completed_at`, `status`, `error_type`, `error_message`, `duration_ms`.

BugOps should eventually publish a heartbeat to infrastructure outside the BugOps process. If the heartbeat stops, an external mechanism alerts the operator. This protects against BugOps silently failing. External heartbeat implementation is deferred.

---

## Cost Controls

No LLM call per signal. No LLM call per exception. No LLM over raw logs. One investigation per BugCase. Investigations rerun only after material evidence change.

Evidence collection is deterministic.

All BugOps LLM usage routes through the existing unified gateway for cost attribution and budget enforcement.

---

## Retention Policy

The following represents the initial default retention policy. It is not immutable architecture and may be updated as operational needs evolve.

| Artifact | Retention |
|---|---|
| runtime_error_events | 30 days |
| raw evidence | 90 days |
| BugCases | permanent |
| Investigations | permanent |

---

## Evolution

**Sprint 018:** SignalSource interface, BugCase, BugAlertEvent, Slack notifications, deterministic reports, separate monitor process.

**Sprint 020:** outcome freshness signals, dependency graph, cascade suppression, idempotency, auto-resolution, detector isolation, notification behavior, deploy suppression.

**Sprint 021:** Evidence Pack model, EvidenceCollector, InvestigationProvider, Investigator Agent, Railway log integration, Configuration Evidence collector.

**Sprint 022:** TicketWriter, TicketExporter, ValidationRunner, human approval workflow, coding-agent handoff format.
