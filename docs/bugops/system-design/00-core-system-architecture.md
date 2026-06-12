# BugOps Core System Architecture

---

## Purpose

This document defines the permanent architecture of BugOps. It records decisions that are expensive to reverse. It is not a sprint plan or implementation blueprint.

---

## What Is BugOps

BugOps is an incident management and investigation system for Backdrop. It monitors production health, detects failures, collects evidence, generates investigations, and produces structured implementation work for human review and coding-agent execution.

BugOps does not remediate failures autonomously. BugOps does not manage implementation workflow, sprint planning, or task tracking.

BugOps owns:

```
Production Signals → Operational Context → Actionable Work
```

BugOps does not own: log storage, notification delivery infrastructure, deployment systems, project management, or source system execution.

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

---

## Architectural Non-Goals

BugOps is not a log management platform, a project management platform, a ticket management platform, a workflow engine, a dashboard platform, a replacement for Sentry, or a replacement for PagerDuty.

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

This is the end-state lifecycle. Individual sprints may implement a smaller subset of states until the later pipeline stages exist. Sprint 018 currently implements open, resolved, and closed.

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
- **Invariant:** evidence collection is deterministic and produces a durable artifact

### Seam 2: Evidence Pack → Investigation

- **Input:** completed Evidence Pack
- **Output:** Investigation attached to the BugCase
- **Owner:** InvestigationProvider
- **Trigger:** Evidence Pack completion, subject to cost controls and eligibility rules
- **Invariant:** Investigation interprets evidence. It does not replace evidence. The Evidence Pack remains inspectable independently.

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

**Sprint 021:** Evidence Pack model, EvidenceCollector, InvestigationProvider, Investigator Agent.

**Sprint 022:** TicketWriter, TicketExporter, ValidationRunner, human approval workflow, coding-agent handoff format.
