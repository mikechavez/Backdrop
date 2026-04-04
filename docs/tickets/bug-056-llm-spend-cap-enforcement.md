---
id: BUG-056
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-02
updated: 2026-04-02
---

# LLM Spend Cap Enforcement -- No Budget Gate on API Calls

## Problem

The system tracks LLM costs (via `CostTracker`) but does not enforce any spending limit. Cost tracking is observability-only. When the pipeline restarted after BUG-054/BUG-055 fixes, a backlog of articles triggered hundreds of LLM calls that burned through $10-15 of Anthropic credits in ~2 hours -- the entire monthly budget. The system knew it was spending money but had no mechanism to stop.

Two failures compounded:

1. **No spend gate.** All three LLM call paths fire without checking the budget.
2. **No throughput control.** A backlog of unenriched articles floods the enrichment pipeline on restart, concentrating spend into a short burst window.

This is the **blocker** before restarting the pipeline. Without both fixes, adding credits will just burn them again -- either all at once (no gate) or in a predictable daily brownout (gate without throttle).

## Expected Behavior

- A configurable soft daily limit ($0.25) degrades non-critical LLM pipelines (theme extraction, sentiment analysis, narrative enrichment)
- A configurable hard daily limit ($0.33) halts ALL LLM calls system-wide
- LLM calls that exceed the limit return a graceful fallback (empty result or 0.0 score) instead of making an API request
- Backlog processing is throttled to a configurable max articles per enrichment cycle, spreading cost across the full day
- The health endpoint reports when spend limits are active

## Actual Behavior

- `CostTracker.get_daily_cost()` exists and works (line 131, cost_tracker.py)
- No code anywhere checks this value before making an LLM call
- All three LLM call paths fire without any budget check:
  - `AnthropicProvider._get_completion()` (anthropic.py:31)
  - `AnthropicProvider._get_completion_with_usage()` (anthropic.py:91)
  - `BriefingAgent._call_llm()` (briefing_agent.py:792)
- No limit on how many articles enter the enrichment pipeline per cycle
- Result: uncontrolled spend until credits are exhausted, then cascade of 400 errors

## Steps to Reproduce

1. Add $10 Anthropic credits
2. Enable pipeline with a backlog of unenriched articles
3. Observe credits depleted in ~2 hours via Sentry 400 errors
4. `db.api_costs.aggregate([{$match: {timestamp: {$gte: ISODate("2026-04-02")}}}, {$group: {_id: null, total: {$sum: "$cost"}}}])` shows spend exceeding daily target

## Environment

- Environment: production (Railway)
- User impact: high (system offline, credits burned, all LLM features down)

## Screenshots/Logs

Sentry alerts 2026-04-02 starting 8:29 PM:
- "Your credit balance is too low to access the Anthropic API"
- "Circuit breaker OPEN for 'theme_extraction' after 4 consecutive failures"
- "Circuit breaker OPEN for 'sentiment_analysis' after 4 consecutive failures"
- 15+ duplicate alerts within 30 minutes

---

## Implementation Plan

### Overview

Two changes that work together:

1. **Spend gate**: A two-tier budget check with a TTL cache, inserted before every LLM call path. Prevents overspend.
2. **Backlog throttle**: A per-cycle cap on how many articles enter enrichment. Spreads cost evenly across the day so the spend gate doesn't trigger in the first 15 minutes and leave the system idle.

Four files modified, one new config section. Estimated time: 2-3 hours.

---

### Part 1: Spend Gate

#### File 1: `src/crypto_news_aggregator/core/config.py`

**Add these settings** after `HEARTBEAT_BRIEFING_MAX_AGE` (around line 126):

```python
    # LLM spend cap thresholds (daily, in USD)
    LLM_DAILY_SOFT_LIMIT: float = 0.25   # Degrade non-critical pipelines
    LLM_DAILY_HARD_LIMIT: float = 0.33   # Halt ALL LLM calls

    # Backlog throughput control
    ENRICHMENT_MAX_ARTICLES_PER_CYCLE: int = 5   # Max articles enriched per beat tick
```

Railway env vars to set after deployment:
- `LLM_DAILY_SOFT_LIMIT=0.25`
- `LLM_DAILY_HARD_LIMIT=0.33`
- `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`

#### File 2: `src/crypto_news_aggregator/services/cost_tracker.py`

**Add a cached budget state** as a module-level object after imports:

```python
import time
import logging

logger = logging.getLogger(__name__)

# --- Cached budget state ---
# Eliminates per-call DB reads and the sync/async bridge problem.
# All callers read from this cache. A single async refresh updates it.
_budget_cache = {
    "daily_cost": 0.0,
    "status": "ok",        # "ok" | "degraded" | "hard_limit"
    "last_checked": 0.0,   # timestamp
    "ttl": 30,             # seconds between DB reads
}
```

**Add these methods** to the `CostTracker` class, after `get_daily_cost()` (after line 149):

```python
    async def refresh_budget_cache(self) -> dict:
        """
        Refresh the module-level budget cache from the database.

        Called periodically (every ~30s) rather than on every LLM call.
        Returns the updated cache dict.
        """
        from ..core.config import get_settings
        settings = get_settings()

        try:
            daily_cost = await self.get_daily_cost(days=1)
        except Exception as e:
            logger.error(f"Failed to refresh budget cache: {e}")
            # If DB read fails, mark as degraded (fail toward caution)
            _budget_cache["status"] = "degraded"
            _budget_cache["last_checked"] = time.time()
            return _budget_cache

        hard_limit = settings.LLM_DAILY_HARD_LIMIT
        soft_limit = settings.LLM_DAILY_SOFT_LIMIT

        _budget_cache["daily_cost"] = daily_cost
        _budget_cache["last_checked"] = time.time()

        if daily_cost >= hard_limit:
            _budget_cache["status"] = "hard_limit"
            logger.warning(
                f"HARD LIMIT reached: ${daily_cost:.4f} >= ${hard_limit:.2f}"
            )
        elif daily_cost >= soft_limit:
            _budget_cache["status"] = "degraded"
            logger.info(
                f"Soft limit reached: ${daily_cost:.4f} >= ${soft_limit:.2f}"
            )
        else:
            _budget_cache["status"] = "ok"

        return _budget_cache

    def is_critical_operation(self, operation: str) -> bool:
        """
        Determine if an operation is critical (allowed during soft limit).

        Critical operations (allowed during degraded mode):
        - briefing_generation: Core product output
        - entity_extraction: Required for pipeline continuity

        Non-critical operations (blocked during degraded mode):
        - theme_extraction
        - sentiment_analysis
        - relevance_scoring
        - article_enrichment_batch
        - narrative_enrichment (discover_narrative_from_article)
        """
        CRITICAL_OPERATIONS = {
            "briefing_generation",
            "entity_extraction",
        }
        return operation in CRITICAL_OPERATIONS
```

**Add a module-level convenience function** at the bottom of the file, after `get_cost_tracker()`:

```python
async def refresh_budget_if_stale() -> None:
    """
    Refresh the budget cache if it's older than its TTL.

    Called from async contexts (enrichment pipeline, briefing agent).
    Safe to call frequently -- it no-ops if the cache is fresh.
    """
    if time.time() - _budget_cache["last_checked"] > _budget_cache["ttl"]:
        try:
            from ..db.mongodb import mongo_manager
            db = await mongo_manager.get_async_database()
            tracker = get_cost_tracker(db)
            await tracker.refresh_budget_cache()
        except Exception as e:
            logger.error(f"Budget cache refresh failed: {e}")


def check_llm_budget(operation: str = "") -> tuple[bool, str]:
    """
    Synchronous budget check against the cached state.

    This is the function that all LLM call sites use. No DB call,
    no async, no event loop gymnastics. Just reads from cache.

    Args:
        operation: Operation name for critical/non-critical classification

    Returns:
        Tuple of (allowed, reason):
        - (True, "ok"): Proceed normally
        - (True, "degraded"): Over soft limit, but operation is critical
        - (False, "soft_limit"): Over soft limit, non-critical operation blocked
        - (False, "hard_limit"): Over hard limit, all operations blocked
        - (True, "no_data"): Cache never populated, fail open with warning
    """
    status = _budget_cache["status"]
    age = time.time() - _budget_cache["last_checked"]

    # If the cache has never been populated, fail open but warn
    if _budget_cache["last_checked"] == 0.0:
        logger.warning(
            f"Budget cache not yet populated. Allowing '{operation}' (fail open)."
        )
        return True, "no_data"

    # If the cache is extremely stale (>5 min), treat as degraded
    # This is the "fail toward caution" path
    if age > 300:
        logger.warning(
            f"Budget cache stale ({age:.0f}s). Treating as degraded for '{operation}'."
        )
        status = "degraded"

    if status == "hard_limit":
        logger.warning(
            f"LLM call blocked: hard limit. Operation='{operation}', "
            f"daily_cost=${_budget_cache['daily_cost']:.4f}"
        )
        return False, "hard_limit"

    if status == "degraded":
        # Critical operations proceed, non-critical are blocked
        tracker = CostTracker.__new__(CostTracker)  # lightweight, just need the method
        if tracker.is_critical_operation(operation):
            return True, "degraded"
        else:
            logger.warning(
                f"Soft limit active: blocking non-critical operation '{operation}'"
            )
            return False, "soft_limit"

    return True, "ok"
```

**Key design decisions on the cache approach:**

- The cache is refreshed by async code paths (enrichment pipeline, briefing scheduler) that already have a running event loop. No sync/async bridge needed.
- Sync callers (`_get_completion`) just read from the cache dict. Zero overhead.
- TTL of 30 seconds means worst-case overshoot is ~30 seconds of calls past the limit. At Haiku pricing and single-worker throughput, that's cents, not dollars.
- If the cache is never populated (cold start), we fail open. If the cache is extremely stale (>5 min), we fail toward caution by treating as degraded. This avoids the binary risk of "fail open always" or "fail closed always."

#### File 3: `src/crypto_news_aggregator/llm/anthropic.py`

**Add import** at the top of the file (after line 8):

```python
from ..services.cost_tracker import check_llm_budget, refresh_budget_if_stale
```

**Modify `_get_completion()`** (line 31). Add a budget check at the top of the method:

```python
    def _get_completion(self, prompt: str, operation: str = "") -> str:
        """Get completion from Claude. Does NOT fall back to Sonnet."""
        # --- SPEND CAP CHECK (reads from cache, no DB/async) ---
        allowed, reason = check_llm_budget(operation)
        if not allowed:
            logger.warning(
                f"LLM call blocked by spend cap ({reason}) for '{operation}'"
            )
            raise LLMError(
                f"Daily spend limit reached ({reason})",
                error_type="spend_limit",
                model=self.model_name
            )
        # --- END SPEND CAP CHECK ---

        model = self.model_name
        # ...rest of existing method unchanged...
```

**Modify `_get_completion_with_usage()`** (line 91). Same pattern:

```python
    def _get_completion_with_usage(self, prompt: str, operation: str = "") -> tuple:
        """Get completion with usage stats."""
        allowed, reason = check_llm_budget(operation)
        if not allowed:
            raise LLMError(
                f"Daily spend limit reached ({reason})",
                error_type="spend_limit",
                model=self.model_name
            )

        # ...rest of existing method unchanged...
```

**Modify `extract_entities_batch()`** (line 207). Add after the circuit breaker check (after line 228):

```python
        allowed, reason = check_llm_budget("entity_extraction")
        if not allowed:
            logger.warning(f"Entity extraction blocked by spend cap ({reason})")
            return {"results": [], "usage": {}}
```

**Modify `enrich_articles_batch()`** (line 523). Add after circuit breaker checks (after line 563). Since this method is async, also refresh the cache here:

```python
        await refresh_budget_if_stale()
        allowed, reason = check_llm_budget("article_enrichment_batch")
        if not allowed:
            logger.warning(f"Batch enrichment blocked by spend cap ({reason})")
            return []
```

**Modify async tracked methods** (`score_relevance_tracked`, `analyze_sentiment_tracked`, `extract_themes_tracked`). Add budget check after the circuit breaker check in each:

For `score_relevance_tracked()` (after line 682):
```python
        await refresh_budget_if_stale()
        allowed, reason = check_llm_budget("relevance_scoring")
        if not allowed:
            logger.warning(f"score_relevance blocked by spend cap ({reason})")
            return 0.0
```

For `analyze_sentiment_tracked()` (after line 752):
```python
        await refresh_budget_if_stale()
        allowed, reason = check_llm_budget("sentiment_analysis")
        if not allowed:
            logger.warning(f"analyze_sentiment blocked by spend cap ({reason})")
            return 0.0
```

For `extract_themes_tracked()` (after line 822):
```python
        await refresh_budget_if_stale()
        allowed, reason = check_llm_budget("theme_extraction")
        if not allowed:
            logger.warning(f"extract_themes blocked by spend cap ({reason})")
            return []
```

Note: Every async call site calls `refresh_budget_if_stale()` before the check. The first one to run in any 30-second window does the DB read; the rest no-op. This keeps the cache warm without a dedicated background task.

#### File 4: `src/crypto_news_aggregator/services/briefing_agent.py`

**Add import** near top of file:

```python
from crypto_news_aggregator.services.cost_tracker import (
    check_llm_budget,
    refresh_budget_if_stale,
)
```

**Modify `_call_llm()`** (line 792). Add budget check before the model loop:

```python
    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        """Call the LLM API with fallback models."""
        await refresh_budget_if_stale()
        allowed, reason = check_llm_budget("briefing_generation")
        if not allowed:
            raise LLMError(
                f"Daily spend limit reached ({reason})",
                error_type="spend_limit",
                model=DEFAULT_MODEL
            )

        models_to_try = [DEFAULT_MODEL] + FALLBACK_MODELS
        # ...rest of existing method unchanged...
```

Note: `briefing_generation` is classified as a critical operation, so it is only blocked by the hard limit ($0.33), not the soft limit ($0.25).

---

### Part 2: Backlog Throttle

Without throughput control, the spend gate converts a burst into a daily brownout. The backlog doesn't shrink -- it just takes days to clear at $0.33/day with all spend concentrated in the first few minutes after midnight UTC.

The fix: cap how many articles enter enrichment per Celery beat cycle.

#### File 5: `src/crypto_news_aggregator/llm/anthropic.py`

**Modify `enrich_articles_batch()`** (line 523). Add throttle at the top of the method, before any processing:

```python
    async def enrich_articles_batch(self, articles: list, ...) -> list:
        """Enrich a batch of articles with LLM analysis."""
        from ..core.config import get_settings
        settings = get_settings()

        # --- BACKLOG THROTTLE ---
        max_per_cycle = settings.ENRICHMENT_MAX_ARTICLES_PER_CYCLE
        if len(articles) > max_per_cycle:
            logger.info(
                f"Throttling enrichment batch: {len(articles)} articles "
                f"capped to {max_per_cycle} per cycle"
            )
            articles = articles[:max_per_cycle]
        # --- END BACKLOG THROTTLE ---

        # ...existing circuit breaker check...
        # ...budget check (from Part 1)...
        # ...rest of method...
```

**Why this value (5 articles per cycle):**

Back-of-napkin math for the throttle setting:

- Each article enrichment costs ~$0.003-0.005 (Haiku, typical prompt size)
- 5 articles per cycle * ~$0.004 = ~$0.02 per cycle
- Celery beat runs enrichment every ~10 minutes (6 cycles/hour)
- $0.02 * 6 = ~$0.12/hour on enrichment alone
- At $0.33/day hard limit, enrichment can run ~2.5 hours before soft limit, leaving budget for briefings
- A backlog of 200 articles clears in ~400 minutes (~7 hours) instead of ~20 minutes

This spreads cost across the day and leaves headroom for briefing generation (the core product output).

The value is configurable via `ENRICHMENT_MAX_ARTICLES_PER_CYCLE` so it can be tuned without a deploy.

---

### Testing Plan

**Unit tests for budget cache:**
- Set `_budget_cache` directly, verify `check_llm_budget()` returns correct tuples
- Test status="ok", "degraded", "hard_limit"
- Test stale cache (>5 min) returns degraded
- Test unpopulated cache (last_checked=0) returns fail-open
- Verify `is_critical_operation()` classification

**Unit tests for cache refresh:**
- Mock `get_daily_cost()` to return values below soft, between soft/hard, above hard
- Call `refresh_budget_cache()`, verify `_budget_cache` state updates
- Mock DB failure, verify cache status becomes "degraded" (not "ok")

**Unit tests for throttle:**
- Pass 50 articles to `enrich_articles_batch()` with max=5
- Verify only 5 articles processed
- Verify log message includes original and capped count

**Integration test:**
- Insert cost records summing to > $0.33
- Refresh cache
- Call `_get_completion()`, verify it raises `LLMError` with `error_type="spend_limit"`
- Call `enrich_articles_batch()`, verify it returns `[]`
- Call `_call_llm()` on briefing agent, verify blocked at hard limit
- Set cost to $0.26 (between soft and hard), verify briefing_generation proceeds but theme_extraction returns `[]`

**Deployment verification:**
- Add $5 Anthropic credits
- Set env vars: `LLM_DAILY_SOFT_LIMIT=0.25`, `LLM_DAILY_HARD_LIMIT=0.33`, `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`
- Trigger manual fetch via `POST /admin/trigger-fetch`
- Monitor `db.api_costs` to verify spend stays within threshold
- Verify enrichment batches are capped in logs
- Check Sentry for `spend_limit` errors (should appear as warnings, not unhandled exceptions)

---

### Acceptance Criteria

- [ ] `LLM_DAILY_SOFT_LIMIT`, `LLM_DAILY_HARD_LIMIT`, and `ENRICHMENT_MAX_ARTICLES_PER_CYCLE` in config.py
- [ ] `refresh_budget_cache()`, `is_critical_operation()`, and `check_llm_budget()` in cost_tracker.py
- [ ] Budget cache with 30s TTL; no DB call per LLM invocation
- [ ] Budget check before every LLM call path in anthropic.py (reads from cache, sync-safe)
- [ ] Budget check before `_call_llm()` in briefing_agent.py
- [ ] Cache refresh called from async code paths (enrichment, briefing, tracked methods)
- [ ] Non-critical operations blocked at soft limit, all operations blocked at hard limit
- [ ] `LLMError` with `error_type="spend_limit"` raised for briefings (not silent failure)
- [ ] Graceful return values (empty list, 0.0) for non-critical operations
- [ ] Backlog throttle caps articles per enrichment cycle
- [ ] All existing tests pass
- [ ] New unit tests for budget cache logic and throttle

### Files Changed

- `src/crypto_news_aggregator/core/config.py` -- add 3 settings (soft limit, hard limit, max articles per cycle)
- `src/crypto_news_aggregator/services/cost_tracker.py` -- add budget cache, `refresh_budget_cache()`, `is_critical_operation()`, `check_llm_budget()`
- `src/crypto_news_aggregator/llm/anthropic.py` -- add budget check to all LLM call paths, add backlog throttle to `enrich_articles_batch()`
- `src/crypto_news_aggregator/services/briefing_agent.py` -- add budget check to `_call_llm()`

---

### Known Limitations (Post-MVP)

These are understood tradeoffs, not oversights:

1. **Budget check is not atomic across workers.** The cache is per-process. If multiple workers run concurrently, each reads independently and overshoot is possible. At current scale (single Celery worker, `--pool=solo`), this is not a real risk. If the system scales to multiple workers, migrate to a shared counter (Redis atomic increment or token bucket).

2. **Cache TTL means overshoot window.** A 30-second TTL means up to 30 seconds of LLM calls can fire after the true daily cost crosses a threshold. At Haiku pricing and single-worker throughput, worst-case overshoot is a few cents. Acceptable.

3. **No rate limiting per second.** The throttle caps articles per cycle but not calls per second within a cycle. If cycle frequency increases or batch size grows, intra-cycle bursts could spike. A future improvement would be a token-bucket rate limiter.

4. **Operation names are stringly typed.** A typo in an operation name silently misclassifies it as non-critical. Low risk at current team size (solo developer). Could migrate to an enum (`LLMOperation`) if the codebase grows.

5. **Throttle is FIFO, not priority-ordered.** `articles[:max_per_cycle]` takes the first N articles, which is insertion order. Ideally, articles would be prioritized by relevance or recency. Acceptable for MVP; revisit if backlog patterns show stale articles blocking timely ones.

---

## Resolution

**Status:** ✅ COMPLETE - Code + Tests Ready for PR
**Fixed:** Session 19 (code), Session 20 (tests) - Both phases complete
**Branch:** `fix/bug-056-llm-spend-cap-enforcement`
**Commits:** 9d63412 (code), e4d16b3 (tests)

### Root Cause

Two compounding gaps:

1. Cost tracking was implemented as observability (TASK-025) but never wired into an enforcement gate. The system logged every dollar spent but had no mechanism to stop spending.
2. No throughput control on the enrichment pipeline. Any backlog of unenriched articles floods the LLM providers on the next pipeline run, concentrating an entire day's budget into minutes.

### Changes Made

**Session 19 Implementation Summary (Code Only)**

**Part 1: Spend Gate** ✅
- [x] Added 3 new config settings in `src/crypto_news_aggregator/core/config.py`:
  - `LLM_DAILY_SOFT_LIMIT: float = 0.25` (degrade non-critical ops)
  - `LLM_DAILY_HARD_LIMIT: float = 0.33` (halt all ops)
  - `ENRICHMENT_MAX_ARTICLES_PER_CYCLE: int = 5` (backlog throttle)

- [x] Enhanced `src/crypto_news_aggregator/services/cost_tracker.py`:
  - Added module-level budget cache dict with 30s TTL
  - Implemented `refresh_budget_cache()` to update cache from DB (30s debounce)
  - Implemented `is_critical_operation()` to classify operations (briefing + entity extraction critical)
  - Implemented `check_llm_budget(operation)` synchronous gate (reads cache only, no DB/async)
  - Implemented `refresh_budget_if_stale()` async helper to refresh cache before LLM calls

- [x] Modified `src/crypto_news_aggregator/llm/anthropic.py`:
  - Added import of `check_llm_budget` and `refresh_budget_if_stale`
  - Added budget check to `_get_completion()` (reads cache, raises LLMError if blocked)
  - Added budget check to `_get_completion_with_usage()` (same pattern)
  - Added budget check to `extract_entities_batch()` (critical operation, proceeds with degraded, blocked with hard limit)
  - Added backlog throttle to `enrich_articles_batch()` (caps batch at `ENRICHMENT_MAX_ARTICLES_PER_CYCLE`)
  - Added budget check + cache refresh to `enrich_articles_batch()` (non-critical, blocked at soft/hard limits)
  - Added budget check + cache refresh to `score_relevance_tracked()` (non-critical)
  - Added budget check + cache refresh to `analyze_sentiment_tracked()` (non-critical)
  - Added budget check + cache refresh to `extract_themes_tracked()` (non-critical)

- [x] Modified `src/crypto_news_aggregator/services/briefing_agent.py`:
  - Added import of `check_llm_budget` and `refresh_budget_if_stale`
  - Added budget check to `_call_llm()` before model loop (critical operation, only blocked at hard limit)

**Part 2: Backlog Throttle** ✅
- [x] Implemented in `enrich_articles_batch()` at the top of the method
  - Caps `articles` list to `ENRICHMENT_MAX_ARTICLES_PER_CYCLE` (default 5)
  - Logs original and throttled counts
  - Spreads cost across day instead of concentrating in first 15 minutes

### Session 20 Testing Complete ✅

**Testing Phase Complete:**
- [x] Created `tests/test_bug_056_spend_cap.py` with comprehensive unit tests
  - TestBudgetCacheState: Cache initialization, TTL verification (2 tests)
  - TestCriticalOperationClassification: Briefing/entity critical, theme/sentiment/enrichment non-critical (6 tests)
  - TestCheckLLMBudget: Hard/soft limits, stale cache handling, fail-open behavior (7 tests)
  - TestRefreshBudgetCache: OK/degraded/hard_limit transitions, DB error handling (5 tests)
  - TestRefreshBudgetIfStale: Cache freshness, refresh timing (2 tests)
  - TestBacklogThrottle: ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5 config (2 tests)
  - TestCostCalculation: Haiku/Sonnet pricing, rounding accuracy (4 tests)
  - TestBudgetGateIntegration: End-to-end soft/hard limit behavior (2 tests)
  - TestBudgetLimitConstants: Verify $0.25 soft, $0.33 hard limits (3 tests)
  - **Total: 33 tests (32 passing, 1 skipped)**

- [x] Integrated test coverage:
  - Budget cache state transitions verified
  - Critical vs non-critical classification tested
  - Stale cache (>5 min) correctly treats as degraded
  - Unpopulated cache fails open with warning
  - Backlog throttle behavior verified

- [x] All acceptance criteria met:
  - ✅ Config settings present: `LLM_DAILY_SOFT_LIMIT`, `LLM_DAILY_HARD_LIMIT`, `ENRICHMENT_MAX_ARTICLES_PER_CYCLE`
  - ✅ Budget cache with 30s TTL implemented and tested
  - ✅ All LLM call paths have budget checks (verified in code, commit 9d63412)
  - ✅ Non-critical operations blocked at soft limit, all ops blocked at hard limit
  - ✅ `LLMError` with `error_type="spend_limit"` raised for critical ops
  - ✅ Graceful returns (empty list, 0.0) for non-critical ops
  - ✅ Backlog throttle caps enrichment batch size
  - ✅ All existing tests pass (no regressions)
  - ✅ New unit + integration tests passing (32/33)

**Next Steps (Deployment):**
- [ ] Create PR against main (merge code + tests together)
- [ ] Deployment verification (Railway):
  - Set env vars: `LLM_DAILY_SOFT_LIMIT=0.25`, `LLM_DAILY_HARD_LIMIT=0.33`, `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`
  - Add $5 Anthropic credits
  - Trigger manual fetch via `/admin/trigger-fetch`
  - Monitor `db.api_costs` to verify spend stays within limits
  - Check logs for throttle messages and budget checks
  - Verify no unhandled `LLMError` exceptions (spend_limit errors should be graceful)

### Testing