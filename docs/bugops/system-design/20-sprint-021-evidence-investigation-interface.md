# Sprint 021: Evidence & Investigation Interface

---

## Purpose

This document defines the interfaces for Sprint 021. It covers the
Evidence Pack interface, Evidence Pack durability contract, Investigation
interface, InvestigationProvider contract, and persistence model.

This document does not specify prompts, models, JSON schemas, acceptance
criteria, or implementation thresholds. Those are deferred to Sprint 021
implementation.

All architecture decisions referenced here are locked in
00-core-system-architecture.md.

---

## Scope

Sprint 021 defines interfaces for:

- Evidence Pack
- EvidenceCollector
- Investigation
- InvestigationProvider

Sprint 021 does not define:

- Prompt content or prompt structure
- Model selection or model configuration
- JSON schemas for Evidence Pack or Investigation payloads
- Acceptance criteria for investigation quality
- Cost thresholds or budget controls beyond what is locked in architecture
- Specific log formats or runtime error summary formats

---

## Evidence Pack Interface

### What goes in

An eligible open BugCase.

A BugCase is eligible for evidence collection when:
- It is active and not terminal (active means: open, notified,
  investigating, or equivalent non-terminal state)
- No Evidence Pack is already attached
- The settling window has elapsed since `first_seen_at`, OR severity
  is Critical and immediate collection is warranted

The settling window allows additional signals to arrive and attach to
the BugCase before evidence is frozen. This prevents an Evidence Pack
from being collected against an incomplete picture of the failure.

### What comes out

A completed Evidence Pack attached to the BugCase.

### What the Evidence Pack must contain

- **Logs:** relevant log excerpts from the period surrounding the
  BugCase's `first_seen_at` and `last_seen_at`
- **Deploy context:** recent deployment events that overlap with or
  precede the BugCase window
- **System state:** scheduler status, worker status, and database
  availability at the time of detection
- **Related signals:** other BugCases or observations that share
  subsystems with this BugCase, within a configurable lookback window
- **Metrics:** artifact counts and freshness indicators for the
  affected subsystems at time of detection (e.g., article count,
  last inserted_at per subsystem)

Evidence collection is deterministic. No LLM is involved in evidence
collection.

Evidence Packs record observed facts and references. They do not infer
root cause.

EvidenceCollector is an extension seam. The collector may evolve
without changing the BugCase → Evidence Pack contract.

### Settling window trigger rules

- Default: collect after a configurable settling window following
  `first_seen_at`
- Exception: collect immediately for Critical severity BugCases where
  evidence volatility is high (e.g., worker crash, scheduler failure)
- If the BugCase resolves before the settling window elapses, evidence
  collection still runs. Short-lived failures still matter for
  operational learning and future investigation.

---

## Evidence Pack Durability Contract

### What persists

The completed Evidence Pack is a durable artifact. It persists
independently of the BugCase lifecycle.

The Evidence Pack remains attached and inspectable after:
- The BugCase resolves
- The BugCase closes
- An Investigation is generated from it

### What expires

Raw evidence components (log excerpts, runtime snapshots) may expire
according to the retention policy. Default: 90 days.

Expiry applies to raw attached data only. The Evidence Pack record
itself and its structural metadata persist permanently.

### What remains permanent

- Evidence Pack record and metadata
- References to the originating BugCase
- Timestamps of collection
- Summary of what was collected (even after raw data expires)

The Investigation generated from an Evidence Pack is a separate
permanent artifact. It does not expire when raw evidence does.

---

## Investigation Interface

### What goes in

A completed Evidence Pack.

### What comes out

An Investigation attached to the BugCase containing:

- **Summary:** a concise description of what the evidence shows
- **Likely causes:** one or more candidate root causes ranked by
  plausibility
- **Evidence references:** specific pointers into the Evidence Pack
  that support each candidate cause
- **Verification steps:** concrete actions an operator or coding agent
  can take to confirm or rule out each candidate cause

### One current investigation per BugCase

A BugCase has one current Investigation. Reruns may replace or
supersede the current Investigation when material new evidence is
attached. Rerun on immaterial change is not permitted.

What constitutes material evidence change and how superseded
Investigations are handled is determined during Sprint 021
implementation and is not defined in this interface document.

---

## InvestigationProvider Contract

### Inputs

- Completed Evidence Pack
- BugCase metadata (severity, root_subsystem, affected_subsystems,
  first_seen_at, last_seen_at, observation_count)

### Outputs

- Summary
- Likely causes
- Evidence references
- Verification steps

### Constraints

- One current Investigation per BugCase at a time
- All LLM usage routes through the existing unified gateway for cost
  attribution and budget enforcement
- Investigation does not replace the Evidence Pack. The Evidence Pack
  remains independently inspectable regardless of Investigation output.
- InvestigationProvider is an extension seam. The implementation may
  use an LLM, a deterministic rule engine, or a hybrid. The interface
  contract does not change based on implementation strategy.

---

## Persistence Model

### Durable artifacts

| Artifact          | Retention   | Notes                                    |
|-------------------|-------------|------------------------------------------|
| Evidence Pack     | Permanent   | Record and metadata; raw data may expire |
| Raw evidence data | 90 days     | Log excerpts, snapshots, runtime data    |
| Investigation     | Permanent   | Does not expire when raw evidence does   |

### Retention alignment

Retention values here are consistent with the defaults established in
00-core-system-architecture.md. They are configurable and not immutable
architecture.

---

## Open Questions — Deferred to Sprint 021 Implementation

The following are explicitly deferred. They are named here so they are
not forgotten and not prematurely resolved.

- Prompt content and structure for the InvestigationProvider
- Model selection and configuration
- JSON schema for Evidence Pack payload
- JSON schema for Investigation output
- Acceptance criteria for investigation quality
- Definition of material evidence change for rerun eligibility
- How superseded Investigations are stored or referenced
- Specific log formats and log excerpt selection strategy
- Runtime error summary format and redaction rules
- Cost threshold and budget enforcement implementation detail
- Settling window default value
