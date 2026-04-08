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
| 3 | TASK-038 | Wire briefing_agent.py Through Gateway | 🔲 OPEN | high | |
| 4 | TASK-039 | Wire health.py Through Gateway | 🔲 OPEN | low | |
| 5 | TASK-040 | Dataset Capture — Pre/Post Refine Drafts | 🔲 OPEN | medium | |
| 6 | TASK-041 | Attribution Burn-in (48hr) + Findings Doc | 🔲 OPEN | low | |

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