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
| 2 | TASK-025 | Implement Cost Controls | ✅ COMPLETE | 3 hr | 4 hr |
| 3 | TASK-026 | Fix Active LLM Failures (BUG-052) | ✅ COMPLETE | 3 hr | 2.5 hr |
| 4 | TASK-027 | Health Check & Site Status | ✅ COMPLETE | 2 hr | 1 hr |
| 5 | TASK-031 | Switch Redis to Railway (redis-py) | ✅ COMPLETE | 1 hr | 1 hr |
| 6 | BUG-053 | Remove Hardcoded SMTP Password | ✅ COMPLETE | 20 min | 20 min |
| 7 | TASK-032 | Clean Up Stale Anthropic Env Vars | ✅ COMPLETE | 10 min | 10 min |
| 8 | TASK-028 | Burn-in Validation (72hr via UptimeRobot) | ⏳ IN PROGRESS | 15 min | - |
| 9 | BUG-054 | RSS Ingestion Not Running (fetch_news disabled) | 🔲 CODE READY | 30 min | - |
| | | **--- PHASE 2: NeMo Agent Toolkit ---** | | |
| 6 | TASK-029 | NeMo Research & Integration Plan | 🔲 OPEN | 2 hr |
| 7 | FEATURE-051 | NeMo Setup & Workflow Instrumentation | 🔲 OPEN | 4 hr |
| 8 | FEATURE-052 | Eval Framework & Baselines | 🔲 OPEN | 3 hr |
| 9 | FEATURE-053 | Optimization & Cost Dashboards | 🔲 OPEN | 4 hr |

---

## Success Criteria

### Phase 1: Stable & Affordable
- [x] Root cause of LLM spend identified and documented in `_generated/evidence/13-llm-spend-audit.md`
- [x] Per-system cost controls in place (daily limits, circuit breakers)
- [x] All three LLM systems operational (briefing generation, entity extraction, sentiment analysis)
- [x] No silent failures — all LLM errors logged with context
- [x] `/health` endpoint live, frontend status indicator working (TASK-027 ✅)
- [x] Redis connected and functional — rate limiter + circuit breaker active (TASK-031 ✅)
- [x] SMTP credentials removed from config (BUG-053 ✅)
- [x] Stale Anthropic env vars cleaned up (TASK-032 ✅)
- [ ] System runs 72 hours without intervention (TASK-028 via UptimeRobot) — IN PROGRESS
- [ ] Daily LLM spend under $0.33 (~$10/month target)
- [ ] RSS ingestion pipeline running on schedule (BUG-054) — code ready, awaiting manual test

### Phase 2: Production-Grade Monitoring
- [ ] NeMo Agent Toolkit integrated and capturing telemetry
- [ ] OpenTelemetry tracing on all three LLM workflows
- [ ] Eval baselines established (briefing quality, entity accuracy, sentiment accuracy)
- [ ] Hyperparameter optimization run (model selection, temperature, max_tokens)
- [ ] Cost dashboard live via telemetry
- [ ] Cost reduced vs. Phase 1 baseline with quality scores maintained

---

## Session 12 Work Summary (2026-04-02) - BUG-054 CODE COMPLETE ✅

**BUG-054: RSS Ingestion Pipeline Not Running - CODE FIXES COMPLETE** ✅ (Awaiting Manual Test)

### Work Completed:
- ✅ Added `name="fetch_news"` to `@shared_task` decorator in `tasks/news.py` (line 19)
- ✅ Re-enabled `fetch_news` in beat schedule with 3-hour interval (tasks/beat_schedule.py, lines 18-30)
- ✅ Fixed dead smoke test code by converting direct `return {` to assignable `schedule` variable
- ✅ Added POST `/admin/trigger-fetch` endpoint for HTTP-based manual testing (api/admin.py, lines 506-551)

### Branch & Commits:
- **Branch:** `fix/bug-054-rss-pipeline-not-running`
- **Commits:**
  - `b5c0dd7` - fix(tasks): Re-enable RSS ingestion pipeline (BUG-054)
  - `cacfd24` - feat(admin): Add /admin/trigger-fetch endpoint for manual testing

### Next Steps (Manual):
1. Deploy branch to Railway
2. Run manual trigger test: `curl -X POST https://context-owl-production.up.railway.app/admin/trigger-fetch`
3. Monitor celery-worker logs for article ingestion success
4. Verify signals page populates within 3 hours
5. Merge PR and watch beat schedule auto-dispatch every 3 hours

### Impact:
- Restores entire data pipeline (articles → entities → signals → briefings)
- Articles stale since March 22 should refresh within 3 hours of deployment

---

## Session 11 Work Summary (2026-04-02) - TASK-032 & BUG-053 COMPLETE ✅

**TASK-032: Clean Up Anthropic Env Vars - COMPLETE** ✅
**BUG-053: Remove Hardcoded SMTP Credentials - COMPLETE** ✅

### Work Completed:
- ✅ **TASK-032:** Deleted `ANTHROPIC_ENTITY_FALLBACK_MODEL`, updated `ANTHROPIC_ENTITY_MODEL` to `claude-haiku-4-5-20251001`
- ✅ **BUG-053:** Removed plaintext SMTP password from config.py
- ✅ Verified health endpoint all green
- ✅ Set up UptimeRobot for 72-hour burn-in monitoring (TASK-028)

---

## Session 9 Work Summary (2026-04-02) - TASK-031 COMPLETE ✅

**TASK-031: Switch Redis from Upstash REST to Railway Redis - COMPLETE** ✅

### Implementation Summary:
Replaced Upstash REST API client with redis-py for direct protocol communication to Railway Redis.

### Work Completed:
- ✅ Rewrote `redis_rest_client.py` to use redis-py with identical interface
- ✅ Support for both Railway Redis (REDIS_URL) and local fallback (REDIS_HOST:PORT)
- ✅ Updated config.py: added REDIS_URL field, removed Upstash-specific settings
- ✅ All existing consumers unchanged: rate_limiter.py, circuit_breaker.py, health.py
- ✅ Graceful degradation when Redis unavailable (returns safe defaults)

### Test Results:
- **redis_client tests:** 11/11 ✅
- **rate_limiter tests:** 10/10 ✅ (unchanged)
- **circuit_breaker tests:** 16/16 ✅ (unchanged)
- **health_endpoint tests:** 20/20 ✅ (unchanged)
- **Total:** 57/57 ✅

### Cost Impact:
- Before: Upstash REST (deleted)
- After: Railway Redis ($0.07/month, included in platform)
- Net savings: ~$0-5/month

### PR:
- **Branch:** `feature/task-031-railway-redis`
- **PR #233:** feat(redis): Switch from Upstash REST to redis-py with Railway Redis (TASK-031)
- **Commits:** 3 (code + docs)

### Unblocks:
- Adding Anthropic credits safely (rate limiter + circuit breaker now active)
- TASK-032 (env var cleanup)
- BUG-053 (SMTP password removal)
- TASK-028 (burn-in validation)

---

## Session 10 Work Summary (2026-04-02) - BUG-053 COMPLETE ✅

**BUG-053: Remove Hardcoded SMTP Credentials - COMPLETE** ✅

### Security Issue Fixed:
`src/crypto_news_aggregator/core/config.py` contained plaintext SMTP password and credentials committed to Git. These are now removed and must be provided via environment variables.

### Changes Made:
- ✅ Removed hardcoded SMTP_PASSWORD from line 105
- ✅ Removed hardcoded SMTP_USERNAME (was "snotboogy")
- ✅ Removed hardcoded EMAIL_FROM email address
- ✅ Set all SMTP settings to empty defaults: `SMTP_SERVER=""`, `SMTP_USERNAME=""`, `SMTP_PASSWORD=""`, `EMAIL_FROM=""`
- ✅ Updated SMTP_PORT from 2525 to standard 587 (TLS)
- ✅ Added comments indicating settings should be provided via environment variables

### Configuration:
- **Branch:** `fix/bug-053-remove-hardcoded-smtp`
- **Commit:** `851f655` - `fix(config): Remove hardcoded SMTP credentials (BUG-053)`
- **Files Changed:** 1 (config.py, 5 insertions, 7 deletions)

### Security Notes:
- Credentials were in Git history (low risk for private repo, but rotated if possible)
- SMTP functionality is not actively used in production
- Production (Railway) uses environment variables for any SMTP setup needed
- No regressions: app starts successfully with empty SMTP settings

### Impact:
- ✅ No hardcoded credentials in source code
- ✅ Credentials must be explicitly configured via environment variables
- ✅ Reduces attack surface and improves security posture
- ✅ Ready for PR merge and deployment

### Next Steps:
1. Merge PR to main
2. Deploy to production (Railway)
3. Proceed to TASK-032 (env var cleanup)

---

## Session 8 Work Summary (2026-04-01/04-02) - TRIAGE & TICKETS

### Production Diagnostics:
Investigated current production state via health endpoint. Findings:
- **Database:** OK
- **Redis:** ERROR — Upstash database was deleted; REST client returning "PING returned False"
- **LLM:** ERROR — Anthropic credit balance is $0 (400 Bad Request)
- **Data freshness:** WARNING — 10+ days stale (nothing running)

Attempted Upstash reconnection (new free-tier DB created, env vars set on Railway) but could not resolve — client connects (1.2ms latency) but response doesn't match expected format. Root cause unclear. Decision: abandon Upstash, switch to Railway-hosted Redis that's already running and costs $0.07/month.

### Railway Cost Investigation:
Reviewed Railway invoice — total ~$43/month, with **$32.55 on memory** (75% of bill). Root cause: Celery worker running without memory limits or pool configuration, averaging ~3.2 GB RAM.
- **celery-worker:** $17.07 RAM (biggest offender)
- **crypto-news-aggregator:** $5.95 RAM
- **celery-beat:** $0.70 RAM
- **Redis:** $0.04 RAM (negligible)

### Fixes Applied:
- ✅ Set 1 GB memory limits on all three app services (Railway minimum)
- ✅ Updated celery-worker start command: added `--pool=solo --max-tasks-per-child=50`
  - `--pool=solo`: single process instead of 4+ forked workers
  - `--max-tasks-per-child=50`: auto-recycle to prevent memory leaks
  - Previous command: `cd src && celery -A crypto_news_aggregator.tasks worker --loglevel=info --queues=default,news,price,alerts,briefings`
  - New command: `cd src && celery -A crypto_news_aggregator.tasks worker --loglevel=info --queues=default,news,price,alerts,briefings --pool=solo --max-tasks-per-child=50`
- ✅ Celery worker confirmed back online after initial OOM crash (was over 1 GB at time of limit)

### Projected Cost Savings:
| Item | Before | After (projected) |
|------|--------|--------------------|
| Railway Memory | ~$32/mo | ~$5-8/mo |
| Railway Total | ~$43/mo | ~$16-19/mo |
| Anthropic LLM | unknown | ~$10/mo (target) |
| **Total** | **$50+/mo** | **~$26-29/mo** |

### Key Decisions:
- **Daily LLM spend target defined:** $0.33/day ($10/month ÷ 30)
- **TASK-028 approach changed:** Use UptimeRobot (free tier) instead of custom script — external monitoring is more credible and requires no hosting
- **Abandon Upstash, use Railway Redis:** Less external dependencies, already paying for it, simpler architecture
- **Execution order:** TASK-031 (Redis) → TASK-032 (env vars) → BUG-053 (SMTP) → add Anthropic credits → UptimeRobot → TASK-028 burn-in

### Tickets Created:
- **TASK-031:** Switch Redis from Upstash REST to Railway Redis (redis-py) — 1 hr, CC session
- **TASK-032:** Clean Up Stale Anthropic Model Env Vars — 10 min, manual Railway config
- **BUG-053:** Remove Hardcoded SMTP Password from config.py — 20 min, CC session

### Security Issue Found:
- `config.py` contains hardcoded SMTP password in plain text (BUG-053 created)
- SMTP not actively used but credentials are live and committed to Git history

### Also Noted:
- `ANTHROPIC_ENTITY_FALLBACK_MODEL` env var on Railway is deprecated (removed by BUG-039) — delete it
- `ANTHROPIC_ENTITY_MODEL` env var uses old model string `claude-3-5-haiku-20241022` — update to `claude-haiku-4-5-20251001`

---

## Session 6 Work Summary (2026-04-01) - TASK-026 COMPLETE ✅

**TASK-026: Fix Active LLM Failures (BUG-052) - COMPLETE** ✅

### Implementation Summary:
Implemented comprehensive structured error handling across all LLM systems to eliminate silent failures and enable visibility into LLM errors.

### Work Completed:
- ✅ Created `LLMError` exception class with error_type classification
- ✅ Fixed `anthropic.py` to raise exceptions instead of returning empty strings
- ✅ Updated sentiment/relevance/themes methods to catch LLMError and return graceful defaults
- ✅ Fixed `briefing_agent.py` to propagate LLM errors (don't swallow them)
- ✅ Fixed `briefing_tasks.py` to distinguish LLM failures from clean skips
- ✅ Added `error_type` field to API response with HTTP code mapping
- ✅ Replaced bare except: with explicit Exception handling
- ✅ Added exc_info=True to all error logging for stack traces

### Test Results:
- **test_llm_exceptions.py:** 10/10 ✅
- **test_anthropic_error_handling.py:** 13/13 ✅
- **test_briefing_agent_error_handling.py:** 5/5 ✅
- **test_briefing_generate_endpoint.py:** 3/3 ✅
- **Total:** 31/31 ✅

### Impact:
- No more silent failures — every LLM error logged with full context
- Celery tasks can distinguish LLM failures from intentional skips
- API returns machine-readable error types (auth_error→502, others→503)
- Resolves BUG-052 completely

### Commits:
- `79a9fe1` - fix(llm): Implement structured error handling for LLM failures (TASK-026)
- `325a8e5` - docs: Complete TASK-026 documentation

### Remaining:
- Create PR from `feature/task-025-cost-controls` to `main` (contains both TASK-025 & TASK-026)
- Deploy to prod (Railway)

---

## Session 5 Work Summary (2026-04-01) - TASK-025 COMPLETE ✅

**TASK-025: Implement Cost Controls - COMPLETE** ✅

### All Stages Complete:
1. ✅ **Stage 1: Rate Limiting** - Per-system daily call limits (9 tests)
2. ✅ **Stage 2: Circuit Breaker** - Failure detection & recovery (28 tests)
3. ✅ **Stage 3: Spend Logging** - Cost tracking & aggregation (9+6 tests)
4. ✅ **Stage 4: E2E Testing** - Complete flow verification (6 tests)

### Work Completed This Session:
- ✅ Added entity extraction cost tracking to `extract_entities_batch()`
- ✅ Implemented `get_cost_by_operation()` for spend breakdown by operation
- ✅ Implemented `get_cost_by_model()` for spend breakdown by model
- ✅ Created 15 new integration tests (spend logging + E2E)
- ✅ Verified all 42 cost control tests passing

### Cost Control Coverage:
**System 1 - Briefing Generation:** ✅ Tracked via briefing_agent.py
**System 2 - Entity Extraction:** ✅ Tracked via extract_entities_batch() (NEW)
**System 3 - Sentiment/Theme/Relevance:** ✅ Tracked via *_tracked() methods

### Test Results:
- **spend_logging_aggregation tests:** 9/9 ✅
- **cost_controls_e2e tests:** 6/6 ✅
- **total cost control tests:** 42/42 ✅

### Metrics:
- All LLM calls logged to MongoDB with complete cost data
- Spend aggregation by operation type and model implemented
- Pricing accuracy verified across all models (Haiku, Sonnet, Opus)
- Resilience confirmed - cost tracking failures don't break LLM operations

### Ready for:
- ✅ Merge to main
- ✅ Deploy to prod (Railway)
- ✅ Production monitoring via spend aggregation

---

## Session 5 Work Summary (2026-04-01) [Earlier Summary]

**TASK-025 Stage 3: Spend Logging Aggregation - COMPLETE ✅**

**Completed:**
- ✅ Added cost tracking to `extract_entities_batch()` (async background task)
- ✅ Implemented `get_cost_by_operation()` for per-operation spend aggregation
- ✅ Implemented `get_cost_by_model()` for per-model spend aggregation
- ✅ Created 9 comprehensive integration tests for spend logging

**Cost Control Coverage (ALL SYSTEMS TRACKED):**
1. **Briefing Generation** - tracked via briefing_agent.py ✅
2. **Entity Extraction** - tracked via extract_entities_batch() ✅ (NEW)
3. **Sentiment/Theme/Relevance** - tracked via *_tracked() methods ✅

**Test Status:**
- Total cost control tests: 36/36 ✅
- New spend logging tests: 9/9 ✅
- All stages (1-3) tests: 62/62 passing

**Remaining for TASK-025:**
- Stage 4: End-to-end integration testing (~20 min)

## Session 4 Work Summary (2026-04-01)

**TASK-025 Stage 1: Rate Limit Integration - COMPLETE ✅**

**Completed:**
- ✅ Integrated rate limit checks into all LLM client methods:
  - `analyze_sentiment_tracked()` - checks sentiment_analysis limit
  - `extract_themes_tracked()` - checks theme_extraction limit
  - `score_relevance_tracked()` - checks relevance_scoring limit
  - `enrich_articles_batch()` - checks both sentiment_analysis + theme_extraction limits
  - `extract_entities_batch()` - checks entity_extraction limit
- ✅ Graceful degradation: methods return empty/0.0 when limit hit
- ✅ Rate limiter incremented after successful API calls
- ✅ Created 9 integration tests for rate limit enforcement, all passing
- ✅ Committed: `feat(cost-controls): Integrate rate limits into LLM client methods (TASK-025 Stage 1)`

**Test Status:**
- Rate limit integration tests: 9/9 ✅
- All earlier cost control tests: 25/25 ✅
- Total: 34/34 ✅

**Files Changed:**
- `src/crypto_news_aggregator/llm/anthropic.py` - Added rate limit checks + increments (76 lines)
- `tests/integration/test_rate_limit_integration.py` - New comprehensive test suite (230 lines)

**Remaining for TASK-025:**
- Implement circuit breaker for failure recovery (~45 min)
- Implement spend logging aggregation (~30 min)
- End-to-end integration testing (~20 min)

**Estimated remaining:** ~1.5 hours to complete TASK-025

## Session 3 Work Summary (2026-04-01)

**Completed:**
- ✅ Fixed `RedisRESTClient.incr()` None handling bug
- ✅ Updated 14 cost tracker tests to use current Claude models
- ✅ Implemented `MockRedis` for rate limiter unit tests  
- ✅ Fixed backfill narrative test async mocks
- ✅ All 25 core cost control tests now passing
- ✅ Committed fixes: `fix(cost-controls): Fix test failures for TASK-025`

**Test Status:**
- Rate limiter: 10/10 ✅
- Cost tracking E2E: 6/6 ✅
- LLM cost tracking: 9/9 ✅
- Total cost controls: 25/25 ✅

**Files Changed:**
- `src/crypto_news_aggregator/core/redis_rest_client.py` - Fixed incr() None handling
- `tests/integration/test_cost_tracking_e2e.py` - Updated model names (haiku-4-5, sonnet-4-5, opus-4-6)
- `tests/integration/test_llm_cost_tracking.py` - Updated model names
- `tests/services/test_rate_limiter.py` - Added MockRedis implementation
- `tests/integration/test_backfill_narratives.py` - Fixed async mock setup

## Session 2 Work Summary (2026-03-31, afternoon)

**Completed:**
- ✅ Fixed all 8 cost tracker test failures (model/pricing mismatches)
- ✅ Created RateLimiter service with Redis backing for per-system daily limits
- ✅ Added `incr()` method to RedisRESTClient
- ✅ Created 10 unit tests for RateLimiter (needed mock fix)

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
- **TASK-031: Switch Redis from Upstash REST to Railway Redis (redis-py)** — 1 hr, CC session. Upstash database deleted; Railway Redis already running at $0.07/mo. Rewrite redis_rest_client.py to use redis-py with identical interface. Blocks safe re-enabling of Anthropic credits.
- **TASK-032: Clean Up Stale Anthropic Model Env Vars** — 10 min, manual Railway config. Delete deprecated `ANTHROPIC_ENTITY_FALLBACK_MODEL`, update `ANTHROPIC_ENTITY_MODEL` to current string.
- **BUG-053: Remove Hardcoded SMTP Password from config.py** — 20 min, CC session. Plaintext password committed to repo. Rotate credential, empty defaults, verify SMTP disabled.

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