# Sprint 13 — LLM Control + Attribution Layer

**Status:** In Progress
**Started:** 2026-04-08
**Target:** Unify all LLM calls behind a single gateway, achieve full cost attribution, and identify the primary cost driver with measured data.

---

## Sprint Goal

Backdrop burns $2.50-5/day in Anthropic credits vs a $0.33/day target because 2 of 4 API call sites bypass the spend cap entirely. This sprint builds a single LLM gateway that all calls must flow through, instruments every call with structured tracing, and runs a 48-hour burn-in to produce a data-driven cost attribution report. No optimization guesses — decisions come from measured data.

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| 1 | TASK-036 | LLM Gateway — Single Entry Point | ✅ MERGED | high | ~1.5h |
| 2 | TASK-037 | Tracing Schema — llm_traces Collection | ✅ MERGED | low | ~0.5h |
| 3 | TASK-038 | Wire briefing_agent.py Through Gateway | ✅ MERGED | high | ~1.5h |
| 4 | TASK-039 | Wire health.py Through Gateway | ✅ MERGED | low | ~1.5h |
| 5 | TASK-040 | Dataset Capture — Pre/Post Refine Drafts | ✅ MERGED | medium | ~2.5h |
| 6 | TASK-042 | Gateway Bypass Fix — Wire Remaining LLM Calls | ✅ MERGED | low | ~0.5h |
| 7 | TASK-041A | Restart 48-Hour Burn-in with Clean Baseline | ✅ MERGED | low | ~0.25h |
| 8 | TASK-041B | Analyze Burn-in + Write Findings Doc | ⏳ WAITING | low | |

---

## Success Criteria

- [ ] Zero direct httpx calls to api.anthropic.com outside `llm/gateway.py`
- [ ] Every LLM call produces a trace record in `llm_traces` with operation tag, cost, tokens, and latency
- [ ] Spend cap enforces on all 4 call sites (briefing_agent, anthropic.py, optimized_anthropic.py, health.py)
- [ ] 48-hour burn-in completes with daily spend at or below $0.33
- [ ] Findings doc delivered with per-operation cost attribution and an optimization decision

---

## Key Decisions

- **Gateway has async + sync modes** — `call()` for async contexts (briefing_agent, enrichment pipeline), `call_sync()` for sync contexts (twitter_service, Celery tasks). One class, one enforcement point, two execution paths.
- **Spend cap breach kills the briefing** — gateway raises `LLMError`, no silent fallback. Briefing generation aborts cleanly.
- **Health endpoint returns "degraded" on spend cap** — not "error". UptimeRobot sees the system is alive but cost-limited.
- **Eval schema now, enforcement later** — `quality` placeholder fields in trace records. Sprint 14 activates them.
- **Data-driven optimization** — no pre-commitment to killing the refine loop or downgrading models until burn-in data confirms the cost driver.
- **NeMo/Langfuse deferred** — gateway + MongoDB tracing is the source of truth for Sprint 13. Langfuse is an optional UI layer for later.

---

## Discovered Work

_Tickets created mid-sprint for issues found during implementation._

---

## Session Log

### Session 1 (2026-04-08) — Sprint Planning ✅
**Sprint 13 planning + ticket creation**
- Reviewed all 6 source files: anthropic.py, optimized_anthropic.py, cost_tracker.py, briefing_agent.py, factory.py, health.py, __init__.py
- Confirmed 4 API call sites, 2 unmetered (briefing_agent, health)
- Confirmed config: LLM_DAILY_SOFT_LIMIT=0.25, LLM_DAILY_HARD_LIMIT=0.33
- Confirmed sync callers still live (twitter_service, Celery tasks) — gateway needs both async + sync
- Resolved gateway design: async core + sync wrapper, not pure async
- Created 6 tickets (TASK-036 through TASK-041) with full implementation notes and code skeletons

### Session 2 (2026-04-08) — TASK-036 Implementation ✅
**LLM Gateway foundation complete**
- Implemented `src/crypto_news_aggregator/llm/gateway.py` (330 lines)
- `GatewayResponse` dataclass with structured return: text, tokens, cost, model, operation, trace_id
- Async `call()` for briefing_agent, enrichment pipeline — full budget check → API call → cost track → trace write flow
- Sync `call_sync()` for twitter_service, Celery tasks — defers trace writes (sync can't do async MongoDB)
- Budget enforcement: `check_llm_budget()` check before API call, raises `LLMError` on hard/soft breach
- Cost tracking: integrated with existing `CostTracker.track_call()`
- Traces: fire-and-forget writes to `llm_traces` collection (don't block LLM calls)
- Module singleton: `get_gateway()` for global access
- Unit tests: 18 tests covering init, budget checks, headers/payload, response parsing, async calls, sync calls, errors, singleton
- Commit: 72a15f4 — Ready for TASK-037 (tracing schema + indexes)

### Session 3 (2026-04-08) — TASK-037 Implementation ✅
**Tracing schema + indexes complete**
- Implemented `src/crypto_news_aggregator/llm/tracing.py` (57 lines)
- `ensure_trace_indexes()` — creates timestamp (TTL 30d), operation, and (operation, timestamp) compound indexes
- `get_traces_summary()` — aggregation pipeline for cost/tokens/duration grouping by operation (used by TASK-041 burn-in)
- Wired indexes into app startup via `main.py` lifespan
- Trace document schema validated: trace_id, operation, timestamp, model, tokens, cost, duration_ms, error, quality placeholders
- Unit tests: 4 tests (index creation, document shape, aggregation, time filtering) — all passing
- Commit: b6a60bd — Ready for TASK-038 (wire briefing_agent through gateway)

### Session 4 (2026-04-08) — TASK-037 CI/CD Fixes + Merge ✅
**Fixed CI/CD test failures + merged TASK-037 PR**
- Issue: `test_broken` job in CI missing environment variables and MongoDB URI misconfiguration
- Commit 58fe993: Added NEWS_API_KEY, API_KEYS, TESTING, CELERY_* vars to test_broken job
- Commit 7990230: Fixed MONGODB_URI to include database name (`/crypto_news`) in both jobs
- All tracing tests passing locally (4/4)
- PR merged to main
- Status: Moving to TASK-038 (wire briefing_agent through gateway)

### Session 5 (2026-04-08) — TASK-038 & TASK-039 & TASK-040 Implementation ✅
**Wire briefing_agent.py, health.py through gateway + dataset capture**

**TASK-038: Wire briefing_agent through gateway**
- Removed httpx, replaced with gateway.call()
- Added distinct operation tags: `briefing_generate`, `briefing_critique`, `briefing_refine`
- Spend cap breach kills briefing cleanly (no retry)
- Model fallback preserved: Sonnet → Haiku on 403
- Commit: c2976c0

**TASK-039: Wire health endpoint through gateway**
- Spend cap breach returns "degraded" status (not "error")
- UptimeRobot sees system is alive but cost-limited
- Commit: 67aff33

**TASK-040: Dataset capture for eval datasets**
- Created `src/crypto_news_aggregator/llm/draft_capture.py` (55 lines)
- Saves GeneratedBriefing snapshots at each stage with trace_id linkage
- Integrated into briefing_agent pipeline
- Non-blocking observability (catches errors, doesn't raise)
- Commit: 7208fa7

**All merged to main, deployed to Railway with $6 Anthropic credits**

### Session 6 (2026-04-08) — TASK-041 Initial Burn-in Monitoring Setup ✅
**48-hour attribution run begins (later halted due to incomplete instrumentation)**
- Verified llm_traces collection is ready (0 records, awaiting first pipeline run)
- Created `/scripts/analyze_burn_in.py` for post-burn-in data analysis
- Created `/docs/sprint-13-burn-in-status.md` tracking doc
- Branch: `feat/task-041-burn-in-setup` (commit a5689c5)
- System actively collecting: cost by operation, model, refine iterations, error rates
- **⚠️ Note:** This measurement was later discovered to be incomplete (see Session 7)

### Session 7 (2026-04-08) — Gateway Bypass Discovery + TASK-042 Fix 🚨 CRITICAL
**Burn-in audit revealed incomplete instrumentation — fixed all 3 bypass points**

**Discovery phase:**
- Code review found 3 bypass points making direct API calls to api.anthropic.com:
  1. `narrative_themes.py` (4 call sites: lines 485, 864, 1015, 1388) — theme extraction, narrative generation, actor/tension clustering
  2. `optimized_anthropic.py` (line 32) — entity extraction via selective_processor, twitter_service
  3. `anthropic.py` (line 22) — fallback provider in factory.py
- Impact: Estimated 40-60% of actual spend was invisible to initial TASK-041 measurement (narrative enrichment is expensive)
- **Decision:** Halt burn-in, fix bypasses, restart with clean data

**Fix phase (TASK-042):**
- **narrative_themes.py:** Routed 4 call sites through `gateway.call()` with operation tags
  - `extract_themes_from_article` → `narrative_theme_extract`
  - `generate_narrative_from_theme` → `narrative_generate`
  - `cluster_by_narrative_salience` → `actor_tension_extract`
  - `generate_narrative_from_cluster` → `cluster_narrative_gen`
- **optimized_anthropic.py:** Refactored `_make_api_call()` to use `gateway.call_sync()`
- **anthropic.py:** Converted direct httpx calls to `gateway.call_sync()`
- **Audit:** Zero direct `api.anthropic.com` calls remain in main app code ✅
- **Commit:** 4f44203 — fix(llm): Wire all remaining LLM calls through gateway (TASK-042)
- **Status:** TASK-042 ✅ MERGED, TASK-041 unblocked

### Session 8 (2026-04-08) — TASK-041A Restart Burn-in with Clean Baseline ⏳ IN PROGRESS
**Clear incomplete traces, restart 48-hour measurement with full instrumentation**

**Burn-in restart (TASK-041A):**
- Cleared `llm_traces` collection (removed incomplete data from Session 6)
- Restarted 48-hour measurement from clean baseline
- All 8 LLM call sites now instrumented:
  - `briefing_generate`, `briefing_critique`, `briefing_refine` (briefing_agent.py)
  - `narrative_theme_extract`, `narrative_generate`, `actor_tension_extract`, `cluster_narrative_gen` (narrative_themes.py)
  - `entity_extract` (optimized_anthropic.py via selective_processor, twitter_service)
  - `health_check` (health.py)
- Measurement window: **2026-04-08 ~XX:XX UTC → 2026-04-10 ~XX:XX UTC** (48 hours)
- **Status:** Burn-in actively collecting data with complete visibility

**Next action:**
- Wait 48 hours for data collection
- 2026-04-10 ~XX:XX UTC: Run `poetry run python scripts/analyze_burn_in.py` → analyze cost by operation
- Write `/docs/sprint-13-burn-in-findings.md` with recommendations (TASK-041B)

### Session 8 (2026-04-08) — TASK-041A Restart Complete ✅
**Burn-in restarted with clean baseline and full instrumentation**

**Completed:**
- ✅ Cleared llm_traces collection: 1 incomplete record deleted
- ✅ Verified empty state: `countDocuments({})` returns 0
- ✅ Updated `/docs/sprint-13-burn-in-status.md` with restart notes and TASK-042 context
- ✅ Fresh 48-hour measurement window active with all 8 LLM operations instrumented

**Measurement starts now (2026-04-08):**
- Briefing operations: `briefing_generate`, `briefing_critique`, `briefing_refine`
- Narrative operations: `narrative_theme_extract`, `narrative_generate`, `actor_tension_extract`, `cluster_narrative_gen`
- Entity extraction: via optimized_anthropic.py gateway calls
- Health check: via health.py gateway calls

**Next checkpoint:** 2026-04-10 20:00 UTC (run analyze_burn_in.py, write findings doc)