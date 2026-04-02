# Session Start

**Date:** 2026-04-02
**Status:** Sprint 12, Phase 1 — 4 of 5 original tickets complete, 3 new tickets added
**Branch:** `main` (TASK-031 will create `feature/task-031-railway-redis`)

---

## Session 8 Work Summary (2026-04-01/04-02) - TRIAGE & TICKETS

### What Happened:
Diagnosed production health, found Redis (Upstash deleted), LLM (zero credits), and data freshness (10+ days stale) all failing. Fixed Celery memory blowout ($32/mo → projected $5-8/mo). Created three tickets to unblock getting Backdrop back online safely.

### Fixes Applied (already live on Railway):
- ✅ Celery worker: `--pool=solo --max-tasks-per-child=50` (was spawning 4+ processes, caused OOM)
- ✅ Memory limits: 1 GB cap on celery-worker, crypto-news-aggregator, celery-beat
- ✅ Daily LLM spend target defined: $0.33/day ($10/month)

### Tickets Created:
- **TASK-031:** Switch Redis from Upstash REST to Railway Redis (redis-py) — CRITICAL, blocks everything
- **TASK-032:** Clean Up Stale Anthropic Model Env Vars — 10 min manual config
- **BUG-053:** Remove Hardcoded SMTP Password from config.py — security fix

---

## Current Health Endpoint Status

```
GET https://context-owl-production.up.railway.app/api/v1/health
```

| Check | Status | Notes |
|-------|--------|-------|
| Database | ✅ ok | MongoDB healthy, ~3ms |
| Redis | ❌ error | Upstash DB deleted; needs TASK-031 |
| LLM | ❌ error | $0 Anthropic credits; add after TASK-031 |
| Data freshness | ⚠️ warning | 10+ days stale; will resolve once pipeline runs |

---

## Next Up (execution order)

1. **TASK-031: Switch to Railway Redis** — CC session, ~1 hr. This is the #1 blocker.
   - Rewrite `redis_rest_client.py` to use redis-py with Railway Redis
   - Same interface, zero changes to rate_limiter.py / circuit_breaker.py / health.py
   - Ticket: `task-031-switch-to-railway-redis.md`

2. **BUG-053: Remove Hardcoded SMTP Password** — CC session, ~20 min. Do alongside TASK-031.
   - Rotate SMTP credential first (manual)
   - Empty SMTP defaults in config.py
   - Verify SMTP code paths are disabled
   - Ticket: `bug-053-hardcoded-smtp.md`

3. **TASK-032: Clean Up Anthropic Env Vars** — Manual, 10 min. Do in Railway UI.
   - Delete `ANTHROPIC_ENTITY_FALLBACK_MODEL` (deprecated by BUG-039)
   - Update `ANTHROPIC_ENTITY_MODEL` → `claude-haiku-4-5-20251001`

4. **Add Anthropic credits** — Manual. Add $10-15 to console.anthropic.com.

5. **Verify health endpoint is fully green** — All 4 checks should pass.

6. **Set up UptimeRobot** — Point at health endpoint, 5-min interval, keyword check for `"status":"healthy"`. Start 72-hour burn-in clock (replaces custom script approach for TASK-028).

---

## Previous Session

- TASK-027 (Health Check & Site Status) completed — 20/20 tests, PR #232 ready for merge
- TASK-026 (Fix Active LLM Failures) completed — structured `LLMError` class, 31/31 tests passing
- TASK-025 fully merged and deployed — rate limiting, circuit breaker, spend logging (42/42 tests)
- PRs #227-#231 all merged to main

---

## Known Issues / Blockers

- **Redis not connected** — rate limiter and circuit breaker silently disabled (TASK-031 fixes this)
- **Anthropic credits at $0** — all LLM systems down (add credits after TASK-031)
- **SMTP password in Git history** — BUG-053 addresses config, but password remains in Git history (low priority for private repo)
- **TASK-030 (Rename GitHub Repo)** still open — manual GitHub UI task, 15 min
- **PR #232 (TASK-027)** needs merge to main before TASK-031 branch

---

## Key Files

**TASK-031 (modify/create):**
- `src/crypto_news_aggregator/core/redis_rest_client.py` — REWRITE: Upstash REST → redis-py
- `src/crypto_news_aggregator/core/config.py` — add REDIS_URL field, remove Upstash fields
- `tests/unit/test_redis_client.py` — NEW: 8 unit tests for new client

**TASK-031 (verify unchanged — same interface):**
- `src/crypto_news_aggregator/services/rate_limiter.py` — imports redis_client, calls get/incr/expire/delete
- `src/crypto_news_aggregator/services/circuit_breaker.py` — imports redis_client, calls get/set/incr/expire/delete
- `src/crypto_news_aggregator/api/v1/health.py` — imports redis_client, calls ping()

**BUG-053 (modify):**
- `src/crypto_news_aggregator/core/config.py` — remove hardcoded SMTP credentials

**Reference (do not modify):**
- `src/crypto_news_aggregator/db/mongodb.py` — mongo_manager
- `src/crypto_news_aggregator/llm/anthropic.py` — LLM client pattern
- `context-owl-ui/src/api/client.ts` — API client pattern

---

## Railway Service Configuration (current)

| Service | Start Command | Memory Limit |
|---------|--------------|--------------|
| celery-worker | `cd src && celery -A crypto_news_aggregator.tasks worker --loglevel=info --queues=default,news,price,alerts,briefings --pool=solo --max-tasks-per-child=50` | 1 GB |
| crypto-news-aggregator | (default) | 1 GB |
| celery-beat | (default) | 1 GB |
| Redis | (Railway managed) | (default) |

**Railway Redis internal URL:** `redis://default:...@redis.railway.internal:6379`

---

## Cost Targets

| Item | Monthly Target |
|------|---------------|
| Anthropic LLM | ~$10 |
| Railway infra | ~$16-19 (projected after memory fix) |
| **Total** | **~$26-29** |

---

## Files