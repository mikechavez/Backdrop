# Sprint 021 — Evidence & Investigation

**Status:** Planned
**Started:** —
**Target:** BugCases automatically produce Evidence Packs and Investigations, eliminating manual context reconstruction after production failures

---

## Sprint Goal

Sprint 021 builds the evidence and triage layers of BugOps. When a BugCase opens, BugOps automatically collects a structured Evidence Pack — logs, metrics, system state, deploy context, related cases, and incident-relevant configuration — then generates a triage Investigation that tells an operator what to check next and in what order.

This sprint is divided into two phases with a mandatory milestone gate between them. Phase A builds the evidence infrastructure. Phase B builds the investigation layer. Phase B does not begin until Phase A is validated against real production Evidence Packs.

The sprint is successful when the InvestigationProvider produces an Investigation comparable in quality to the hand-written Golden Investigation for BUG-064 (`golden-investigation-bug-064.md`).

---

## Design Artifacts

The following artifacts were produced during pre-sprint design and are the authoritative reference for all implementation decisions in this sprint:

- `00-core-system-architecture-v2.md` — updated architecture with new permanent principles
- `20-sprint-021-evidence-investigation-interface-v2.md` — updated interface contract with all locked decisions
- `golden-investigation-bug-064.md` — hand-written target Investigation for BUG-064

Key design insight from BUG-064 Golden Incident exercise: for a cost-control failure, the most diagnostic evidence was not logs — it was cost control metrics, the exact incident timestamp, and healthy signals eliminating other subsystems. Log excerpts confirmed the retry pattern but were not required to form the primary hypothesis. This informs evidence section weighting in the InvestigationProvider prompt.

---

## Scope Boundary

### In Scope

**Phase A — Evidence Infrastructure**
- [ ] EvidencePack model and schema (TASK-114)
- [ ] EvidencePack schema review against BUG-064 (TASK-114A)
- [ ] EvidencePack persistence (TASK-115)
- [ ] EvidenceCollector framework with settling window and trigger logic (TASK-116)
- [ ] Subsystem metrics + system state collector (TASK-117)
- [ ] Related BugCase collector (TASK-118)
- [ ] Railway API client — shared foundation for deploy context and logs (TASK-119)
- [ ] Deploy context collector via Railway (TASK-120)
- [ ] Configuration Evidence collector (TASK-121)
- [ ] Railway log collector with redaction (TASK-122)
- [ ] Wire EvidenceCollector into monitor loop (TASK-123)

**Phase B — Triage Generation**
- [ ] Investigation model and schema (TASK-124)
- [ ] InvestigationProvider with prompt and gateway routing (TASK-125)
- [ ] Wire Investigation generation to Evidence Pack completion (TASK-126)
- [ ] Evidence Pack and Investigation quality review (TASK-127)

### Out of Scope / Non-Goals

- [ ] Investigation reruns or superseded Investigation versioning
- [ ] RuntimeExceptionSignalSource (deferred)
- [ ] External heartbeat (deferred)
- [ ] Investigation UI, API endpoint, or admin surface beyond Slack notification
- [ ] Redis log collection
- [ ] Per-subsystem Railway log filtering beyond service-level
- [ ] Historical system state reconstruction (current-at-collection-time only)
- [ ] Full worker/scheduler heartbeat system (best-effort via Railway status only)
- [ ] TicketWriter or coding agent handoff (Sprint 022)

---

## Sprint Order

| # | Ticket | Title | Phase | Status | Est |
|---|--------|-------|-------|--------|-----|
| 1 | TASK-114 | Define EvidencePack model and schema | A | ✅ COMPLETE | M |
| 2 | TASK-114A | EvidencePack schema review against BUG-064 | A | ✅ COMPLETE | S |
| 3 | TASK-115 | Implement EvidencePack persistence | A | ✅ COMPLETE | S |
| 4 | TASK-116 | Implement EvidenceCollector framework | A | ✅ COMPLETE | M |
| 5 | TASK-117 | Collect subsystem metrics and system state | A | 🔲 OPEN | M |
| 6 | TASK-118 | Collect related BugCases | A | 🔲 OPEN | S |
| 7 | TASK-119 | Build Railway API client | A | 🔲 OPEN | M |
| 8 | TASK-120 | Collect deploy context via Railway | A | 🔲 OPEN | M |
| 9 | TASK-121 | Collect Configuration Evidence | A | 🔲 OPEN | S |
| 10 | TASK-121A | Collect LLM Trace and Cost Evidence | A | 🔲 OPEN | S |
| 11 | TASK-122 | Collect Railway log excerpts with redaction | A | 🔲 OPEN | M |
| 12 | TASK-123 | Wire EvidenceCollector into monitor loop | A | 🔲 OPEN | M |
| — | **PHASE A EXIT GATE** | Review 3+ real Evidence Packs before proceeding | — | 🔲 OPEN | — |
| 13 | TASK-124 | Define Investigation model and schema | B | 🔲 OPEN | M |
| 14 | TASK-125 | Implement InvestigationProvider | B | 🔲 OPEN | L |
| 15 | TASK-126 | Wire Investigation generation to Evidence Pack completion | B | 🔲 OPEN | M |
| 16 | TASK-127 | Evidence Pack and Investigation quality review | B | 🔲 OPEN | M |

**Sequencing:**

Phase A — Evidence Infrastructure (sequential where noted, parallel where possible):
- TASK-114 → TASK-114A → TASK-115 → TASK-116 (strict sequence, foundation)
- TASK-117, TASK-118, TASK-121, TASK-121A (parallel, all depend on TASK-116, no Railway dependency)
- TASK-119 → TASK-120, TASK-122 (TASK-119 must precede both)
- TASK-123 (depends on all collectors: 117, 118, 119, 120, 121, 121A, 122)

Phase A Exit Gate (mandatory before Phase B):
- Generate 3+ real Evidence Packs from production BugCases
- Review manually against exit criteria below

Phase B — Triage Generation (sequential):
- TASK-124 → TASK-125 → TASK-126 → TASK-127

---

## Phase A Exit Criteria

**Do not begin TASK-124 until all of the following are confirmed:**

- [ ] At least 3 real Evidence Packs generated from production BugCases and stored successfully
- [ ] No Evidence Pack has a missing section without an explicit reason recorded in `collection_errors`
- [ ] Configuration Evidence section is populated with LLM budget settings and critical operations list
- [ ] LLM Trace Evidence section is populated with operation counts, costs, and recent traces
- [ ] Log excerpts are present for at least 2 of the 3 services (FastAPI, Celery worker, Celery scheduler)
- [ ] Truncation metadata is recorded correctly when log cap is reached
- [ ] Redaction is applied — `redactions_applied` count is accurate
- [ ] Per-section `collected_at` timestamps are present on all collected sections
- [ ] Evidence references (E-001, E-002...) are indexable within the pack — no collisions across collectors
- [ ] At least one partial Evidence Pack (Railway API unavailable or timeout) handled gracefully with explicit error record
- [ ] BUG-064 scenario is reproducible: a simulated cost-control failure produces an Evidence Pack containing `llm_trace_summary.total_cost`, `config_evidence.critical_operations`, blocked operation name, and healthy system signals

Operator judgment call after manual review:
- [ ] Configuration Evidence is useful — budget settings and critical operations list would have helped diagnose a real incident
- [ ] Log excerpts add signal beyond what metrics already show
- [ ] Evidence Pack is readable by a human unfamiliar with the incident

---

## Success Criteria

**Phase A**
- Evidence Packs generated automatically after settling window for all eligible BugCases
- Critical BugCases trigger immediate collection without waiting for settling window
- Evidence Packs generated even when BugCases resolve before settling window elapses
- Partial Evidence Packs record missing sources explicitly — never silently omit
- Log excerpts redacted before storage
- All Evidence Pack collectors are independent — one failure does not halt others
- Phase A Exit Criteria passed before Phase B begins

**Phase B**
- Investigations generated automatically from completed Evidence Packs
- Every Investigation hypothesis includes at least one evidence reference
- No Investigation asserts a claim that contradicts healthy signals in the Evidence Pack
- Investigation token budget enforced — structured evidence never dropped to preserve logs
- All LLM usage routes through the unified gateway
- Slack notification sent when Investigation is ready, including incident summary and first recommended investigation step
- TASK-127 quality review validates at least 5 real Evidence Packs and Investigations against the Golden Investigation benchmark and four failure modes

---

## Agent Safety Notes

These constraints apply to all implementation agents working this sprint:

- Do not modify production data
- Do not introduce broad database, shell, or filesystem access when a narrow tool/API is sufficient
- Do not change unrelated files
- Do not add autonomous destructive actions
- Keep implementation bounded to the ticket's listed files unless a blocker is documented
- If implementation requires a new file/path not listed in the ticket, stop and document why before proceeding
- Railway API calls must use `RAILWAY_API_TOKEN` from environment — never hardcode credentials
- All LLM calls must route through the existing unified gateway — never call Anthropic API directly
- Log content must be redacted before storage and before passing to any LLM — never store or forward raw log lines

---

## Implementation Notes

### New Config Keys

Add to `core/config.py` in the BugOps section, following existing naming conventions:

```python
BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES: int = 10
BUGOPS_LOG_WINDOW_MINUTES: int = 10
BUGOPS_LOG_LINE_CAP: int = 200
BUGOPS_EVIDENCE_MAX_TOTAL_CHARS: int = 60000
BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS: int = 12000
RAILWAY_API_TOKEN: str = ""
```

### New Collections

```
evidence_packs         — EvidencePack documents (permanent)
investigations         — Investigation documents (permanent)
```

### Expected Branch Naming

```
task/bugops-114-evidence-pack-model
task/bugops-114a-schema-review-bug-064
task/bugops-115-evidence-pack-persistence
task/bugops-116-evidence-collector-framework
task/bugops-117-metrics-system-state
task/bugops-118-related-bugcase-collector
task/bugops-119-railway-api-client
task/bugops-120-deploy-context-collector
task/bugops-121-config-evidence-collector
task/bugops-121a-llm-trace-cost-collector
task/bugops-122-log-collector-redaction
task/bugops-123-wire-evidence-collector
task/bugops-124-investigation-model
task/bugops-125-investigation-provider
task/bugops-126-wire-investigation-generation
task/bugops-127-quality-review
```

### Expected Commit Format

```
feat(bugops): description
task(bugops): description
fix(bugops): description
```

### Test Expectations

- Unit tests added or updated for every logic change
- Follow existing patterns in `tests/bugops/`: `AsyncMock` for Motor/HTTP, `MagicMock` for sync, `@pytest.mark.asyncio` for async tests, `patch.object` for settings overrides
- New test files: `test_evidence_pack_model.py`, `test_evidence_collector.py`, `test_railway_client.py`, `test_llm_trace_collector.py`, `test_investigation_model.py`, `test_investigation_provider.py`
- All existing BugOps tests must continue to pass after each ticket

### Truncation Priority Order

When Evidence Pack exceeds `BUGOPS_EVIDENCE_MAX_TOTAL_CHARS`, truncate in this order (last to first):

1. Log excerpts — truncated first
2. Related BugCases — truncated last among structured data
3. Configuration Evidence, deploy context, system state, metrics, LLM trace summary, metadata — never truncated

---

## Key Decisions

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-06-16 | Phase A / Phase B milestone gate | Prevent over-specifying Investigation before seeing real Evidence Packs | Phase B tickets not written until gate passed |
| 2026-06-16 | One Investigation per BugCase, no reruns in Sprint 021 | Simpler; rerun design deferred until at least one Investigation exists in production | TASK-125 does not implement rerun logic |
| 2026-06-16 | System state is current-at-collection-time only | Historical reconstruction requires heartbeat system not yet built | Worker/scheduler liveness is best-effort via Railway service status |
| 2026-06-16 | Configuration Evidence added as first-class collector | BUG-064 exercise revealed operation name mismatch unconfirmable without it | TASK-121 added to Phase A |
| 2026-06-16 | LLM Trace Evidence added as first-class collector | Cost and routing activity is primary evidence for a significant class of failures | TASK-121A added to Phase A |
| 2026-06-16 | Redis logs excluded from Sprint 021 | Redis process logs rarely diagnostic for Backdrop failures | Can be added in future sprint if corpus shows need |
| 2026-06-16 | Schema-vs-prompt separation for Investigation | Ten-section format is a rendering concern, not a persistence concern | Investigation schema stores structured fields; prompt renders ten sections |
| 2026-06-16 | Human first, agent second consumer hierarchy | Sections 1-7 for operator triage; sections 8-10 for TicketWriter | Prompt must not optimize agent sections at expense of operator sections |
| 2026-06-16 | Default Investigation model: DeepSeek | Structured analysis task, not prose generation; dramatically cheaper; already integrated; benchmarkable against corpus | BUGOPS_INVESTIGATION_MODEL defaults to DeepSeek in TASK-125 |
| 2026-06-16 | Operation name: bugops_investigation | Required for cost tracking, budget enforcement, model routing, and corpus analysis | All InvestigationProvider calls use this operation name in llm_traces |
| 2026-06-16 | All InvestigationProvider calls route through LLM Gateway | Direct provider calls prohibited; gateway enforces spend caps, tracing, and model routing | TASK-125 must use gateway.call(), never direct Anthropic API |
| 2026-06-16 | Evidence Packs retained permanently | Evidence Packs are the operational corpus; raw data expires at 90 days but records persist | evidence_packs collection has no TTL index |
| 2026-06-16 | Investigations generated only after Evidence Pack completion | Evidence before interpretation; no immediate investigation path; Critical cases get fast Evidence Packs via immediate collection | TASK-126 triggers on Evidence Pack completion event, not on BugCase creation |
| 2026-06-16 | Phase B blocked until 3 real Evidence Packs pass manual review | Prevents over-specifying Investigation layer before seeing actual collected evidence | Phase A Exit Gate is a hard dependency for TASK-124 |

---

## Discovered Work

| Ticket | Title | Reason Created | Status |
|--------|-------|----------------|--------|
| TASK-121A | Collect LLM Trace and Cost Evidence | LLM activity is primary evidence for cost-control failures; llm_traces is single source of truth | 🔲 OPEN |

---

## Session Log

### Session 1 (2026-06-16) — Design complete

Pre-sprint design session produced:
- Updated architecture doc (`00-core-system-architecture-v2.md`) with three new permanent principles, Investigation Consumer Hierarchy, Quality Standard, Failure Taxonomy, Truncation Policy, and Closed-Loop Learning sections
- Updated Sprint 021 interface doc (`20-sprint-021-evidence-investigation-interface-v2.md`) resolving all deferred open questions
- Golden Incident selection: BUG-064 (Memory Leak + Retry Storm)
- Hand-written Evidence Pack for BUG-064 revealing missing Configuration Evidence collector
- Golden Investigation for BUG-064 (`golden-investigation-bug-064.md`) as InvestigationProvider target
- All Phase A tickets written and ready for implementation

### Session 2 (2026-06-16) — Phase A finalized

Post-design decisions locked:
- Default Investigation model: DeepSeek, operation name `bugops_investigation`, gateway routing required
- Evidence Packs retained permanently
- Investigations generated only after Evidence Pack completion — no immediate investigation path
- Phase B blocked until Phase A Exit Gate passed
- TASK-121A added: LLM Trace and Cost Evidence collector
- `llm_traces` field names confirmed: `timestamp` (not `created_at`), `cost` (not `cost_usd`)
- Seven total Phase A collectors: metrics, system state, related cases, deploy context, config evidence, LLM traces, Railway logs

### Session 3 (2026-06-17) — TASK-114 Implementation Complete

TASK-114 (Define EvidencePack model and schema) implemented and locked:
- ✅ EvidencePackCreate and EvidencePack models defined in src/crypto_news_aggregator/bugops/models.py
- ✅ Nested models added: CollectionError, LogExcerptSection, SectionMetrics
- ✅ LLMTraceRecord and LLMTraceSummary (first-class, typed) for cost-control failure diagnosis
- ✅ EvidenceReferenceAllocator for collision-free evidence reference IDs (E-001, E-002...)
- ✅ Full validators for root_subsystem, severity, blast_radius against enums
- ✅ 34 comprehensive tests (timestamp defaults, allocator sequencing, partial pack handling, ref-allocator integration, MongoDB serialization)
- ✅ Zero regressions: 214 total BugOps tests passing (180 existing + 34 new)
- ✅ Schema locked for BUG-064 cost-control failure diagnosis (llm_trace_summary.total_cost, operation_breakdown, config_evidence.critical_operations)
- Commit: d2109c8
- Five critical TASK-114A production-compatibility lockdown points documented in memory (llm_traces field matching, operation_breakdown structure, healthy_signals typing, sections_missing/collection_errors clarity, allocator framework integration)

### Session 4 (2026-06-18) — TASK-114A Schema Review Complete

TASK-114A (EvidencePack schema review against BUG-064) completed:
- ✅ All 11 evidence references (E-001 through E-011) from Golden Investigation mapped to schema fields
- ✅ Schema mapping document created: `docs/sprints/sprint-021/design-artifacts/evidence-pack-bug064-schema-mapping.md`
- ✅ One schema gap found and fixed: LogExcerptSection.window_start and window_end changed to Optional
- ✅ Rationale: Window boundaries are desirable metadata but not required; collectors populate when available
- ✅ Verification: All evidence types (cost control metrics, retry patterns, errors, deployment health, infrastructure health) fully representable
- ✅ Tests: 79 passed, no regressions (pytest tests/bugops/ -k "not alert_to_case and not monitor and not slack")
- Commits: 6fb26ad (schema + mapping), fc2e234 (ticket completion)
- Schema locked and ready for Phase A collector implementation (TASK-115 onwards)

### Session 5 (2026-06-19) — TASK-115 Persistence Layer Complete

TASK-115 (Implement EvidencePack persistence) implemented and locked:
- ✅ EvidencePack MongoDB collection added to BugOpsStore with 5 store methods
- ✅ `create_evidence_pack`: Insert and return with normalized ObjectId
- ✅ `get_evidence_pack` / `get_evidence_pack_for_case`: Retrieve by pack_id or bugcase_id
- ✅ `update_evidence_pack_section`: Section-by-section updates with MongoDB dot-notation merge semantics
  - evidence_references field never replaced; collectors merge their refs (E-001/E-002 then E-003/E-004 = all four preserved)
  - Other fields updated directly (last writer wins)
- ✅ `mark_evidence_pack_complete`: Fetches stored pack, checks collection_errors and sections_missing, sets status (COMPLETE vs PARTIAL)
- ✅ Six new config keys added: BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES, BUGOPS_LOG_WINDOW_MINUTES, BUGOPS_LOG_LINE_CAP, BUGOPS_EVIDENCE_MAX_TOTAL_CHARS, BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS, RAILWAY_API_TOKEN
- ✅ MongoDB indexes wired into existing db/mongodb.py initialization path (not orphaned):
  - pack_id (unique) for deduplication
  - bugcase_id for case lookup
  - collection_status for filtering by completion state
  - created_at (descending) for time-based queries
- ✅ 14 comprehensive tests (create, retrieve, partial updates, reference merging, status logic)
- ✅ 62 total BugOps tests passing (14 new + 48 existing); no regressions
- Commit: 986ec0f
- Persistence foundation locked for Phase A collector implementation (TASK-116 onwards)

### Session 6 (2026-06-19) — TASK-116 Framework Complete

TASK-116 (Implement EvidenceCollector framework) implemented and locked:
- ✅ `EvidenceCollectorBase` protocol at `bugops/evidence/base.py` — interface contract
- ✅ `EvidenceCollector` orchestrator class at `bugops/evidence/collector.py`:
  - `is_eligible(bugcase)`: Checks not manually closed, no existing pack, settling window elapsed OR Critical
  - `collect(bugcase)`: Main entry point — creates pack, runs collectors in isolation, marks complete
  - `_is_settling_window_elapsed()`: Window logic — Critical collects immediately, 10m default for others
  - `_generate_pack_id()`: Pack ID format `ep_{case_id}_{unix_timestamp}`
  - `register_collector()`: Register collectors during initialization
- ✅ Collector isolation: Each collector runs in independent try/except, one failure ≠ halt
- ✅ CollectionError recording: Per-collector failures captured, not propagated
- ✅ Settling window: Resolved BugCases ARE eligible if window elapsed and no pack exists
- ✅ 20 comprehensive tests covering all 12 acceptance criteria:
  - Eligibility: closed, existing pack, window not elapsed, window elapsed, Critical, Resolved
  - Collection: pack creation, collector execution, isolation, error recording, completion, zero collectors
  - Settling window: Critical, no first_seen, after window, before window
  - Pack ID generation and collector registration
- ✅ 77 total core tests passing (20 new + 57 existing store/model tests); no regressions
- Commit: e3ac564
- Framework ready for Phase A collector implementation (TASK-117 onwards) — all 7 collectors can now register and run
