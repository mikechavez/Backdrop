# BugOps v2 Product Spec

## Product Summary

BugOps is an incident management and investigation system for Backdrop that turns production failures into investigation-ready bug tickets.

It monitors production health and runtime failures, groups related signals into incidents, gathers evidence automatically, generates investigations, and produces structured tickets for implementation through coding agents (e.g. Claude Code, Codex, or future coding agents).

The goal is not autonomous remediation.

The goal is to eliminate manual monitoring and context reconstruction so production failures become immediately visible, understandable, and actionable.

---

# Problem

Today production failures are discovered manually.

Example:

Scheduler failure
→ Articles stop ingesting
→ Signals stop generating
→ Narratives become stale
→ Briefings stop publishing

The operator often discovers the issue days later.

Even after discovering the issue, investigation requires reconstructing context across:

- Railway logs
- MongoDB
- Worker status
- Scheduler status
- Deploy history
- Historical incidents

The reconstruction step often takes longer than fixing the bug.

---

# Product Goal

Transform:

Production Failure
→ Manual Discovery
→ Manual Investigation
→ Manual Ticket Creation
→ Fix

Into:

Production Failure
→ Automatic Detection
→ Incident
→ Investigation
→ Ticket
→ Human Approval
→ Coding Agent
→ Validation

---

# Product Principles

1. Evidence before interpretation
2. Context before conclusions
3. Deterministic systems before LLM reasoning
4. Humans approve code changes
5. Preserve evidence before it disappears
6. Incidents before tickets
7. Cost awareness by default

---

# Core Concepts

## Signal

A single observation.

Examples:

- Articles stale
- Briefing stale
- Worker crash
- ImportError
- Mongo timeout

Signals are not operator-facing.

## Incident

The primary operational object in BugOps.

An incident represents a production problem and may contain multiple signals.

## Incident Data Model

Each incident contains:

- incident_id
- severity
- status
- root_subsystem
- primary_signal
- first_seen_at
- last_seen_at
- blast_radius
- confidence
- correlation_reason

### Root Subsystem

The subsystem believed to be closest to the originating failure.

### Blast Radius

The set of downstream subsystems impacted by the incident.

### Correlation Reason

Records why signals were grouped into the same incident.

Purpose:

Incidents must explain why they exist, why signals were grouped, and why severity was assigned.

## Evidence Pack

Automatically collected context attached to an incident.

Contains:

- timestamps
- logs
- metrics
- deploy history
- runtime failures
- related incidents

## Investigation

A durable analysis object attached to an incident.

Contains:

- evidence summary
- likely subsystem
- possible causes
- verification steps
- unknowns

Investigations persist after raw evidence expires.

## Ticket

Implementation work generated from an investigation.

One incident may generate:

- zero tickets
- one ticket
- many tickets

Tickets are export artifacts generated from investigations. BugOps does not manage implementation workflow, sprint planning, or task tracking.

---

# Architecture

Signal Sources
→ Signal Events
→ Incident Correlator
→ Incident
→ State Change Events
→ Notification Subscriber

Incident
→ Evidence Pack
→ Investigation
→ Ticket(s)
→ Human Approval
→ Coding Agent
→ Validation
→ Resolved / Reopened

---

# Severity Model

Severity is assigned deterministically at detection time and may be escalated as impact grows.

### Critical

- Scheduler unavailable
- Worker unavailable
- Database unavailable
- Multiple critical subsystems degraded

### High

- Article ingestion stalled
- Briefing generation stalled
- Narrative refresh stalled

### Medium

- Repeated runtime exceptions
- Partial subsystem degradation

### Low

- Single runtime exception
- Non-impacting failures

Incident severity is derived from its signals and observed impact.

---

# Incident Lifecycle

Open
→ Notified
→ Investigating
→ Ticket Generated
→ Human Approval
→ Fix In Progress
→ Validating
→ Resolved

Possible transition:

Resolved
→ Reopened

Operator actions:

- acknowledge
- mute
- snooze
- close
- reopen

## Reopen Escalation

Track:

- reopen_count
- validation_failures

Rules:

- incidents may reopen automatically after failed validation
- repeated reopen cycles increase incident visibility
- after a configurable threshold, incidents require manual operator review

---

# Notification Layer

Notifications subscribe to incident state changes.

Events:

- incident_created
- incident_reopened
- ticket_ready
- validation_failed

Routing:

- Critical → Immediate Slack
- High → Slack
- Medium → Digest
- Low → Stored only

Additional rules:

- deduplicate repeated notifications
- throttle repeated alerts
- notify again only if severity increases, a new subsystem joins the blast radius, or the incident reopens

---

# Signal Sources

## Outcome Signals

### ArticleFreshnessSignalSource

Detects stale article ingestion.

### SignalFreshnessSignalSource

Detects stalled signal generation.

### NarrativeFreshnessSignalSource

Detects stale narratives.

### BriefingFreshnessSignalSource

Detects missing briefings.

### Freshness Baseline Rules

Successful RSS fetches with zero new content are not automatically failures.

Freshness signals evaluate:

- historical source activity
- expected publishing frequency
- time-of-day patterns
- multi-source behavior

## Runtime Signals

### RuntimeErrorSignalSource

Captures:

- exception type
- message
- stack trace
- service

Requirements:

- redaction on write
- fingerprinting
- aggregation

### WorkerFailureSignalSource

Detects:

- worker unavailable
- crash loops
- heartbeat failures

### SchedulerFailureSignalSource

Detects:

- scheduler unavailable
- missed scheduled execution

### DatabaseFailureSignalSource

Detects:

- Mongo failures
- timeout storms

### CostAnomalySignalSource

Detects:

- spend spikes
- abnormal Mongo activity
- unexpected token consumption
- gateway attribution gaps
- LLM routing bypasses

---

# Dependency Graph

scheduler
→ ingestion
→ articles
→ signals
→ narratives
→ briefings

---

# Incident Correlation

Sprint 020 uses deterministic correlation.

A signal joins an existing incident if:

- same fingerprint
- same subsystem
- downstream of an open incident subsystem
- within correlation window

Otherwise create a new incident.

LLM-based correlation is out of scope.

---

# Auto Resolution

Incidents resolve automatically when outcome recovery remains stable for a validation window.

Recovery is based on restored system outcomes, not component liveness.

Examples:

Worker healthy
→ not sufficient

Scheduler healthy
→ not sufficient

Articles flowing again
→ valid recovery signal

Signals generating again
→ valid recovery signal

Narratives refreshing again
→ valid recovery signal

Briefings publishing again
→ valid recovery signal

Manual close remains available.

Resolved incidents may reopen if recovery conditions fail.

---

# Evidence Pack

Generated after a settling window.

Rules:

- wait 10–15 minutes
- or run immediately when a critical runtime signal appears

Purpose:

Allow root-cause evidence to arrive before investigation.

---

# Investigation

Investigator Agent inputs:

- incident
- evidence pack

Outputs:

- likely subsystem
- possible causes
- alternative hypotheses
- confidence
- verification steps
- evidence references

Rules:

- one investigation per incident
- rerun only after material evidence change

---

# Ticket Generation

Ticket Writer outputs:

- title
- severity
- impact
- evidence
- likely subsystem
- verification steps
- acceptance criteria
- validation steps

Designed for coding-agent consumption.

---

# Validation

Validation evaluates:

- outcome recovery
- subsystem health
- regression detection
- recovery stability

Possible outcomes:

- resolved
- reopened
- manual review required

---

# Monitoring the Monitor

BugOps publishes an external heartbeat.

Heartbeat alerts must not depend on BugOps infrastructure.

BugOps must also monitor the health of its own detectors and signal sources.

---

# Cost Controls

Rules:

- no LLM per signal
- no LLM per exception
- no LLM over raw logs
- one investigation per incident
- rerun only after material evidence change

Evidence collection is deterministic.

BugOps LLM usage must route through the existing unified gateway for attribution and budget enforcement.

---

# Retention Policy

- runtime_error_events: 30 days
- raw evidence: 90 days
- incidents: permanent
- investigations: permanent

---

# Deploy Suppression

Maintenance mode supports:

- notification suppression
- deploy suppression windows

Suppressed incidents continue to be recorded.

Rules:

- suppression affects notification behavior only
- incidents remain visible
- suppression expires automatically
- unresolved incidents may notify after suppression ends

---

# Sprint 020: Failure Visibility

## Goal

Failure
→ Incident
→ Alert

## Deliverables

- dead man's switch
- check loop
- outcome freshness signals
- runtime failure signals
- cost anomaly signals
- incident model
- incident lifecycle
- auto resolution
- manual close/mute
- deterministic severity
- dependency graph
- incident correlation
- notification layer
- runtime aggregation
- redaction on write
- deploy suppression
- retention policy

## Success Criteria

- production failures become incidents automatically
- operators are notified automatically
- incidents resolve automatically when healthy
- no manual monitoring required

---

# Sprint 021: Evidence & Investigation

## Goal

Incident
→ Evidence Pack
→ Investigation

## Deliverables

- evidence pack model
- deployment capture
- worker/scheduler state capture
- runtime error summaries
- related incident lookup
- graph-scoped evidence collection
- investigation model
- investigator agent

---

# Sprint 022: Ticket Factory & Validation

## Goal

Investigation
→ Ticket
→ Human Approval
→ Coding Agent
→ Validation

## Deliverables

- ticket writer
- coding-agent handoff format
- acceptance criteria
- validation checklist
- recovery validation
- reopen logic
- post-fix summary

---

# Future Considerations

- recurring incident detection
- historical fix retrieval
- operational intelligence
- advanced correlation strategies
