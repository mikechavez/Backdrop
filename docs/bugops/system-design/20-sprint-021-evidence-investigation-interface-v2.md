# Sprint 021: Evidence & Investigation Interface

---

## Purpose

This document defines the interfaces for Sprint 021. It covers the
Evidence Pack interface, Evidence Pack durability contract, Investigation
interface, InvestigationProvider contract, and persistence model.

All architecture decisions referenced here are locked in
00-core-system-architecture.md.

---

## Design Context

This document reflects decisions made during a pre-sprint design session
using BUG-064 (Memory Leak + Retry Storm) as the Golden Incident. A
hand-written Golden Investigation artifact exists at
`golden-investigation-bug-064.md` and serves as the target output for
the InvestigationProvider. Sprint 021 is successful when the
InvestigationProvider can produce an Investigation of comparable quality
from the Evidence Pack alone.

Key insight from the Golden Incident exercise: for BUG-064, the most
diagnostic evidence was not logs. It was cost control metrics, the
exact incident timestamp, and healthy signals eliminating other
subsystems. Log excerpts confirmed the retry pattern but were not
required to form the primary hypothesis. This should inform how
Evidence Pack sections are weighted in the InvestigationProvider prompt.

---

## Scope

Sprint 021 defines interfaces and implementations for:

- Evidence Pack model and schema
- EvidenceCollector framework
- Subsystem metrics collector
- Related BugCase collector
- Railway API client (foundation for deploy context and log collection)
- Deploy context collector (via Railway)
- Log excerpt collector (via Railway)
- System state collector (via `/health` endpoint and Railway service status)
- Configuration Evidence collector
- Evidence redaction layer
- Investigation model and schema
- InvestigationProvider
- Monitor loop integration for Evidence Pack and Investigation generation

Sprint 021 does not define:

- Retroactive Investigation reruns (one Investigation per BugCase, no reruns this sprint)
- Superseded Investigation storage or versioning
- Runtime error signal sources (RuntimeExceptionSignalSource deferred)
- External heartbeat
- Investigation UI or API surface beyond Slack notification
- Per-subsystem Railway log filtering beyond service-level collection

---

## Locked Decisions

The following were deferred in the original interface document and are
now resolved.

**Settling window default:** 10 minutes (`BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES=10`).
Matches Sprint 020 Recovery Window. Gives downstream signals time to
attach before evidence is frozen. Critical BugCases collect immediately.

**Investigation reruns:** One Investigation per BugCase. No reruns in
Sprint 021. Rerun eligibility and superseded Investigation handling are
deferred to a future sprint.

**Token budget:** `BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS=12000`.
`BUGOPS_EVIDENCE_MAX_TOTAL_CHARS=60000`. If the Evidence Pack exceeds
the budget, logs are compressed or truncated before structured evidence
is removed. See Truncation Policy below.

**Log window:** `BUGOPS_LOG_WINDOW_MINUTES=10` on each side of
`first_seen_at` and `last_seen_at`.

**Log line cap:** `BUGOPS_LOG_LINE_CAP=200` per service. Redis logs
are not collected in Sprint 021.

**Services collected:** FastAPI, Celery worker, Celery scheduler.

**Prompt structure:** The 10-section Investigation structure is locked.
See Investigation Structure below.

**Success criterion:** A person unfamiliar with the incident can reach
the likely fix area substantially faster using the Investigation than
without it.

**Investigation consumer hierarchy:** Human operator first (sections
1–7), TicketWriter second (sections 8–10).

**Failure taxonomy:** Controlled vocabulary locked in architecture doc.

---

## Evidence Pack Interface

### What goes in

An eligible open BugCase.

A BugCase is eligible for evidence collection when:
- Status is active and not terminal (open, notified, investigating,
  or equivalent non-terminal state)
- No Evidence Pack is already attached
- The settling window has elapsed since `first_seen_at`, OR severity
  is Critical and immediate collection is warranted

The settling window allows additional signals to arrive and attach
before evidence is frozen.

### What comes out

A completed Evidence Pack attached to the BugCase. The pack may be
partial. It must never be ambiguous.

Every missing source must be recorded explicitly with reason and
timestamp. Silence about a missing source is not permitted.

Example of correct partial pack reporting:
```
railway_logs: unavailable
  reason: API timeout
  attempted_at: 2026-04-13T00:15:03Z
```

Example of incorrect partial pack reporting:
```
(no railway_logs section)
```

### What the Evidence Pack must contain

**Metadata**
- `bugcase_id`
- `collection_started_at`
- `collection_completed_at`
- `collection_duration_ms`
- `incident_first_seen_at`
- `incident_last_seen_at`
- `root_subsystem`
- `severity`
- `collection_status`: `complete` or `partial`

**BugCase snapshot**
- Primary signal summary
- Blast radius
- Current status at collection time

**Subsystem metrics** — collected at collection time, not incident time
- Per affected subsystem: last artifact timestamp, record count,
  freshness indicator
- `collected_at` timestamp for this section

**System state** — current-at-collection-time only, not historical
- MongoDB: status and latency from `/health` endpoint
- Redis: status and latency from `/health` endpoint
- FastAPI: overall status from `/health` endpoint
- Pipeline heartbeats: `fetch_news` and `generate_briefing` status
  and last success from `/health` endpoint
- Celery worker: Railway deployment status
- Celery scheduler: Railway deployment status
- `collected_at` timestamp for this section

**Healthy signals** — explicit enumeration of what was confirmed healthy
and what each healthy signal eliminates as a primary cause. This section
is required, not optional.

**Related BugCases** — open or recently resolved cases sharing
subsystems, within a configurable lookback window (default 7 days)
- `collected_at` timestamp for this section

**Deploy context** — via Railway API
- Current deployment ID per service
- Deployment status
- `created_at` and `updated_at` per deployment
- Recent deployments overlapping or preceding the BugCase window
- Services reviewed: FastAPI, Celery worker, Celery scheduler
- `collected_at` timestamp for this section

**Configuration Evidence** — incident-relevant configuration only,
not a full config dump. Sprint 021 scope:
- LLM gateway budget settings: soft limit, hard limit
- Critical operations list
- BugOps freshness window thresholds
- `collected_at` timestamp for this section

**Log excerpts** — via Railway API
- Per service: `lines_fetched`, `lines_stored`, `truncated` (bool),
  `window_start`, `window_end`
- Redacted before storage (see Redaction below)
- Services: FastAPI, Celery worker, Celery scheduler
- `collected_at` timestamp for this section

**Collection statistics**
- `total_chars`
- `sections_collected` list
- `sections_missing` list with reason per missing section
- `redactions_applied` count
- `truncation_applied` list of sections truncated

**Collection errors** — explicit record of any collection failure
- Per failure: source, error type, error message, `attempted_at`

---

## Evidence Pack Ambiguity Rule

Evidence Packs may be partial. They must never be ambiguous.

Every section that was not collected must appear in `sections_missing`
with an explicit reason. Every truncation must be recorded in
`collection_statistics`. Every redaction must increment
`redactions_applied`.

An Evidence Pack with a missing section and no explanation is a
defective Evidence Pack. Collection failures do not justify silence.

---

## Evidence Pack Durability Contract

### What persists

The completed Evidence Pack is a durable artifact. It persists
independently of the BugCase lifecycle.

The Evidence Pack remains attached and inspectable after:
- The BugCase resolves
- The BugCase closes
- An Investigation is generated from it

Collection still runs if a BugCase resolves before the settling window
elapses. Short-lived failures matter for the operational corpus.

### What expires

Raw evidence components (log excerpts, runtime snapshots) may expire
per the retention policy. Default: 90 days.

Expiry applies to raw attached data only. The Evidence Pack record,
structural metadata, and collection statistics persist permanently.

### What remains permanent

- Evidence Pack record and metadata
- References to the originating BugCase
- Timestamps of collection
- Collection statistics (even after raw data expires)
- Investigations generated from this pack

---

## Truncation Policy

When Evidence Pack size exceeds `BUGOPS_EVIDENCE_MAX_TOTAL_CHARS`,
sections are truncated in this priority order. Higher-priority sections
are preserved first.

```
1. BugCase metadata              ← never truncated
2. Subsystem metrics             ← never truncated
3. System state and healthy signals  ← never truncated
4. Deploy context                ← never truncated
5. Configuration Evidence        ← never truncated
6. Collection errors             ← never truncated
7. Related BugCases              ← truncated last among structured data
8. Log excerpts                  ← truncated first
```

Logs are the first evidence trimmed. Structured evidence is compact
and high-signal. Logs are noisy and large.

When log truncation occurs, most-recent lines within the window are
preferred over earliest lines.

---

## Redaction

Log lines must be redacted before storage and before passing to the
InvestigationProvider. Redaction occurs in EvidenceCollector, not in
InvestigationProvider.

Redaction targets: API keys, tokens, connection strings, email
addresses, MongoDB URIs, HTTP Authorization headers, bearer tokens,
and any value matching common secret patterns.

Redacted values are replaced with `[REDACTED]`. The count of
redactions applied is recorded in collection statistics.

The InvestigationProvider must never receive raw unredacted log content.

---

## Redaction and Partial Collection: Collection Failure Behavior

If Railway API is unavailable during log collection:
- Log excerpts section is marked missing with reason and timestamp
- All other sections continue to collect normally
- Evidence Pack is marked `collection_status: partial`
- BugCase is not affected

Collection failure in one source never halts collection of other
sources. Each source is independent.

---

## Railway API Client

Sprint 021 implements a Railway GraphQL API client as a shared
foundation for both deploy context and log collection.

The client:
- Authenticates via `RAILWAY_API_TOKEN` environment variable
- Resolves service name → active deployment ID (cached per poll cycle)
- Supports deployment listing with date range filtering
- Supports log fetching by deployment ID and time window
- Handles auth errors, rate limits, and timeouts with structured
  error reporting
- Does not use Railway CLI (CLI requires local auth, cannot run in
  Railway container)

The existing stub at `bugops/signal_sources/railway_logs.py` is the
starting point. The GraphQL client implementation lives there or in
a shared `bugops/clients/railway.py` module — determined during
implementation.

---

## System State Collection

System state uses current-at-collection-time checks only. Historical
state reconstruction is not in scope for Sprint 021.

**MongoDB, Redis, FastAPI, pipeline heartbeats:** collected via
`GET /health` at `src/crypto_news_aggregator/api/v1/health.py`.
No authentication required. Response includes `status`, `latency_ms`,
and pipeline heartbeat status for `fetch_news` and `generate_briefing`.

**Celery worker and scheduler liveness:** collected via Railway service
deployment status (active/inactive, restart count). This is best-effort
in Sprint 021. A full heartbeat system is deferred.

System state is a point-in-time snapshot. The Evidence Pack records
`collected_at` for this section. The Investigation must not imply
system state reflects incident time if collection occurred later.

---

## Configuration Evidence Collection

Configuration Evidence collects incident-relevant configuration values
only. It is not a full config dump.

Sprint 021 scope:
- `LLM_DAILY_SOFT_LIMIT` from Railway environment or settings
- `LLM_DAILY_HARD_LIMIT` from Railway environment or settings
- `CRITICAL_OPERATIONS` list from `cost_tracker.py` settings
- BugOps freshness window thresholds from `core/config.py`

The BUG-064 Golden Incident demonstrated that the operation name
mismatch (`briefing_generate` vs `briefing_generation`) was
unconfirmable from the Evidence Pack without Configuration Evidence.
This collector closes that gap.

Configuration Evidence is collected deterministically. No LLM is
involved.

---

## Investigation Interface

### What goes in

- A completed Evidence Pack
- BugCase metadata: severity, root_subsystem, affected_subsystems,
  first_seen_at, last_seen_at, observation_count

### What comes out

An Investigation attached to the BugCase, structured in ten sections.

### Investigation Structure

Every Investigation must contain these ten sections in order:

1. **Incident Summary** — what broke, when, and for how long
2. **Impact** — which subsystems and outputs are affected
3. **What Is Broken** — observed failure signals with evidence references
4. **What Is Not Broken** — confirmed healthy signals and what they eliminate
5. **Recent Changes** — deploy context and configuration changes near incident time
6. **Evidence Timeline** — chronological ordering of key observations
7. **Recommended Investigation Order** — ordered checklist with estimated time per step, ordered by time-to-confirm not confidence
8. **Hypotheses** — each with supporting evidence, contradicting evidence, confidence, and evidence references. No hypothesis without an evidence reference.
9. **Potential Fix Areas** — probable files, components, and do-not-modify zones
10. **Unknowns and Missing Evidence** — explicitly named gaps, never omitted

Sections 1–7 serve the human operator performing triage.
Sections 8–10 serve the TicketWriter generating a Ticket Draft.

### Investigation Consumer Hierarchy

**Primary consumer: Human operator**

The operator reads sections 1–7 to understand what to check next,
in what order, without opening Railway, MongoDB, or any external tool.

**Secondary consumer: TicketWriter**

The TicketWriter reads sections 8–10 to generate a self-contained
Ticket Draft without re-reading the Evidence Pack.

Optimizing sections 8–10 at the expense of sections 1–7 is incorrect.

### Investigation Quality Standard

**Success criterion:** A person unfamiliar with the incident can reach
the likely fix area substantially faster using the Investigation than
without it.

**Automatic failure modes:**

1. **Unsupported claim** — any hypothesis without an evidence reference.
   Unknown is allowed. Invented is not.

2. **Missed obvious evidence** — a conclusion that ignores a directly
   relevant data point in the Evidence Pack.

3. **No actionable next step** — analysis without an investigation order.

4. **Wrong subsystem** — pointing toward a component that healthy
   signals in the Evidence Pack eliminate as a primary cause.

An Investigation that fails any of these checks is a failed Investigation.

### One Investigation per BugCase

A BugCase has one Investigation in Sprint 021. No reruns. Rerun
eligibility is deferred.

---

## InvestigationProvider Contract

### Inputs

- Completed Evidence Pack (redacted, within token budget)
- BugCase metadata

### Outputs

An Investigation with all ten sections populated.

### Constraints

- One Investigation per BugCase
- All LLM usage routes through the existing unified gateway for cost
  attribution and budget enforcement
- Max input tokens: `BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS=12000`
- If Evidence Pack exceeds token budget, apply truncation policy before
  passing to LLM. Never remove structured evidence to preserve logs.
- Investigation does not replace the Evidence Pack. Both artifacts
  persist independently.
- InvestigationProvider is an extension seam. Implementation may use
  an LLM, a deterministic rule engine, or a hybrid.
- The InvestigationProvider must not receive unredacted log content.
- Every hypothesis must include evidence references. The prompt must
  enforce this structurally, not as a suggestion.

### Model and prompt

Model selection and prompt content are determined during Sprint 021
implementation. The Golden Investigation artifact
(`golden-investigation-bug-064.md`) is the prompt target and quality
benchmark. Write the prompt to produce that artifact from the BUG-064
Evidence Pack.

---

## Persistence Model

### Durable artifacts

| Artifact | Retention | Notes |
|---|---|---|
| Evidence Pack | Permanent | Record and metadata; raw data may expire |
| Raw evidence data | 90 days | Log excerpts, snapshots, runtime data |
| Investigation | Permanent | Does not expire when raw evidence does |

---

## New Config Keys

Add to `core/config.py` in the BugOps section, following existing
naming conventions:

```python
BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES: int = 10
BUGOPS_LOG_WINDOW_MINUTES: int = 10
BUGOPS_LOG_LINE_CAP: int = 200
BUGOPS_EVIDENCE_MAX_TOTAL_CHARS: int = 60000
BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS: int = 12000
RAILWAY_API_TOKEN: str = ""
```

---

## Sprint 021 Success Criteria

- Evidence Packs are generated automatically after the settling window
  for all eligible BugCases
- Evidence Packs generated for Critical BugCases immediately, without
  waiting for settling window
- Evidence Packs are generated even when BugCases resolve before the
  settling window elapses
- Partial Evidence Packs record missing sources explicitly with reason
  and timestamp — never silently omit
- Log excerpts are redacted before storage
- Investigations are generated automatically from completed Evidence Packs
- Every Investigation hypothesis includes at least one evidence reference
- No Investigation asserts a claim that contradicts healthy signals in
  the Evidence Pack
- Investigation token budget is enforced; structured evidence is never
  dropped to preserve logs
- All LLM usage routes through the unified gateway
- A Slack notification is sent when an Investigation is ready, including
  the incident summary and first recommended investigation step
- TASK-211 quality review validates at least 5 real Evidence Packs and
  Investigations against the Golden Investigation benchmark and four
  failure modes

---

## Open Questions — Deferred to Sprint 021 Implementation

The following remain open and are resolved during implementation, not design.

- JSON schema for Evidence Pack payload (implement during TASK-200)
- JSON schema for Investigation output (implement during TASK-208)
- Prompt content and exact structure (derive from golden artifact during TASK-209)
- Railway GraphQL query structure for deployment listing and log fetching (TASK-205)
- Exact redaction pattern list beyond common cases (TASK-207)
- Settling window behavior for BugCases that transition through multiple
  severity levels before evidence collection
- Whether Configuration Evidence should pull from Railway environment API
  or from `core/config.py` at collection time (both may be needed)
