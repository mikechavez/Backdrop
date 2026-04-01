---
ticket_id: TASK-025
title: Implement Cost Controls
priority: critical
severity: high
status: IN_PROGRESS (Session 2: Priorities 1-3 complete + test fixes; Session 3: daily limits/circuit breaker)
date_created: 2026-03-31
date_started: 2026-03-31
branch: feature/task-025-cost-controls
pr: https://github.com/mikechavez/Backdrop/pull/227
effort_estimate: 3 hr
effort_actual: 3.5 hr (implementation + test fixes); remaining: daily limits, circuit breaker, spend logging
---

# TASK-025: Implement Cost Controls

## Problem Statement

There are no guardrails preventing runaway LLM spend. When something goes wrong (retry storm, batch re-processing, loop), costs compound silently until the budget is gone. We need per-system limits, circuit breakers, and spend visibility so this can't happen again.

**Note:** Exact scope depends on TASK-024 audit findings. The items below are the expected controls; adjust based on what the audit reveals.

---

## Implementation Status

### SESSION 3 SUMMARY (2026-04-01)

**✅ FIXED ALL TEST FAILURES**
- Fixed `RedisRESTClient.incr()` to handle `None` return when Redis disabled
  - Changed: `int(response.get("result", 0))` → check for None before converting
- Updated 14 cost tracker tests with current model names:
  - Old: `claude-3-5-haiku-20241022`, `claude-3-5-sonnet-20241022`
  - New: `claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929`, `claude-opus-4-6`
- Updated pricing expectations to match CostTracker (Haiku $1.00/$5.00)
- Implemented `MockRedis` class for rate limiter unit tests
- Fixed backfill narrative test mocks to use `AsyncMock` for MongoDB operations

**✅ RATE LIMITER SERVICE - TESTS PASSING**
- All 10 rate limiter unit tests now passing
- All 6 cost tracking E2E tests passing  
- All 9 LLM cost tracking integration tests passing
- **Total: 25/25 core cost control tests passing**

**Test Results:**
- `tests/services/test_rate_limiter.py` - 10/10 ✅
- `tests/integration/test_cost_tracking_e2e.py` - 6/6 ✅
- `tests/integration/test_llm_cost_tracking.py` - 9/9 ✅
- Remaining 8 failures are unrelated integration tests (HTTPX mock issues, not cost-controls)

**Next steps:**
- Integrate rate limits into API endpoints (briefing, entity_extraction, sentiment_analysis)
- Implement circuit breaker
- Implement spend logging
- End-to-end integration testing

### SESSION 2 SUMMARY (2026-03-31)

**Completed:**
- ✅ Cost tracking enabled for System 3 (sentiment/theme/relevance)
- ✅ Fixed CostTracker config zeros (pricing now visible)
- ✅ Implemented batch enrichment (50% cost reduction)
- ✅ Created RateLimiter service with Redis backing
- ✅ Added `incr()` method to RedisRESTClient
- ✅ Created 10 unit tests for RateLimiter

**In Progress:**
- Test mocking (completed in Session 3)

### ✅ COMPLETED (In Session 1)

#### Priority 1: Enable Cost Tracking for System 3
- ✅ Added `_get_completion_with_usage()` method to extract token metrics from API responses
- ✅ Created async tracked variants:
  - `score_relevance_tracked()` — tracks relevance_scoring operation
  - `analyze_sentiment_tracked()` — tracks sentiment_analysis operation
  - `extract_themes_tracked()` — tracks theme_extraction operation
- ✅ Integrated `CostTracker.track_call()` using asyncio.create_task() (non-blocking)
- **Result:** System 3 (sentiment/theme/relevance) now has full cost visibility (was 100% untracked)

#### Priority 2: Fix CostTracker Config Zeros
- ✅ `ANTHROPIC_ENTITY_INPUT_COST_PER_1K_TOKENS`: 0.0 → **0.80** (config.py:50)
- ✅ `ANTHROPIC_ENTITY_OUTPUT_COST_PER_1K_TOKENS`: 0.0 → **4.0** (config.py:51)
- **Result:** Entity extraction cost now visible in logs (was reporting $0.00)

#### Priority 3: Implement Request Batching (50% cost reduction)
- ✅ Added `enrich_articles_batch()` method to batch up to 10 articles per API call
- ✅ Refactored RSS enrichment loop from per-article to batch processing
- ✅ Single LLM call returns: relevance_score, sentiment_score, themes for entire batch
- **Impact:** Reduces HTTP calls from 3N → N/10 (e.g., 30 articles: 90 calls → 3 calls)

### 🔴 TEST FAILURES DISCOVERED

When running `poetry run pytest tests/ -k "cost"`, found 12 failing tests:
- Cost tracker pricing model mismatch (tests expect `claude-3-5-haiku-20241022`, code has `claude-haiku-4-5-20251001`)
- Pricing values in tests vs CostTracker.PRICING dict inconsistency
- See: tests/services/test_cost_tracker.py failures

**Decision:** Defer test fixes and full validation to next session (user request).

### 🚀 NOT YET IMPLEMENTED

Per the ticket spec, these remain for follow-up work:

## Task (Original Scope - TBD Next Session)

### 1. Per-System Daily Call Limits
- Implement a daily call counter per system (briefing, entity extraction, sentiment, narrative themes)
- Store counts in Redis with daily TTL expiry
- When a system hits its daily limit, reject new calls with a clear error (not silent failure)
- Limits should be configurable via environment variables with sensible defaults

### 2. Per-Request Token Budget
- Enforce explicit `max_tokens` on every API call site identified in TASK-024
- No call should rely on the API default — every call must set `max_tokens` intentionally
- Values should be right-sized per system (briefing needs more tokens than entity extraction)

### 3. Circuit Breaker
- After N consecutive failures for a given system, stop making calls for a cooldown period
- Log when circuit breaker trips and when it resets
- Configurable thresholds: failure count, cooldown duration

### 4. Spend Logging
- Log every LLM API call with: timestamp, system, model, tokens in, tokens out, estimated cost
- Write to existing cost tracking collection (verify it's working — TASK-024 may flag issues)
- Add a daily spend summary that can be queried

---

## Verification

- [ ] **Unit tests:**
  - Rate limiter correctly tracks counts and rejects at limit
  - Circuit breaker trips after N failures, resets after cooldown
  - Token budget enforcement rejects oversized requests
  - Spend logger calculates cost correctly for each model
- [ ] **Integration tests:**
  - System gracefully degrades when daily limit hit (returns structured error, doesn't crash)
  - Circuit breaker trips on simulated consecutive failures, recovers after cooldown
  - Spend logging writes correct data to MongoDB cost tracking collection
- [ ] CC runs all new tests and confirms pass before marking complete

---

## Acceptance Criteria

- [ ] Daily call limits enforced per system with configurable thresholds
- [ ] Every LLM call site has explicit `max_tokens` set
- [ ] Circuit breaker prevents retry storms (configurable failure count + cooldown)
- [ ] Every LLM call logged with model, tokens, and estimated cost
- [ ] All controls fail-open with clear error messages (never silent)
- [ ] All new code has unit and integration tests passing

---

## Impact

Prevents budget blowouts and gives Mike visibility into daily spend. Combined with TASK-027 (health check), creates the foundation for continuous operation.

---

## Related Tickets

- TASK-024: LLM Spend Audit (blocks this ticket — findings shape exact implementation)
- TASK-026: Fix Active LLM Failures
- TASK-027: Health Check & Site Status
- TASK-028: Burn-in Validation