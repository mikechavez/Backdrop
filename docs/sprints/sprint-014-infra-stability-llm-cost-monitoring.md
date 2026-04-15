# Sprint 14 — Infrastructure Stability + LLM Cost Monitoring

**Status:** CLOSED
**Start:** 2026-04-11
**End:** 2026-04-14
**Sprint Goal:** Fix critical briefing bugs, validate scheduled briefing execution, measure actual LLM costs, establish sustainable infrastructure baseline.

---

## Goal Assessment

**Partial completion.** Briefing bugs are fixed and verified. Scheduled briefing execution is confirmed working — 2 runs on 2026-04-14 (morning + evening), correct content, correct model, correct costs. The cost measurement work revealed the infrastructure is not yet at a sustainable baseline. Daily spend is $1.13 against a $1.00 hard limit, and the hard limit is not triggering because the budget enforcement system has a blind spot (BUG-079). The technical foundation is solid; cost stability is not achieved.

---

## Completed

- **BUG-064:** Memory leak + retry storm — MERGED
- **BUG-065:** Briefing soft limit incorrectly triggered — MERGED
- **BUG-066:** Daily cost calculation (rolling 24h vs calendar day) — CODE COMPLETE
- **BUG-067:** Motor AsyncIOMotorDatabase truthiness check — CODE COMPLETE
- **BUG-068:** Double cost tracking (OptimizedAnthropicLLM duplicate) — CODE COMPLETE
- **BUG-069:** Briefing persistence (empty documents) — FIXED & VERIFIED
- **BUG-070:** Narrative tier-1 only filter — VERIFIED WORKING
  - Articles confirm Tier 1: 53, Tier 2: 3 enriched in last 24 hours. Call volume dropped as expected.
- **BUG-071:** Narrative prompt compression — DEPLOYED
  - 1,700 → 900 token system prompt reduction confirmed.
- **BUG-072:** LLM cache infrastructure wiring — DEPLOYED
- **BUG-073:** Article fingerprint generation — PARTIALLY FIXED
  - Service layer path now generates fingerprints. RSS ingest path (rss_fetcher.py) still inserts directly, bypassing fingerprint generation. 28 articles in last 24h across all 5 sources have no fingerprint field. Carried forward as BUG-076.
- **BUG-074:** Briefing agent empty narrative list — FIXED & VERIFIED
  - Root cause: missing `.sort()` before `.limit()` in `_get_active_narratives()`. Fix confirmed working; briefing agent now receives April 2026 narratives.
- **BUG-075:** Inconsistent model routing — PARTIALLY FIXED
  - Detection works: `_validate_model_routing()` logs a warning on mismatch. Enforcement does not work: method logs but does not override or block. One Opus call traced to Claude Code test session. Enforcement gap carried forward as BUG-077.
- **TASK-065:** Observability on narrative backfill update_one calls — COMPLETE
- **TASK-066:** Stale narrative cleanup — COMPLETE
  - 233 stale October 2025 documents deleted. Collection is 347 documents, all April 2026, 0 stale remaining.
- **TASK-028:** Scheduled briefing validation — COMPLETE
  - 2 runs confirmed on 2026-04-14, correct content, correct model ($0.010033/run).

---

## Discovered During Validation

Four new bugs identified during TASK-028 cost validation. None existed as tickets at sprint start.

1. `llm_traces` uses `timestamp` field, not `created_at`. All prior cost queries using `created_at` returned empty results. Every cost query going forward must use `timestamp`.
2. Budget enforcement reads from `api_costs`. Gateway tracing writes to `llm_traces`. `entity_extraction` (198 calls, $0.177/day) writes to `llm_traces` only — never reaches `api_costs`. Daily cost as seen by enforcement: $0.957. Actual Anthropic spend: $1.134. Hard limit of $1.00 is not triggering. → BUG-079
3. RSS enrichment sync methods (rss_fetcher.py) call AnthropicProvider without operation names, routing as `provider_fallback` in `llm_traces` and `article_enrichment_batch` in `api_costs`. 261 calls/day ($0.26) cannot be correlated across collections. → BUG-078
4. `_tracked` async methods in AnthropicProvider call `tracker.track_call()` manually after already routing through the gateway. Gateway writes to `llm_traces`; manual call writes to `api_costs` with different operation name. Partial double-write architectural issue persists from BUG-068. → BUG-079

---

## System State at Close

| Item | State |
|---|---|
| Services (Railway) | All running: FastAPI, Celery Worker, Celery Beat, MongoDB, Redis |
| Scheduled briefings | Working. 2 runs confirmed 2026-04-14, correct content, correct model |
| Narrative collection | 347 documents, all April 2026, 0 stale |
| Article ingest | Active. ~56 articles enriched in last 24h. RSS fingerprint gap open (BUG-076) |
| Daily Anthropic spend | $1.134 (Haiku: $1.095, Opus: $0.039 from test session) |
| Budget enforcement view | $0.957 — blind to $0.177 (BUG-079) |
| Hard limit ($1.00) | NOT triggering due to BUG-079 |
| Model routing | 682/683 calls on Haiku. One Opus from Claude Code test, not production |
| llm_traces count | 3,853 total. Timestamp field confirmed (not created_at) |

---

## Tickets Carried into Sprint 15

- BUG-076: RSS ingest path does not generate article fingerprints
- BUG-077: `_validate_model_routing` warns but does not enforce model selection
- BUG-078: RSS enrichment calls have no operation name, masking $0.26/day in traces
- BUG-079: Budget enforcement is blind to entity_extraction costs — hard limit not enforcing against true spend