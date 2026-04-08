# Sprint 12 — Backdrop Stability & Production-Grade Monitoring

**Status:** CLOSED (2026-04-08)
**Started:** 2026-04-01
**Sessions:** 25
**Phase 1:** Complete (17/18 tasks — TASK-028 burn-in deferred to Sprint 13)
**Phase 2:** Moved to Sprint 13 (NeMo integration reframed as full sprint)

---

## Sprint Goal

_Get Backdrop continuously operational and affordable, then integrate NVIDIA NeMo Agent Toolkit for production-grade observability and optimization._

**Outcome:** Phase 1 achieved. Pipeline is live, cost controls are in place, monitoring is deployed. However, LLM spend still exceeds targets (~$2.50-5/day vs $0.33/day goal) due to untraced token leaks. NeMo integration elevated from Phase 2 add-on to dedicated Sprint 13 with ADR-driven planning.

---

## Sprint Order (Final)

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
| 8 | BUG-055 | SMOKE_BRIEFINGS Leak + MongoDB Quota Full | ✅ COMPLETE | 45 min | 45 min |
| 9 | BUG-054 | RSS Ingestion Not Running | ✅ COMPLETE | 30 min | 30 min |
| 10 | TASK-030 | Rename GitHub Repo | ✅ COMPLETE | 15 min | 15 min |
| 11 | TASK-033 | Add Sentry Error Monitoring | ✅ COMPLETE | 30 min | 45 min |
| 12 | TASK-034 | Pipeline Heartbeat Health Check | ✅ COMPLETE | 1 hr | 1 hr |
| 13 | TASK-035 | Daily Pipeline Digest via Slack | ✅ COMPLETE | 1-2 hr | 1 hr |
| 14 | BUG-056 | LLM Spend Cap Enforcement | ✅ COMPLETE | 1-1.5 hr | 2 hr |
| 15 | BUG-057 | Narrative Retry Storm Fix | ✅ COMPLETE | 1-1.5 hr | 2 hr |
| 16 | BUG-058 | Briefing Generation Silently Skips | ✅ COMPLETE | 1 hr | 1 hr |
| 17 | BUG-059 | Cost Tracking Silently Fails | ✅ COMPLETE | 1 hr | 1 hr |
| 18 | TASK-028 | Burn-in Validation (72hr) | ⏸ DEFERRED | 15 min | — |
| | | **--- PHASE 2: NeMo (moved to Sprint 13) ---** | | | |
| 19 | TASK-029 | NeMo Research & Integration Plan | → Sprint 13 | 2 hr | — |
| 20 | FEATURE-051 | NeMo Setup & Workflow Instrumentation | → Sprint 13 | 4 hr | — |
| 21 | FEATURE-052 | Eval Framework & Baselines | → Sprint 13 | 3 hr | — |
| 22 | FEATURE-053 | Optimization & Cost Dashboards | → Sprint 13 | 4 hr | — |

---

## Success Criteria (Final)

### Phase 1: Stable & Affordable
- [x] Root cause of LLM spend identified and documented
- [x] Per-system cost controls in place (daily limits, circuit breakers)
- [x] All three LLM systems operational
- [x] No silent failures — all LLM errors logged with context
- [x] `/health` endpoint live, frontend status indicator working
- [x] Redis connected and functional
- [x] SMTP credentials removed from config
- [x] Stale Anthropic env vars cleaned up
- [ ] ~~System runs 72 hours without intervention~~ — deferred (token leaks make burn-in premature)
- [ ] ~~Daily LLM spend under $0.33~~ — spend cap code deployed but leaks persist
- [x] SMOKE_BRIEFINGS disabled, smoke test block removed
- [x] MongoDB Atlas under 512 MB quota
- [x] RSS ingestion pipeline running on schedule
- [x] Sentry error monitoring active
- [x] Pipeline heartbeat health check live
- [x] Daily Slack digest code complete (awaiting webhook config)

---

## Key Decisions

- TASK-025 deferred to multi-session: cost tracking Priorities 1-3 implemented; testing deferred
- Daily LLM spend target: $0.33/day ($10/month ÷ 30)
- TASK-028 approach: UptimeRobot (free tier) instead of custom script
- Abandoned Upstash, switched to Railway Redis ($0.07/mo)
- Railway memory limits set to 1 GB on all services (saved ~$25/mo)
- Sprint 12 Phase 2 (NeMo) elevated to full Sprint 13 with ADR

---

## Discovered Work (carried to backlog)

- **TASK-028:** 72-hour burn-in validation — deferred until token leaks resolved via NeMo tracing
- **TASK-035 webhook:** Slack webhook URL still needs manual Railway config
- **Prompt Audit:** Reduce first-call failure rate based on degraded rate data from BUG-057
- **Sprint 13 backlog:** Full README rewrite (pairs with RSS pivot)

---

## Session Log

### Session 25 (2026-04-05) — BUG-059 COMPLETE ✅
**BUG-059: Cost Tracking Silently Fails + Spend Cap Never Enforces**
- Fixed 5 import paths in anthropic.py: `db.mongo_manager` → `db.mongodb`
- Replaced 4 `asyncio.create_task()` with `await` in anthropic.py
- Added budget checks to `_make_api_call()` in optimized_anthropic.py
- Replaced 6 `asyncio.create_task()` with `await` in optimized_anthropic.py
- Added operation names to all 3 API call methods
- Branch: `fix/bug-058-briefing-generation-skips` | Commit: `586e99e`

### Session 24 (2026-04-04) — BUG-058 COMPLETE ✅
**BUG-058: Briefing Generation Silently Skips**
- Replaced `_get_trending_signals()` to call `compute_trending_signals()` on-demand
- Root cause: queried non-existent `trending_signals` collection
- 43 briefing tests passing, zero regressions
- Branch: `fix/bug-058-briefing-generation-skips` | Commit: `b82df8d`

### Session 23 (2026-04-03) — BUG-057 CONFIG COMPLETE ✅
**Disable Dead News Sources & Price Alerts**
- ENABLED_NEWS_SOURCES → empty list, commented out fetch-news and check-price-alerts schedules
- Eliminates ~480 unnecessary log lines/day
- PR: #249 | Commit: `eef324a`

### Session 22 (2026-04-03) — BUG-057 TESTS COMPLETE ✅
**Narrative Retry Storm — 12 tests added**
- All 121 tests passing (7 skipped), zero regressions
- PR: #248 | Commit: `54631ac`

### Session 21 (2026-04-03) — BUG-057 CODE COMPLETE ✅
**Narrative Retry Storm — Implementation**
- Zero-retry on validation failures, degraded fallback, per-article LLM call cap (2)
- Tier 2/3 auto-fixes, degraded rate tracking, downstream filtering
- Commit: `20e5e28`

### Session 20 (2026-04-03) — BUG-056 TESTS COMPLETE ✅
**LLM Spend Cap — 33 tests (32 passing, 1 skipped)**
- Commit: `e4d16b3`

### Session 19 (2026-04-03) — BUG-056 CODE COMPLETE ✅
**LLM Spend Cap Enforcement — Implementation**
- Soft limit $0.25/day, hard limit $0.33/day, TTL-cached budget checks
- Backlog throttle: ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5
- Commit: `9d63412`

### Session 18 (2026-04-03) — TASK-035 COMPLETE ✅ + Briefing Fix
- Daily Slack digest: services/daily_digest.py, tasks/digest_tasks.py, 7 tests
- Fixed briefing trending_signals → compute_trending_signals

### Session 17 (2026-04-02) — TASK-034 COMPLETE ✅
**Pipeline Heartbeat Health Check**
- Heartbeat recording after fetch_news and briefing generation
- HTTP 500 on stale pipeline (6h fetch, 18h briefing thresholds)
- 7 tests passing

### Session 16 (2026-04-02) — TASK-033 COMPLETE ✅
**Sentry Error Monitoring**
- sentry-sdk integrated with FastAPI + Celery
- Fixed Railway start command for proper poetry install

### Session 15 (2026-04-02) — BUG-055 FULLY COMPLETE ✅ + BUG-054 VERIFIED ✅ + TASK-030 ✅
- Removed SMOKE_BRIEFINGS env var, pruned MongoDB (516→253 MB)
- Verified pipeline live: articles flowing, data freshness 0.4h
- Renamed GitHub repo

### Session 14 (2026-04-02) — BUG-055 CODE COMPLETE ✅
- Empty-data guard, removed smoke test block, fixed event loop bug
- Commit: `f119256`

### Session 13 (2026-04-02) — BUG-055 DIAGNOSED
- Found SMOKE_BRIEFINGS=1 causing 480+ wasted API calls/day against full MongoDB

### Session 12 (2026-04-02) — BUG-054 CODE COMPLETE ✅
- Root cause: fetch_news commented out in beat_schedule.py
- Added name="fetch_news", re-enabled schedule, added /admin/trigger-fetch
- Commits: `b5c0dd7`, `cacfd24`

### Session 11 (2026-04-02) — TASK-032 ✅
- Cleaned Anthropic env vars, added credits, set up UptimeRobot

### Session 10 (2026-04-02) — BUG-053 ✅
- Removed hardcoded SMTP password from config.py

### Session 9 (2026-04-02) — TASK-031 ✅
- Switched Upstash REST → Railway redis-py, 57/57 tests passing
- PR: #233

### Session 8 (2026-04-01-02) — Triage & Tickets
- Diagnosed production state: Redis dead, Anthropic $0, data 10+ days stale
- Set 1 GB memory limits (saved ~$25/mo Railway)
- Created TASK-031, TASK-032, BUG-053

### Session 7 (2026-04-01) — TASK-027 COMPLETE ✅
- Health check endpoint + site status, 20/20 tests, PR #232

### Session 6 (2026-04-01) — TASK-026 COMPLETE ✅
- Structured LLMError handling, 31/31 tests
- Commits: `79a9fe1`, `325a8e5`

### Session 5 (2026-04-01) — TASK-025 COMPLETE ✅
- All 4 stages: rate limiting, circuit breaker, spend logging, E2E
- 42/42 tests passing

### Session 4 (2026-04-01) — TASK-025 Stage 1 ✅
- Rate limit integration, 34/34 tests

### Session 3 (2026-04-01) — Test Fixes
- Fixed RedisRESTClient.incr(), updated model names, MockRedis, 25/25 tests

### Session 2 (2026-03-31) — TASK-025 Foundations
- RateLimiter service, RedisRESTClient.incr(), 10 unit tests

### Session 1 (2026-03-31) — TASK-024 + TASK-025 Start
- Cost tracking enabled, pricing config fix, batch enrichment (50% cost reduction)
- PR: #227 | Commit: `00ae29e`