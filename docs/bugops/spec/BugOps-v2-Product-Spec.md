# Product Spec: BugOps v2

## Product Summary

BugOps is an AI-assisted production operations system that turns production failures into actionable bug-bash tickets.

It continuously monitors both product outcomes and runtime failures, detects incidents, preserves investigation evidence, groups related signals into a single incident, and generates structured tickets that can be handed directly to Claude Code.

The goal is not autonomous remediation.

The goal is to eliminate manual monitoring and context reconstruction so production failures become immediately visible, understandable, and actionable.

---

## User

### Primary User

Production operator responsible for maintaining Backdrop.

Current implementation:

One operator (Mike).

### Future Users

- AI coding agents
- Future maintainers
- Engineering collaborators

---

## Problem

Today production failures are discovered manually.

Example:

Production failure
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
- Recent deployments
- Previous incidents

The reconstruction step often takes longer than fixing the bug.

---

## Product Goal

Transform:

Production Failure
→ Manual Discovery
→ Manual Investigation
→ Manual Ticket Creation
→ Fix

Into:

Production Failure
→ Automatic Detection
→ Automatic Evidence Collection
→ Automatic Ticket Creation
→ Claude Code Implementation
→ Validation

---

## Product Principles

1. Evidence before interpretation
2. Context before conclusions
3. Incidents before tickets
4. Humans approve code changes
5. Deterministic systems before LLM reasoning
6. Preserve evidence before it disappears

---

## Core Concepts

### Signal

A single observation.

Examples:

- No briefing in 24 hours
- Worker crash
- ImportError
- Mongo timeout

Signals are not operator-facing.

### Incident

An operator-facing representation of a production problem.

An incident may contain multiple signals.

Example:

Incident: Article Ingestion Failure

Signals:
- worker crash
- ImportError
- articles stale
- signals stale

### Evidence Pack

Automatically collected context attached to an incident.

Contains:

- timestamps
- logs
- metrics
- deploy history
- task status
- related signals
- related incidents

### Ticket

Structured work item generated from an incident.

Intended for:
- operator review
- Claude Code implementation

---

## Scope

### In Scope

#### Detection

Outcome monitoring:
- articles
- signals
- narratives
- briefings

Runtime monitoring:
- exceptions
- worker failures
- scheduler failures
- startup failures
- database failures

#### Investigation

- Evidence collection
- Failure localization
- Ticket generation

#### Validation

- Recovery verification
- Incident closure

### Out of Scope

- Autonomous code changes
- Autonomous deploys
- Autonomous merges
- Autonomous remediation
- General observability platform
- Datadog replacement

---

## System Architecture

Signal Sources
→ Signal Events
→ Incident Correlation
→ Incident
→ Evidence Pack
→ Investigator Agent
→ Ticket Writer Agent
→ Bug Ticket
→ Claude Code
→ Validation

---

## Signal Sources

### Outcome Signals

#### ArticleFreshnessSignalSource

Detect:
- No articles ingested within threshold

Default:
- 6 hours

#### SignalFreshnessSignalSource

Detect:
- No signals generated

Default:
- 12 hours

#### NarrativeFreshnessSignalSource

Detect:
- Narratives stale

Default:
- 24 hours

#### BriefingFreshnessSignalSource

Detect:
- No briefing published

Default:
- 24 hours

### Runtime Signals

#### RuntimeErrorSignalSource

Detect:
- Unhandled exceptions

Sources:
- FastAPI
- Workers
- Scheduler

Capture:
- exception type
- message
- stack trace
- service

#### WorkerFailureSignalSource

Detect:
- worker crash loops
- worker unavailable
- heartbeat missing

#### SchedulerFailureSignalSource

Detect:
- scheduler stopped
- scheduled jobs not executing

#### DatabaseFailureSignalSource

Detect:
- Mongo connection failures
- timeout storms

---

## Incident Correlation

Goal:

Avoid creating multiple tickets for a single outage.

Example:

Scheduler stopped
→ Articles stale
→ Signals stale
→ Briefings stale

Should become:

One Incident

Not:

Four Incidents

---

## Evidence Pack

Every incident automatically gathers:

### Timeline

- first signal
- last signal
- first occurrence
- latest occurrence

### Product State

- latest article
- latest signal
- latest narrative
- latest briefing

### Infrastructure State

- worker status
- scheduler status
- recent failures

### Deployment Context

- recent deploys
- recent config changes

### Historical Context

- similar incidents
- related cases

---

## Investigator Agent

Purpose:

Transform evidence into investigation guidance.

Input:

- incident
- evidence pack

Output:

- likely subsystem
- possible causes
- verification steps
- confidence levels

Example:

Likely subsystem: Scheduler

Confidence: High

Evidence:
- no articles
- no signals
- no scheduled tasks executed

Verification:
- check Celery Beat logs
- check scheduler heartbeat

---

## Ticket Writer Agent

Purpose:

Create Claude-ready tickets.

Output:

- Title
- Severity
- Impact
- Observed Behavior
- Expected Behavior
- Evidence
- Likely Subsystem
- Verification Steps
- Acceptance Criteria
- Validation Steps

---

## Validation Layer

After deployment, BugOps verifies:

- articles resumed
- signals resumed
- narratives refreshed
- briefing published

If healthy:
- Incident Resolved

Otherwise:
- Incident Reopened

---

## Success Metrics

### Primary Metric

Reduce time from:

Failure Occurs
→ Operator Understands Problem

From:

30–60 minutes

To:

Under 10 minutes

### Secondary Metrics

- Incidents detected automatically
- Tickets generated automatically
- Incidents with sufficient evidence
- False-positive rate
- Duplicate incident rate
- Mean time to recovery

---

## Sprint 020

### Production Health & Runtime Failure Detection

#### Deliverables

Outcome Signals:
- ArticleFreshnessSignalSource
- SignalFreshnessSignalSource
- NarrativeFreshnessSignalSource
- BriefingFreshnessSignalSource

Runtime Signals:
- RuntimeErrorSignalSource
- WorkerFailureSignalSource
- SchedulerFailureSignalSource

New Models:
- runtime_error_events
- incident_evidence

New Capabilities:
- exception fingerprinting
- incident correlation
- evidence pack generation
- ticket generation

#### Success Criteria

- Production failures become incidents automatically.
- Every incident contains investigation evidence.
- Every incident produces a Claude-ready bug ticket.
- No manual monitoring required.
