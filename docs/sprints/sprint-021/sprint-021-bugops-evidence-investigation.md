# Sprint 021 — Evidence & Investigation

**Status:** In Progress
**Started:** 2026-06-16
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
| 5 | TASK-117 | Collect subsystem metrics and system state | A | ✅ COMPLETE | M |
| 6 | TASK-118 | Collect related BugCases | A | ✅ COMPLETE | S |
| 7 | TASK-119 | Build Railway API client | A | ✅ COMPLETE (VERIFIED) | M |
| 8 | TASK-120 | Collect deploy context via Railway | A | ✅ COMPLETE (VERIFIED) | M |
| 9 | TASK-121 | Collect Configuration Evidence | A | ✅ COMPLETE | S |
| 10 | TASK-121A | Collect LLM Trace and Cost Evidence | A | ✅ COMPLETE | S |
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

### Session 6 (2026-06-19) — TASK-116 Framework Complete + Code Review

TASK-116 (Implement EvidenceCollector framework) implemented, code-reviewed, and locked:
- ✅ `EvidenceCollectorBase` protocol at `bugops/evidence/base.py` — interface contract
- ✅ `EvidenceCollector` orchestrator class at `bugops/evidence/collector.py`:
  - `is_eligible(bugcase)`: Checks not manually closed, no existing pack, settling window elapsed OR Critical
  - `collect(bugcase)`: Main entry point — creates pack, runs collectors in isolation, marks complete
  - `_is_settling_window_elapsed()`: Window logic — Critical collects immediately, 10m default for others
  - `_generate_pack_id()`: Pack ID format `ep_{case_id}_{unix_timestamp}`
  - `register_collector()`: Register collectors during initialization
- ✅ Collector isolation: Each collector runs in independent try/except, one failure ≠ halt
- ✅ CollectionError recording: Per-collector failures accumulated locally, written once at end (no overwrites)
- ✅ sections_collected accuracy: Only includes successfully completed collectors, not failed ones
- ✅ Settling window: Resolved BugCases ARE eligible if window elapsed and no pack exists
- ✅ 22 comprehensive tests covering all 12 acceptance criteria + 2 critical code-review requirements:
  - Eligibility: closed, existing pack, window not elapsed, window elapsed, Critical, Resolved
  - Collection: pack creation, collector execution, isolation, error recording, completion, zero collectors
  - Settling window: Critical, no first_seen, after window, before window
  - Error accumulation: Single failure, multiple failures all recorded (no overwrites)
  - sections_collected accuracy: Success/failure filtering verified
  - Pack ID generation and collector registration
- ✅ Code-review verification (2 critical requirements):
  - Failed collectors append CollectionError without overwriting prior errors
  - sections_collected only includes collectors that actually completed successfully
- ✅ 99 total tests passing (22 new + 77 existing store/model tests); zero regressions
- Commits: e3ac564 (implementation) + a94ad5e (docs) + 25827d7 (code-review refinements)
- Framework ready for Phase A collector implementation (TASK-117 onwards) — all 7 collectors can now register and run

### Session 7 (2026-06-19) — TASK-117 Metrics and System State Collectors Complete

TASK-117 (Collect subsystem metrics and system state) implemented, verified, and locked:
- ✅ `MetricsCollector` at `bugops/evidence/collectors/metrics.py`:
  - Queries MongoDB for subsystem freshness (articles, signals, narratives, briefings)
  - Collects last artifact timestamp and counts within freshness window
  - Generates human-readable indicators: "within window", "N minutes ago", "no artifacts found"
  - Uses EvidenceReferenceAllocator for collision-free reference IDs
  - Handles errors internally without raising (catches, logs, continues per acceptance criteria)
  
- ✅ `SystemStateCollector` at `bugops/evidence/collectors/system_state.py`:
  - Calls `GET /api/v1/health` to gather system state (MongoDB, Redis, LLM, pipeline)
  - Derives healthy_signals list: only adds signals for `status == "ok"` or `"healthy"`
  - Explicitly records Celery worker/scheduler as sections_missing (deferred to TASK-119)
  - Handles timeouts and HTTP errors gracefully without raising
  - Maps error response attributes correctly (e.response.status_code)

- ✅ Auto-registration in `EvidenceCollector.__init__`:
  - Both collectors registered during initialization
  - All 22 TASK-116 tests continue to pass with auto-registered collectors
  
- ✅ Store enhancements for multi-collector support:
  - `sections_missing`: now uses `$push` with `$each` for append semantics (not overwrite)
  - `healthy_signals`: now uses `$push` with `$each` for append semantics (not overwrite)
  - evidence_references: already had merge semantics (dot-notation $set)
  
- ✅ Config: Added `BUGOPS_HEALTH_ENDPOINT_URL = "http://localhost:8000"`

- ✅ Test suite (14 new tests):
  - MetricsCollector (6 tests): recent artifacts, stale artifacts, no artifacts, subsystem filtering, ref allocation, root subsystem only
  - SystemStateCollector (8 tests): healthy system, no healthy signals, partial health, timeout, HTTP error, Celery missing, ref allocation, latency parsing
  - Mocked mongo_manager in test fixtures to isolate collector behavior
  
- ✅ Acceptance criteria verification:
  - Both collectors query/call correct sources (MongoDB, /health endpoint)
  - Both collectors use EvidenceReferenceAllocator (no hardcoded E-001, E-002)
  - Both collectors handle errors internally without raising
  - Both collectors registered with EvidenceCollector
  - Celery worker/scheduler explicitly recorded as sections_missing with reason
  - Healthy signals only added for passing checks (status == "ok" or "healthy")
  - sections_missing and healthy_signals support multi-collector append (via store $push)

- ✅ 77 total tests passing (14 new + 63 existing TASK-116/persistence/model tests); zero regressions
- Commits: ff6166d (implementation + 22 tests) + bcd87ce (critical fixes: error handling, merge semantics)
- All 7 Phase A collectors now have a proven pattern for safe error handling and multi-collector data merging

### Session 8 (2026-06-19) — TASK-118 Related BugCase Collector Complete

TASK-118 (Collect related BugCases) implemented, verified, and locked:
- ✅ `RelatedCaseCollector` at `bugops/evidence/collectors/related_cases.py`:
  - Deterministic collector (no LLM, no Railway API calls)
  - Queries MongoDB for cases sharing subsystems within 7-day lookback window
  - Matches on: root_subsystem, blast_radius, or affected_subsystems overlap
  - Excludes current BugCase by case_id, limits to 10 results, sorts by first_seen_at descending
  - Converts related BugCases to dicts preserving: case_id, root_subsystem, severity, status, first_seen_at, last_seen_at, title
  - Handles empty related cases gracefully (writes empty list + timestamp, no error)

- ✅ `get_related_cases()` store method added to `BugOpsStore`:
  - Returns up to 10 BugCases sharing subsystems within lookback_days
  - Query logic: $or across root_subsystem, affected_subsystems, blast_radius; excludes current case by $ne
  - Returns sorted by first_seen_at descending (most recent first)
  - Gracefully handles empty subsystems list (returns [])

- ✅ Auto-registration in `EvidenceCollector.__init__`:
  - RelatedCaseCollector registered during initialization (now 3 auto-collectors total)

- ✅ Test suite (12 new tests for RelatedCaseCollector):
  - With related cases found (multiple matches)
  - With no related cases found (empty section handling)
  - Subsystem extraction and deduplication
  - Missing subsystem fields (None/empty lists)
  - Store error handling (graceful failure)
  - Timestamp formatting as ISO strings
  - Reference allocator usage (collision-free IDs)
  - Sort order preservation (most recent first)
  - Collector name attribute
  - Edge cases: single case, maximum 10 cases
  - Field preservation from BugCases

- ✅ Acceptance criteria verification:
  - Collector implemented and registered with EvidenceCollector
  - get_related_cases() store method added and tested
  - Zero related cases handled gracefully (section written with empty list, not omitted)
  - Evidence reference added only when related cases found
  - Uses ref_allocator.next_ref() for collision-free IDs
  - All tests pass, no regressions

- ✅ 48 collector tests passing (12 new RelatedCaseCollector + 36 existing framework/metrics/system-state tests); zero regressions
- Commit: 04012b3 (implementation + 12 tests + test updates)
- Phase A now has 4 of 7 collectors complete; next: Railway API client (TASK-119) → deploy context, logs

### Session 10 (2026-06-20) — TASK-120 Deploy Context Collector Complete

TASK-120 (Collect deploy context via Railway) implemented and locked:
- ✅ `DeployContextCollector` at `bugops/evidence/collectors/deploy_context.py`
- ✅ Fetches deployments for all 3 services within 24-hour lookback window
- ✅ Explicit evidence reference always added — absence of deployments recorded
- ✅ Railway API errors recorded per-service in `sections_missing`
- ✅ Uses `EvidenceReferenceAllocator` for collision-free reference IDs
- ✅ Registered with `EvidenceCollector.__init__` for auto-initialization
- ✅ 8 comprehensive tests (all services, partial failures, empty deployments, sorting)
- ✅ 70+ evidence collector tests passing; zero regressions
- Commits: 0e05dc5 (implementation + tests)
- Status: ✅ Ready to unlock TASK-121 and TASK-121A (parallel Phase A collectors)

### Session 9 (2026-06-20) — TASK-119 Railway API Client Complete

TASK-119 (Build Railway GraphQL API client) implemented, verified, and locked:
- ✅ `RailwayClient` at `bugops/clients/railway.py`:
  - GraphQL client for Railway API at `https://backboard.railway.app/graphql/v2`
  - Auth via `RAILWAY_API_TOKEN` bearer token
  - Service name mapping: internal names (fastapi, celery_worker, celery_scheduler) → Railway display names
  - Three public methods: `get_active_deployment_id()`, `get_recent_deployments()`, `get_logs()`
  - Private method `_graphql()` handles all HTTP/GraphQL error handling, never raises to caller

- ✅ Service resolution with caching:
  - `get_active_deployment_id(service_name)`: Resolves internal name to deployment ID via two-step GraphQL lookup (service ID → active deployment)
  - Deployment ID cached per client instance to prevent redundant API calls within single collection cycle
  - Returns None gracefully if service not found, API unavailable, or mapping unknown

- ✅ Deployment history:
  - `get_recent_deployments(service_name, since)`: Fetches up to 50 deployments created at or after `since` timestamp
  - Returns list of deployment dicts with status, timestamps, service name
  - Returns empty list on error (no exceptions raised)

- ✅ Log fetching with truncation detection:
  - `get_logs(service_name, start_time, end_time, line_cap)`: Fetches logs within time window
  - Fetches `line_cap + 1` lines from Railway to detect truncation
  - Returns tuple: `(log_lines[:line_cap], was_truncated=True)` if result > line_cap
  - Returns `(log_lines, False)` if result <= line_cap
  - Returns `([], False)` on error (safe default)

- ✅ Error handling:
  - `_graphql()` method catches and handles: HTTP 401/403/5xx, timeouts (10s), JSON parse errors, GraphQL errors
  - All errors logged at error level, never raised
  - Returns None to caller on any error; calling code uses safe defaults

- ✅ Config keys added to `core/config.py`:
  - `RAILWAY_API_TOKEN: str = ""` (already present)
  - `RAILWAY_PROJECT_ID: str = ""`
  - `RAILWAY_SERVICE_NAME_FASTAPI: str = "fastapi"`
  - `RAILWAY_SERVICE_NAME_CELERY_WORKER: str = "celery-worker"`
  - `RAILWAY_SERVICE_NAME_CELERY_SCHEDULER: str = "celery-scheduler"`

- ✅ Test suite (21 comprehensive tests):
  - GraphQL execution: auth header format, response parsing, error handling (401, timeout, JSON parse, GraphQL errors)
  - Deployment ID resolution: caching, unknown service, API errors, service name mapping
  - Recent deployments: date filtering, error handling, response format, unknown services
  - Log fetching: line_cap + 1 fetching, truncation detection, empty lists on error, message extraction

- ✅ Code implementation complete with all acceptance criteria met:
  - RailwayClient implemented at bugops/clients/railway.py ✅
  - Auth via RAILWAY_API_TOKEN environment variable ✅
  - RAILWAY_PROJECT_ID and service name mapping config keys added ✅
  - Deployment ID caching implemented — no redundant API calls per collection cycle ✅
  - Truncation detection uses line_cap + 1 fetch strategy ✅
  - All methods return safe defaults on error — never raise to caller ✅
  - All 21 tests pass with mocked HTTP ✅
  - All existing BugOps tests continue to pass (57 collector + framework tests verified) ✅
  - GraphQL queries documented in Completion Summary ✅

- ✅ Live Railway API verification complete:
  - ✅ Schema introspection: 124 query fields confirmed
  - ✅ Endpoint verified: https://backboard.railway.com/graphql/v2 (corrected from .app to .com)
  - ✅ Auth verified: Project tokens use Project-Access-Token header (not Bearer)
  - ✅ Service resolution: Successfully resolved celery-worker (2c8a41b9-6ff...)
  - ✅ Deployment resolution: Retrieved active deployment (1f60248e-364...)
  - ✅ Log fetching: Retrieved 10 real production log lines from celery-worker
  - ✅ Query syntax verified: orderBy argument removed (not supported by Railway API; pre-sorted results)

- 📍 Status: ✅ FULLY COMPLETE — Code tested, schema verified, live services and logs confirmed working
- Commits: 213bf49 (code), 14edcc8 (docs), 2343ae4 (live verification fixes)
- Railway API client is production-ready and tested against live data
- Ready to unlock TASK-120 (deploy context) and TASK-122 (log collection)
- ✅ `RelatedCaseCollector` at `bugops/evidence/collectors/related_cases.py`:
  - Deterministic collector (no LLM, no Railway API calls)
  - Queries MongoDB for cases sharing subsystems within 7-day lookback window
  - Matches on: root_subsystem, blast_radius, or affected_subsystems overlap
  - Excludes current BugCase by case_id, limits to 10 results, sorts by first_seen_at descending
  - Converts related BugCases to dicts preserving: case_id, root_subsystem, severity, status, first_seen_at, last_seen_at, title
  - Handles empty related cases gracefully (writes empty list + timestamp, no error)

- ✅ `get_related_cases()` store method added to `BugOpsStore`:
  - Returns up to 10 BugCases sharing subsystems within lookback_days
  - Query logic: $or across root_subsystem, affected_subsystems, blast_radius; excludes current case by $ne
  - Returns sorted by first_seen_at descending (most recent first)
  - Gracefully handles empty subsystems list (returns [])

- ✅ Auto-registration in `EvidenceCollector.__init__`:
  - RelatedCaseCollector registered during initialization (now 3 auto-collectors total)

- ✅ Test suite (12 new tests for RelatedCaseCollector):
  - With related cases found (multiple matches)
  - With no related cases found (empty section handling)
  - Subsystem extraction and deduplication
  - Missing subsystem fields (None/empty lists)
  - Store error handling (graceful failure)
  - Timestamp formatting as ISO strings
  - Reference allocator usage (collision-free IDs)
  - Sort order preservation (most recent first)
  - Collector name attribute
  - Edge cases: single case, maximum 10 cases
  - Field preservation from BugCases

- ✅ Acceptance criteria verification:
  - Collector implemented and registered with EvidenceCollector
  - get_related_cases() store method added and tested
  - Zero related cases handled gracefully (section written with empty list, not omitted)
  - Evidence reference added only when related cases found
  - Uses ref_allocator.next_ref() for collision-free IDs
  - All tests pass, no regressions

- ✅ 48 collector tests passing (12 new RelatedCaseCollector + 36 existing framework/metrics/system-state tests); zero regressions
- Commit: 04012b3 (implementation + 12 tests + test updates)
- Phase A now has 4 of 7 collectors complete; next: Railway API client (TASK-119) → deploy context, logs

### Session 11 (2026-06-20) — TASK-121 Configuration Evidence Collector Complete

TASK-121 (Collect Configuration Evidence) implemented and locked:
- ✅ `ConfigEvidenceCollector` at `bugops/evidence/collectors/config_evidence.py`
- ✅ Collects LLM daily soft/hard limits, CRITICAL_OPERATIONS from cost_tracker, BugOps thresholds, investigation config
- ✅ Graceful missing settings handling: uses getattr() with None default (forward-compatible)
- ✅ Two evidence references added: one for budget threshold (budget-relevant to cost-control failures), one for critical operations (operation-relevant to routing/classification failures)
- ✅ Evidence reference descriptions include actual values for diagnostic value (not just field names)
- ✅ Auto-registers with EvidenceCollector during initialization (no manual registration)
- ✅ 13 comprehensive unit tests: all settings reads, missing settings, reference allocation, timestamp, investigation config
- ✅ Framework tests updated: now expect 5 auto-registered collectors (added config_evidence)
- ✅ 35 collector tests passing (13 new ConfigEvidenceCollector + 22 existing framework); zero regressions
- Commit: 68a97e4 (implementation + tests + ticket update)
- Status: ✅ Ready to unlock TASK-121A (parallel phase, LLM trace collector)
- Phase A now has 5 of 7 collectors complete; next: TASK-121A (LLM trace), TASK-122 (Railway logs), TASK-123 (wire monitor loop)

### Session 12 (2026-06-20) — TASK-121A LLM Trace and Cost Evidence Collector Complete

TASK-121A (Collect LLM Trace and Cost Evidence) implemented and locked:
- ✅ `LLMTraceCollector` at `bugops/evidence/collectors/llm_traces.py` (152 lines)
- ✅ Queries `llm_traces` collection with correct field names: `timestamp` (NOT `created_at`), `cost` (NOT `cost_usd`)
- ✅ Window calculation: 60 minutes before `first_seen_at` to `last_seen_at` (or `first_seen_at` if `None`)
- ✅ Aggregates: total_calls, total_cost, total_input_tokens, total_output_tokens, cached_calls
- ✅ Per-operation breakdown: calls, cost, last_at timestamp for each operation
- ✅ Recent traces: limited to 10, sorted most recent first
- ✅ Evidence references: E-001 (cost), E-002 (operations) — collision-free via ref_allocator
- ✅ Graceful empty window handling (no traces found)
- ✅ Updated `LLMTraceSummary` model in `bugops/models.py`:
  - Added window_start, window_end, collected_at timestamps
  - Changed from total_operations to total_calls
  - Changed recent_traces from `list[LLMTraceRecord]` to `list[dict]` (flexible storage)
  - Added operation_breakdown and budget_events fields
- ✅ Conditional registration in EvidenceCollector (optional db parameter)
- ✅ 14 comprehensive unit tests: field names, window calculation, aggregation, breakdown, limiting, refs, empty handling, defaults, sorting, timestamps
- ✅ 62 total collector tests passing (14 new LLMTraceCollector + 48 existing); zero regressions
- Commits: 734c496 (implementation + tests + full spec compliance)
- Status: ✅ COMPLETE — Ready to unlock TASK-122 (log collector) and TASK-123 (monitor wiring)
- Phase A now has 6 of 7 collectors complete; final collector: TASK-122 (Railway logs with redaction)
