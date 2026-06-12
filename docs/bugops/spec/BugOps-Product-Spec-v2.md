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

Tickets are implementation artifacts, not operational artifacts.

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
→ Coding Agent
→ Validation
→ Resolved / Reopened

---

# Severity Model

Severity is assigned deterministically at detection time.

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

Incident severity is derived from its signals.

---

# Incident Lifecycle

Open
→ Notified
→ Investigating
→ Ticket Generated
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

### No Input vs Failure Rule

Successful RSS fetch with zero new content is not a failure.

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

---

# Dependency Graph

Used for correlation and evidence scoping.

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

Incidents resolve automatically when conditions remain healthy for a stability window.

Example:

Worker healthy for 60 consecutive minutes
→ Resolve incident

Manual close remains available.

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

After implementation:

- articles resume
- signals resume
- narratives refresh
- briefings publish

Outcome:

- resolved
- reopened

---

# Monitoring the Monitor

BugOps publishes an external heartbeat.

Examples:

- Healthchecks.io
- UptimeRobot

Heartbeat alerts must not depend on BugOps infrastructure.

---

# Cost Controls

Rules:

- no LLM per signal
- no LLM per exception
- no LLM over raw logs
- one investigation per incident
- rerun only after material evidence change

Evidence collection is deterministic.

---

# Retention Policy

- runtime_error_events: 30 days
- raw evidence: 90 days
- incidents: permanent
- investigations: permanent

---

# Deploy Suppression

Maintenance mode supports:

- notification mute
- deploy suppression window

Purpose:

Prevent deploy-induced alert storms.

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
