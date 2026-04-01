# Sprint 12 — Backdrop Stability & Production-Grade Monitoring

**Status:** Not Started
**Started:**
**Target:** Open-ended (until stable)

---

## Sprint Goal

_Get Backdrop continuously operational and affordable, then integrate NVIDIA NeMo Agent Toolkit for production-grade observability and optimization._

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| | | **--- PHASE 1: Triage & Stabilize ---** | | | |
| 1 | TASK-024 | LLM Spend Audit | ✅ COMPLETE | 2 hr | 2 hr |
| 2 | TASK-025 | Implement Cost Controls | 🟡 IN_PROGRESS | 3 hr | 3.5 hr (test fixes + daily limits WIP) |
| 3 | TASK-026 | Fix Active LLM Failures (BUG-052) | 🔲 OPEN | 3 hr | - |
| 4 | TASK-027 | Health Check & Site Status | 🔲 OPEN | 2 hr | - |
| 5 | TASK-028 | Burn-in Validation (72hr) | 🔲 OPEN | 1 hr | - |
| | | **--- PHASE 2: NeMo Agent Toolkit ---** | | |
| 6 | TASK-029 | NeMo Research & Integration Plan | 🔲 OPEN | 2 hr |
| 7 | FEATURE-051 | NeMo Setup & Workflow Instrumentation | 🔲 OPEN | 4 hr |
| 8 | FEATURE-052 | Eval Framework & Baselines | 🔲 OPEN | 3 hr |
| 9 | FEATURE-053 | Optimization & Cost Dashboards | 🔲 OPEN | 4 hr |

---

## Success Criteria

### Phase 1: Stable & Affordable
- [ ] Root cause of LLM spend identified and documented in `_generated/evidence/13-llm-spend-audit.md`
- [ ] Per-system cost controls in place (daily limits, circuit breakers)
- [ ] All three LLM systems operational (briefing generation, entity extraction, sentiment analysis)
- [ ] No silent failures — all LLM errors logged with context
- [ ] `/health` endpoint live, frontend status indicator working
- [ ] System runs 72 hours without intervention
- [ ] Daily LLM spend under $X (define after audit)

### Phase 2: Production-Grade Monitoring
- [ ] NeMo Agent Toolkit integrated and capturing telemetry
- [ ] OpenTelemetry tracing on all three LLM workflows
- [ ] Eval baselines established (briefing quality, entity accuracy, sentiment accuracy)
- [ ] Hyperparameter optimization run (model selection, temperature, max_tokens)
- [ ] Cost dashboard live via telemetry
- [ ] Cost reduced vs. Phase 1 baseline with quality scores maintained

---

## Session 2 Work Summary (2026-03-31, afternoon)

**Completed:**
- ✅ Fixed all 8 cost tracker test failures (model/pricing mismatches)
- ✅ Created RateLimiter service with Redis backing for per-system daily limits
- ✅ Added `incr()` method to RedisRESTClient
- ✅ Created 10 unit tests for RateLimiter (need mock Redis fix)

**In Progress:**
- 🟡 Daily call limits implementation (core logic done, tests need mocking)

**Files Changed:**
- `tests/services/test_cost_tracker.py` - Updated all 8 tests to current models/pricing
- `src/crypto_news_aggregator/services/cost_tracker.py` - Fixed duplicate PRICING entry, added claude-opus-4-6
- `src/crypto_news_aggregator/core/redis_rest_client.py` - Added `incr()` method
- `src/crypto_news_aggregator/services/rate_limiter.py` - New RateLimiter service
- `tests/services/test_rate_limiter.py` - New test file (10 tests)

**Remaining for TASK-025:**
- Fix rate limiter test mocking
- Implement circuit breaker 
- Implement spend logging
- End-to-end testing

---

## Session 1 Work Summary (2026-03-31)

**What was completed:**

### Cost Tracking Enabled (System 3)
- Implemented `_get_completion_with_usage()` to extract token metrics from Anthropic API responses
- Created async tracked methods for sentiment, theme, and relevance scoring
- All enrichment operations now tracked via CostTracker.track_call() (non-blocking async)
- Operations tracked: `relevance_scoring`, `sentiment_analysis`, `theme_extraction`

### Config Fix
- Fixed pricing config zeros: `ENTITY_INPUT_COST=0.0→0.80`, `ENTITY_OUTPUT_COST=0.0→4.0`
- Entity extraction cost now visible in cost tracking logs

### Batch Enrichment (50% cost reduction)
- Implemented `enrich_articles_batch()` for batch processing up to 10 articles/call
- Refactored RSS enrichment loop from per-article (3N calls) to batched (N/10 calls)
- Example: 30 articles now cost 3 API calls instead of 90

### Branch & PR
- Branch: `feature/task-025-cost-controls`
- PR #227: feat(cost-controls): Implement LLM cost tracking and batching
- Commit: 00ae29e

**What's remaining:**
- Fix test failures (12 tests failing due to model name/pricing mismatches)
- Implement daily call limits (Priority task, not yet started)
- Implement circuit breakers (Priority task, not yet started)
- Full end-to-end testing

## Key Decisions

_Decisions made during the sprint that affect scope, priority, or approach._

- **TASK-025 deferred to multi-session:** Cost tracking (Priorities 1-3) implemented; testing and remaining items (daily limits, circuit breakers) deferred to next session per user request

---

## Discovered Work

- **TASK-030: Rename GitHub Repo & Update Public-Facing Metadata** — 15 min, manual (GitHub UI). Pre-sprint housekeeping before TASK-024. Repo name still shows legacy name; employers hitting GitHub links from resume/LinkedIn see the wrong project name. Full README rewrite deferred to Sprint 13 backlog.

---

## Completed

| # | Ticket | Title | Status | Effort |
|---|--------|-------|--------|--------|
| 1 | TASK-024 | LLM Spend Audit | ✅ COMPLETE | 2 hr |

---

## Next Sprint: RSS Feed Pivot (AI Content)

**Note:** Sprint 13 will overhaul RSS feeds and content sourcing — replacing crypto sources with AI-related articles and information. The core ingestion/processing pipeline stays, but feed list, relevance classifiers, entity models, and briefing prompts all change. This is a major change requiring an ADR before implementation. No action needed this sprint beyond this note.

**Backlog for Sprint 13:**
- Full README rewrite (pairs with RSS pivot — README should reflect what the app actually does post-pivot)