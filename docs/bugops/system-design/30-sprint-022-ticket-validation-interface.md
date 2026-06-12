# Sprint 022: Ticket & Validation Interface

---

## Purpose

This document defines the interfaces for Sprint 022. It covers the
Ticket Draft interface, TicketWriter contract, TicketExporter contract,
human approval interface, coding agent handoff contract, validation
interface, ValidationRunner contract, and reopen logic.

This document does not specify ticket formats, validation thresholds,
prompt content, model selection, or implementation detail. Those are
deferred to Sprint 022 implementation.

All architecture decisions referenced here are locked in
00-core-system-architecture.md.

---

## Scope

Sprint 022 defines interfaces for:

- Ticket Draft
- TicketWriter
- TicketExporter
- Human approval
- Coding agent handoff
- Validation
- ValidationRunner
- Reopen logic

Sprint 022 does not define:

- Ticket format or field schema
- Validation thresholds or scoring rubrics
- Prompt content or model selection for TicketWriter
- Coding agent protocol or execution environment
- Export target configuration beyond current implementation
- Specific acceptance criteria format

---

## Ticket Draft Interface

### What goes in

A completed Investigation.

### What comes out

One or more Ticket Drafts attached to the BugCase.

A single Investigation may produce multiple Ticket Drafts. Each Ticket
Draft represents a discrete unit of proposed implementation work.
The relationship is one Investigation to one or more Ticket Drafts.

### Human promotion requirement

Ticket Drafts are proposed work. They are not approved work.

No Ticket Draft proceeds to coding agent execution without explicit
human approval. This is a permanent architecture invariant and is not
configurable.

---

## TicketWriter Contract

### Inputs

- Completed Investigation
- BugCase metadata (severity, root_subsystem, affected_subsystems,
  first_seen_at, last_seen_at)

### Outputs

One or more Ticket Drafts, each containing at minimum:

- Title
- Severity
- Affected subsystem
- Summary of evidence supporting this ticket
- Likely cause being addressed
- Verification steps
- Acceptance criteria
- Validation steps
- File guidance (see below)

**File Guidance**

Each Ticket Draft includes a file guidance block to support coding agent
execution. The TicketWriter populates this based on the Investigation.
File guidance is a recommendation, not an authorization.

```
Likely files to inspect:
  - path/to/relevant/file.py

Likely files to modify:
  - path/to/file.py

Do not modify:
  - path/to/protected_area/

Unknowns:
  - Exact file for [X] must be located during implementation
```

Unknown file locations are explicitly named rather than omitted.
The coding agent is expected to locate unknowns during implementation.

Exact field schema is deferred to Sprint 022 implementation.

### Constraints

- TicketWriter is an extension seam. Implementation may change without
  altering the Investigation → Ticket Draft contract.
- All LLM usage routes through the existing unified gateway for cost
  attribution and budget enforcement.
- TicketWriter owns content generation only. It does not own export
  or delivery.
- Ticket Drafts may propose code changes, configuration changes,
  documentation changes, operational actions, or no-code follow-up.
  The TicketWriter recommends likely files to inspect or modify based
  on the Investigation. It does not authorize changes.
- TicketWriter proposes. Human approves. Coding agent executes.

---

## TicketExporter Contract

### What goes in

An approved Ticket Draft.

### What comes out

An exported ticket in the target format, delivered to the target
destination.

### Current implementation

Repository markdown. Approved Ticket Drafts are written as structured
markdown files into the repository.

### Future targets

GitHub issues, Linear, PR comments, or other destinations. These are
deferred and listed in 90-deferred-future-work.md.

### Constraints

- TicketExporter is an extension seam. Export targets may be added or
  changed without altering the TicketWriter contract.
- TicketExporter is decoupled from content generation. It receives a
  finalized Ticket Draft and is responsible only for delivery.
- TicketExporter does not modify Ticket Draft content.

---

## Human Approval Interface

### Where review occurs

The operator reviews Ticket Drafts before any coding agent execution.
The review surface is not specified in this interface document. It may
be a CLI command, an internal UI, or a direct file review depending on
Sprint 022 implementation.

### What the operator approves

The operator approves a Ticket Draft for coding agent execution. Approval
is per Ticket Draft, not per Investigation or per BugCase.

An operator may approve some Ticket Drafts from an Investigation and
decline others. Partial approval is supported.

### What gets handed to the coding agent

An approved Ticket Draft with all required fields populated. The coding
agent receives a self-contained handoff artifact. It does not need
direct access to BugOps internals at execution time. Relevant evidence
and investigation excerpts may be included in the handoff artifact.

---

## Coding Agent Handoff Contract

### What must be present

The handoff artifact must contain sufficient context for a coding agent
to execute the implementation work without requiring access to BugOps
internals. At minimum:

- Title
- Affected subsystem
- Summary of the problem being addressed
- Likely cause
- Verification steps
- Acceptance criteria
- Validation steps
- File guidance (likely files to inspect, likely files to modify,
  do not modify, unknowns)

The coding agent receives a self-contained handoff artifact. It does not
need direct access to BugOps internals at execution time. Relevant
evidence and investigation excerpts may be included in the handoff
artifact.

### Format requirements

Exact handoff format is deferred to Sprint 022 implementation. Format
must be self-contained and not require the coding agent to query BugOps
state at execution time.

---

## Validation Interface

### What goes in

- An implementation result (coding agent completion report or operator
  attestation)
- The approved Ticket Draft that was executed
- The originating BugCase

### What comes out

A Validation Run attached to the BugCase, with one of three outcomes:

- **Resolved:** recovery is stable and the BugCase closes
- **Reopened:** recovery conditions are not met and the BugCase
  returns to active state
- **Manual review required:** validation cannot determine outcome
  and escalates to the operator

---

## ValidationRunner Contract

### Inputs

- Implementation result
- Approved Ticket Draft
- BugCase metadata

### Outputs

- Validation Run record
- Outcome: resolved, reopened, or manual review required

### Constraints

- ValidationRunner is an extension seam. It is expected to evolve
  significantly as validation strategies mature.
- Validation evaluates outcome recovery using the same freshness
  authority as the original detector. Component liveness alone is
  not sufficient for resolution.
- Validation thresholds and scoring are deferred to Sprint 022
  implementation.

---

## Reopen Logic

### What triggers reopen

A Validation Run that returns outcome: reopened causes the BugCase
to return to active state.

Reopen may also be triggered by the auto-resolution recovery model
if recovery conditions fail after a BugCase has resolved (see
00-core-system-architecture.md Recovery Model).

### Reopen tracking

Each reopen increments `reopen_count` on the BugCase.

### Manual review escalation

After a configurable number of reopen cycles, the BugCase requires
manual operator review before further automated action is taken.
The escalation threshold is configurable and is not defined in this
interface document.

---

## Persistence Model

### Durable artifacts

| Artifact        | Retention | Notes                                          |
|-----------------|-----------|------------------------------------------------|
| Ticket Drafts   | Permanent | Persist after approval, export, and resolution |
| Validation Runs | Permanent | Persist after BugCase resolves or closes       |

### Retention alignment

Retention values here are consistent with the defaults established in
00-core-system-architecture.md. They are configurable and not immutable
architecture.

---

## Open Questions — Deferred to Sprint 022 Implementation

The following are explicitly deferred. They are named here so they are
not forgotten and not prematurely resolved.

- Ticket Draft field schema
- Coding agent handoff format
- Human approval review surface
- Validation threshold and scoring logic
- Definition of implementation result for ValidationRunner input
- Acceptance criteria format
- Manual review escalation threshold
- Export target configuration for TicketExporter beyond repository
  markdown
- Prompt content and model selection for TicketWriter
