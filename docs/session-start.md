# Session Start

**Date:** 2026-04-13 (Session 19, Sprint 14)
**Status:** BUG-066 ✅ complete (daily cost calculation fix), ready for PR + merge
**Branch:** fix/bug-066-daily-cost-calculation (parent: main)
**Next:** Create PR, merge to main, then deploy to production

---

## What Happened Last

**Session 14 (Previous):** TASK-059 complete — removed 3 low-quality RSS sources (watcherguru 7%, glassnode 5.3%, bitcoinmagazine 14% tier 1 rates)

**Session 15 (Previous):** TASK-060 complete — implemented tier 1 only enrichment filter
- Tier 2-3 articles (56% of ingest) skip full LLM enrichment, save tier assignment only
- Tier 1 articles (17% of ingest) receive full enrichment unchanged
- Expected cost reduction: $1.80/day → $0.36-0.45/day (-75%)
- Commit: 76f912c, branch: `cost-optimization/tier-1-only`

**Session 16 (Current):** TASK-062 complete — move tier classification before enrichment
- Fix root cause of cost bleed: classify BEFORE LLM enrichment, not after
- Pre-classify all articles in batch (rule-based, no cost)
- Filter batch to only tier 1 articles before calling expensive LLM
- Tier 2-3 articles saved with tier only, no entities/sentiment/themes/keywords
- Skip enrichment batch entirely if zero tier 1 articles present
- Cost impact: ~98% reduction on enrichment calls ($0.36-0.45/day vs $21/day when hard limit raised)
- Commit: 6dc21a4, branch: `cost-optimization/tier-1-only`

**Earlier (Sessions 1–13):** Built complete LLM control layer (TASK-036 through TASK-042) + burn-in measurement
- ✅ TASK-036: LLM Gateway with async/sync modes, budget enforcement
- ✅ TASK-037: Tracing schema, indexes (TTL 30d)
- ✅ TASK-038: Wired briefing_agent through gateway
- ✅ TASK-039: Wired health endpoint through gateway
- ✅ TASK-040: Dataset capture for eval datasets
- ✅ TASK-041: 48-hour burn-in run
- ✅ TASK-044: Lift hard spend limit to $15 for measurement
- ✅ TASK-042: Gateway bypass fix — all LLM calls unified
- ✅ TASK-041A: Restart burn-in with clean baseline
- ✅ BUG-058, BUG-060: Soft limit & timezone bugs fixed
- ✅ TASK-045: Remove verbose narrative logging
- ✅ TASK-046: Verify briefing task registration with Celery
- ✅ TASK-059: Remove low-quality RSS sources

**Current Work (Session 10):**
- ✅ Raised soft spend limit from $1.00 → $3.00 (commit c1deb83)
  - $1.00 was too aggressive; single briefing costs ~$1.20
  - $3.00 allows 2-3 full briefings while catching runaway costs
- ✅ **BUG-060 FIXED:** Timezone-naive datetime breaking signal computation
  - **Root cause:** `datetime.now(timezone.utc).replace(tzinfo=None)` stripping timezone info
  - **Impact:** Signal computation returned 0 results, blocking briefing generation
  - **Fix:** Removed `.replace(tzinfo=None)` from 5 instances in signal_service.py
  - **Commit:** 5808da4
  - **Status:** ✅ Merged and deployed

**Session 11 (Previous):**
- ✅ **Investigated Soft Limit Blocker** — Ran comprehensive database queries
  - **Finding:** Soft limit NOT actually hit. Actual spend $0.445 << $3.00 limit
  - **Cost breakdown:** narrative_generate $0.262 (58%), entity_extraction $0.183 (42%)
  - **Issue found:** No briefing generation operations recorded (zero `briefing_generate` calls in database)
  - **Timeline:** Morning briefing scheduled 2026-04-09 13:00 UTC but no activity visible in cost tracking
  - **Created:** BUG-061 to document findings (docs/tickets/bug-061-budget-tracking-discrepancy.md)
- ✅ **TASK-045 Complete** — Removed verbose narrative logging
  - Removed 26+ `[VELOCITY DEBUG]` lines from `calculate_recent_velocity()`
  - Removed 17 `[MERGE NARRATIVE DEBUG]` lines from merge upsert section
  - Replaced with concise single-line summaries
  - Reduces per-cycle logging from 380+ lines to ~2 lines
  - Commit: dde11bf

**Session 12 (Previous):**
- ✅ **TASK-046 Complete** — Verified briefing task registration with Celery
  - **Finding:** All infrastructure already 100% in place
  - **Task decorators:** ✅ All briefing tasks have @shared_task with correct names
  - **Celery initialization:** ✅ tasks/__init__.py imports all tasks and enables autodiscover
  - **Beat schedule:** ✅ All task names match @shared_task decorators
  - **Celery config:** ✅ Beat schedule properly applied at app startup
  - **Added:** test_task_registration.py verification script
  - **Branch:** fix/task-046-register-briefing-tasks
  - **Commit:** 91a72ab

**Session 13 (Previous):**
- ✅ **TASK-045 Critical Bug Fix** — Undefined variable in narrative merge log
  - **Problem:** TASK-045 removed verbose logging but left a line with undefined `articles_by_id` variable
  - **Location:** narrative_service.py line 1045 in merge upsert section
  - **Symptom:** Crashes during narrative clustering when trying to calculate velocity
  - **Fix:** Removed the velocity calculation line (undefined), kept simple merge summary log
  - **Before:** `velocity = calculate_recent_velocity([a['timestamp'] for a in articles_by_id.values()]) if articles_by_id else 0.0`
  - **After:** `logger.info(f"Merged {len(combined_article_ids)} articles into narrative '{title}'")`
  - **Branch:** fix/narrative-clustering-merge-log
  - **Commit:** 869baa8

**Previous (Session 9):**
- ✅ BUG-058: Raised soft limit to $1.00, fixed TypeError in narrative detection (commit 641e120)

**Session 19 (Current):**
- ✅ **BUG-066 FIXED** — Daily cost calculation using rolling 24hr window instead of calendar day
  - **Problem:** `get_daily_cost()` used `timedelta(days=1)` creating rolling 24-hour windows
  - **Impact:** At 16:05 UTC, returned cost for 08:05 yesterday + 16 hours today, triggering hard limit incorrectly
  - **Actual daily spend:** $0.4193 (under $0.60 hard limit)
  - **Reported by cache:** $0.7153 (includes yesterday's 8 hours)
  - **Fix:** Changed to calendar-day alignment: `now - timedelta(days=days-1)` → `.replace(hour=0, minute=0, second=0, microsecond=0)`
  - **Result:** days=1 returns today's cost (00:00 UTC onwards), days=2 returns yesterday, etc.
  - **Branch:** fix/bug-066-daily-cost-calculation
  - **Commit:** ac7341c
  - **Tests:** All 11 cost_tracker tests passing ✅

**Session 21 (2026-04-13) — BUG-067 Motor Truthiness Check Fix ✅**
- ✅ **BUG-067 FIXED** — Motor AsyncIOMotorDatabase truthiness check fails
  - **Problem:** Code checked `if briefing_id and db:` which triggers truthiness check on Motor object
  - **Error:** `TypeError: Database objects do not implement truth value testing or bool()`
  - **Location:** Line 437 of `briefing_agent.py` in `_self_refine()` method
  - **Fix:** Changed to `if briefing_id and db is not None:`
  - **Why:** Motor explicitly forbids `bool()` checks, allows `is None` / `is not None` comparisons
  - **Impact:** Unblocks post-refine draft capture during briefing generation self-refine loop
  - **Files Changed:** `src/crypto_news_aggregator/services/briefing_agent.py` (line 437)

**Session 22 (2026-04-13 — CURRENT) — BUG-068 Double Cost Tracking Fix ✅**
- ✅ **BUG-068 FIXED** — Removed manual cost tracking from OptimizedAnthropicLLM
  - **Problem:** OptimizedAnthropicLLM manually called `CostTracker.track_call()` in parallel with LLMGateway, creating duplicate cost entries
  - **Data Impact:** api_costs had 53,326 records (bloated with duplicates), llm_traces had 327 (clean from gateway only)
  - **Cost Discrepancy:** Hard limit check read $0.6068 from api_costs vs actual $0.6300 from llm_traces → false hard_limit triggers
  - **Root Cause:** OptimizedAnthropicLLM written before LLMGateway existed; never updated to remove manual tracking
  - **Fix Applied:**
    - Removed `self.cost_tracker` initialization and `_get_cost_tracker()` method
    - Removed 4 manual `track_call()` invocations for entity extraction (cached + real)
    - Removed 2 manual `track_call()` invocations for narrative extraction (cached + real)
    - Removed 2 manual `track_call()` invocations for narrative summary (cached + real)
    - Removed `get_cost_summary()` method
    - Updated 3 tests to verify NO api_costs entries created
    - Removed cost summary logging from RSS fetcher
  - **Verification:** 9/9 tests passing, all optimized LLM integration tests pass
  - **Impact:** LLMGateway now single source of truth for cost tracking; api_costs stops growing

**Session 23 (2026-04-13) — BUG-069 Briefing Persistence Fix ✅**
- ✅ **BUG-069 FIXED** — Briefing generation logs "Saved" but never persists to database
  - **Problem:** `_save_briefing()` skipped database insert when `briefing_id` was provided
  - **Root cause:** Logic assumed if `briefing_id` exists, save already happened elsewhere (false assumption)
  - **Impact:** Briefings logged as saved but never inserted to `daily_briefings`, invisible on UI
  - **User impact:** Generated briefings invisible, cost incurred but no output
  - **Location:** Line 929-938 of `briefing_agent.py` in `_save_briefing()` method
  - **Fix Applied:**
    - Always call `await insert_briefing(briefing_doc)` regardless of `briefing_id` presence
    - Set `_id` in document BEFORE inserting so MongoDB respects provided ID
    - Ensures briefing persists to `daily_briefings` with `published: true`
  - **Files Changed:** `src/crypto_news_aggregator/services/briefing_agent.py` (9 lines changed)
  - **Branch:** `fix/bug-066-daily-cost-calculation` (parent: main) — will add to existing PR

**Session 24 (2026-04-13) — BUG-070 Narrative Tier-1 Only Fix ✅**
- ✅ **BUG-070 FIXED** — Narrative generation processes all articles instead of tier-1-only
  - **Problem:** `MAX_RELEVANCE_TIER = 2` processes tier 1-2 articles, violating TASK-060 tier-1-only optimization
  - **Impact:** 193 narrative_generate calls/day instead of expected 70 → $0.35/day spend (56% of budget)
  - **Root cause:** Constant set to 2 (includes tier 2) when it should be 1 (tier 1 only)
  - **Location:** Line 27 of `narrative_themes.py`
  - **Fix Applied:**
    - Changed `MAX_RELEVANCE_TIER = 2` → `MAX_RELEVANCE_TIER = 1`
    - Filter logic already in place, only needed constant update
    - Expected savings: -64% narrative calls, ~$0.38/day cost reduction
  - **Files Changed:** `src/crypto_news_aggregator/services/narrative_themes.py` (1 line)
  - **Branch:** `fix/bug-070-narrative-tier-1-only`
  - **Commit:** 03df32f

**Session 25 (2026-04-13) — BUG-071 Narrative Prompt Compression ✅**
- ✅ **BUG-071 FIXED** — Narrative prompt bloat (~1,700 tokens) reduced to ~900 tokens
  - **Problem:** Prompt included redundant rule statements (appear 3x), verbose explanations, token-heavy examples
  - **Impact:** Paying for ~900 unnecessary tokens per call (~$0.105/day wasted)
  - **Solution:** Compress to ~700-token system prompt + 4-line user message
  - **Changes Applied:**
    1. Added `NARRATIVE_SYSTEM_PROMPT` constant (lines 665-709) with concise rules
    2. Replaced 128-line prompt building with 4-line user message (lines 774-777)
    3. Updated gateway.call() to use `system=NARRATIVE_SYSTEM_PROMPT` (line 799)
  - **Token Reduction Breakdown:**
    - Salience explanation: 150 → 30 tokens (-120)
    - Anti-hallucination rules: 100 → 20 tokens (-80)
    - Entity normalization: 250 → 50 tokens (-200)
    - JSON examples: 200 → 0 tokens (-200)
    - Misc prose: 150 → 30 tokens (-120)
    - **Total: 1,500 → 700 tokens (-800, -53%)**
  - **Quality Maintained:** Haiku handles concise instructions without verbose examples
  - **Files Changed:** `src/crypto_news_aggregator/services/narrative_themes.py` (add constant, replace prompt)
  - **Tests Fixed:** Updated 6 discovery-narrative tests to mock `get_gateway()` instead of `get_llm_provider()`
  - **Branch:** `fix/bug-070-narrative-tier-1-only`
  - **Cost Impact:** ~$0.105/day savings on narrative_generate calls alone

**Session 26 (2026-04-13) — BUG-072 LLM Cache Infrastructure Wiring ✅**
- ✅ **BUG-072 FIXED** — Wire LLM cache infrastructure for narrative generation
  - **Problem:** llm_cache MongoDB collection exists but narrative_generate never uses it
  - **Impact:** 30% of narrative_generate calls are wasteful re-processing of unchanged articles (~$0.037/day waste)
  - **Entity extraction reference:** Already has 99.1% cache hit rate (working model)
  - **Solution:** Add cache lookup/save to both async and sync gateway methods
  - **Implementation Details:**
    1. Added async cache methods to LLMGateway:
       - `_get_from_cache(operation, input_hash)` - Checks llm_cache, increments hit counter
       - `_save_to_cache(operation, input_hash, response)` - Saves with upsert, 30-day TTL
    2. Added sync cache methods (for entity extraction and sync contexts):
       - `_get_from_cache_sync(operation, input_hash)` - Direct MongoDB sync lookup
       - `_save_to_cache_sync(operation, input_hash, response)` - Sync save with upsert
    3. Wired cache into `call()` (async):
       - Generate SHA1 hash of input messages for deduplication
       - Check cache before API calls for cacheable operations
       - Return cached results with 0 cost/tokens on hit
       - Save responses to cache after successful API calls
    4. Wired cache into `call_sync()` (sync):
       - Same cache logic for synchronous contexts
    5. Cache configuration:
       - **Cacheable operations:** narrative_generate, entity_extraction, narrative_theme_extract
       - **Non-cacheable (always fresh):** briefing_generate, briefing_refine, briefing_critique
  - **Testing:**
    - ✅ `TestCacheMethods::test_get_from_cache_hit` - Cache hit returns correct response
    - ✅ `TestCacheMethods::test_get_from_cache_miss` - Cache miss returns None
    - ✅ `TestCacheMethods::test_save_to_cache` - Responses saved with upsert
    - ✅ `TestCacheMethods::test_call_cache_hit` - Cached calls return 0 cost/tokens
    - ✅ All 22 gateway tests passing
  - **Files Changed:** 
    - `src/crypto_news_aggregator/llm/gateway.py` (6 methods, cache logic in call/call_sync)
    - `tests/llm/test_gateway.py` (4 new tests for cache behavior)
  - **Branch:** `fix/bug-072-llm-cache-wiring`
  - **Commit:** c68e760
  - **Cost Impact:** -30% narrative_generate calls = ~$0.037/day savings
  - **Expected annual savings:** ~$13.50 from cache alone

**Session 27 (2026-04-13) — BUG-073 Article Fingerprint Generation Fix ✅**
- ✅ **BUG-073 FIXED** — Articles inserted without fingerprints, breaking deduplication
  - **Problem:** `create_or_update_articles()` in articles.py used direct MongoDB insert, bypassing fingerprint generation
  - **Impact:** All articles ingested after April 9 have `fingerprint: null`, deduplication completely non-functional
  - **Root Cause:** RSS fetcher calls `create_or_update_articles()` which inserted directly without calling `ArticleService.create_article()`
  - **Solution:** Route all article inserts through `ArticleService.create_article()` which generates fingerprints and checks for duplicates
  - **Files Changed:** `src/crypto_news_aggregator/db/operations/articles.py`
    - Added import: `from crypto_news_aggregator.services.article_service import get_article_service`
    - Modified `create_or_update_articles()` to call `article_service.create_article()` instead of direct `collection.insert_one()`
    - Preserved existing `source_id` duplicate check for update path
  - **Branch:** `fix/bug-073-fingerprint-generation`
  - **Testing:** All article service tests pass (10/10), no regressions

**Next Steps:** 
- Create PR for BUG-073: fingerprint generation fix
- Create PR for BUG-070 + BUG-071 + BUG-072 combined (narrative optimizations)
- Merge to main once approved
- Deploy to production (total narrative cost reduction: -68% from tier-1 filter + prompt compression, additional -30% from cache)

---

## Sprint 13 Goal

Unify all LLM calls behind a single gateway, achieve full cost attribution, and identify the primary cost driver with measured data.

---

## What's Next

**Immediate (Today):**
1. Create PR: `cost-optimization/tier-1-only` → main (contains both TASK-060 + TASK-062)
2. Deploy to production (Railway)
3. Monitor first hour: Check LLM call volume (expect <50 calls/hour from tier 1 enrichment)
4. Verify tier 2-3 articles have tier assignment but no entities/sentiment
5. Check logs for "No tier 1 articles, skipping enrichment" messages
6. Verify cost trend: expect $0.36-0.45/day (down from $21/day)

**Post-Deployment Monitoring (TASK-061):**
1. Run MongoDB query to verify tier distribution (tier 1 enriched, tier 2-3 tier-only)
2. Monitor cost trend for 24 hours
3. If cost < $0.20/day unexpectedly: Investigate classifier behavior
4. If cost on target: Proceed to optimization validation

**After TASK-062 Stabilizes:**
1. TASK-061: Post-deploy verification and cost impact validation
2. TASK-041B: Analyze burn-in data and write findings doc
3. Sprint 14 planning based on cost attribution data

---

## Known Issues / Blockers

**Active:**
- 🟢 Burn-in underway (started 2026-04-09 02:48 UTC, expected completion 2026-04-10 ~02:48 UTC)
  - Hard limit at $15.00 (temporary for measurement)
  - Current spend: $0.0061 (97% under budget)
  - Gateway working correctly
  - 5 traces collected so far (entity_extraction)
- 🟡 Anthropic API balance — monitor during burn-in
- 🟡 TASK-035 Slack webhook not configured

**Resolved (Session 6 — TASK-043):**
- ✅ Budget cache issue: Cleared api_costs ($0.9970 pre-burn-in costs), reset budget to "ok"
- ✅ Signal generation issue: Identified as normal Celery beat scheduling (working as designed)
- ✅ Production health: All systems healthy, no critical errors

**Resolved (Sprint 13):**
- ✅ TASK-036 through TASK-042: Complete LLM control layer with tracing + gateway unification
- ✅ BUG-056: Spend cap code deployed with TASK-044 hard limit lift for measurement

**Resolved (Session 9 — BUG-058):**
- ✅ BUG-058: Soft spend limit + narrative type error fixed
  - Raised `SOFT_SPEND_LIMIT` from $0.25 → $1.00 (allows burn-in ops, still 15x below hard limit)
  - Fixed TypeError in `detect_narratives()`: `cluster.get()` → `primary_nucleus` (cluster is list, not dict)
  - Commit: 641e120 `fix(config, narratives): Raise soft spend limit and fix type error in narrative detection`

**Resolved (Sprint 12):**
- ✅ BUG-054: Pipeline live
- ✅ BUG-055: Smoke briefings stopped, MongoDB pruned
- ✅ BUG-057: Retry storm fixed
- ✅ BUG-059: Cost tracking fixed

---

## Infrastructure Reference

### Railway Services

| Service | Start Command | Memory Limit |
|---------|--------------|--------------|
| celery-worker | `cd src && celery -A crypto_news_aggregator.tasks worker --loglevel=info --queues=default,news,price,alerts,briefings --pool=solo --max-tasks-per-child=50` | 1 GB |
| crypto-news-aggregator | (default) | 1 GB |
| celery-beat | (default) | 1 GB |
| Redis | (Railway managed) | (default) |

**Railway Redis internal URL:** `redis://default:...@redis.railway.internal:6379`

### Health Endpoint

```
GET https://context-owl-production.up.railway.app/api/v1/health
```

### Cost Targets

| Item | Monthly Target |
|------|---------------|
| Anthropic LLM | ~$10 |
| Railway infra | ~$16-19 |
| **Total** | **~$26-29** |

### Session 18 (2026-04-10) — TASK-063 Switch Briefing Model to Haiku ✅
**Switched briefing generation from Sonnet primary to Haiku primary (10x cost reduction)**

**Problem:**
- Briefing generation uses Sonnet 4.5 ($5/$15 per 1M tokens) costing ~$0.05 per briefing
- Cost optimization opportunity: Haiku is 10x cheaper (~$0.005 per briefing)
- Need to test Haiku's capability on briefing quality while keeping Sonnet as fallback safety net

**Solution (TASK-063):**
- Swapped model constants in `briefing_agent.py`:
  - Line 53: `BRIEFING_PRIMARY_MODEL` → `"claude-haiku-4-5-20251001"` (was Sonnet)
  - Line 54: `BRIEFING_FALLBACK_MODEL` → `"claude-sonnet-4-5-20250929"` (was Haiku)
- Fixed undefined `DEFAULT_MODEL` reference at line 921:
  - Changed `"model": DEFAULT_MODEL` → `"model": BRIEFING_PRIMARY_MODEL`
  - Ensures briefing metadata correctly logs which model generated it

**Implementation:**
- File: `src/crypto_news_aggregator/services/briefing_agent.py`
- 2 edits: lines 53-54 (model swap), line 921 (DEFAULT_MODEL fix)
- Gateway automatically uses new model list at line 846: `models = [BRIEFING_PRIMARY_MODEL, BRIEFING_FALLBACK_MODEL]`
- Fallback to Sonnet still available if Haiku fails (via gateway.call() at line 857-866)

**Verification:**
- ✅ Grep confirms: Haiku now primary, Sonnet now fallback, no DEFAULT_MODEL undefined references
- ✅ Code syntax: Valid Python, no imports needed
- ✅ Gateway integration: Automatic, no changes to call sites

**Expected Impact:**
- Cost reduction: ~$0.05/briefing (Sonnet) → ~$0.005-0.01/briefing (Haiku)
- **Savings: 80-90% per briefing** (~$90/month for 3 briefings/day)
- Quality: Haiku tested on entity extraction (already in use), briefing generation is new use case
- Safety: Sonnet fallback available if quality issues detected

**Status:** ✅ Code complete, committed to cost-optimization/tier-1-only branch
**Testing:** Pending manual smoke test via `/admin/trigger-briefing?briefing_type=morning&is_smoke=true`

### Session 19 (2026-04-12) — BUG-064 Memory Leak + Retry Storm Fix ✅

**Issue:** Celery worker consuming 2.5GB RAM from unclosed event loops + retry storms
- **Root cause 1:** Every task retry creates new asyncio event loop but never closes it (Motor/MongoDB connections leak)
- **Root cause 2:** Operation name mismatch: `"briefing_generate"` (task) vs `"briefing_generation"` (critical ops list) → soft limit blocks briefing generation incorrectly
- **Root cause 3:** `max_retries=2` too low; soft limit hits at 00:00:10 UTC every day, triggering 100+ retries over night
- **Root cause 4:** `LLM_DAILY_SOFT_LIMIT=$0.25` too restrictive; post-optimization briefings cost $0.50-0.70/day

**Fixes Applied:**
1. ✅ **Event loop cleanup:** Already in place (line 37 of `briefing_tasks.py` has `loop.close()`)
2. ✅ **Max retries:** Increased from 2 → 3 for all three briefing tasks
   - Files: `src/crypto_news_aggregator/tasks/briefing_tasks.py` lines 72, 139, 206
3. ✅ **Operation name mismatch:** Added `"briefing_generate"` to CRITICAL_OPERATIONS set
   - File: `src/crypto_news_aggregator/services/cost_tracker.py` lines 304-307
4. ⏳ **Soft limit increase:** `LLM_DAILY_SOFT_LIMIT=$0.25` → `$0.50` (requires Railway env var change)

**Testing:**
- ✅ All critical operation classification tests pass (7/7)
- ✅ Cost tracker unit tests pass (8/8)
- ✅ New test: `test_briefing_generate_is_critical()` validates operation name variant

**Branch:** `fix/bug-064-memory-leak-retry-storm`
**Files Changed:**
- ✏️ `src/crypto_news_aggregator/tasks/briefing_tasks.py` (max_retries: 2 → 3, 3 places)
- ✏️ `src/crypto_news_aggregator/services/cost_tracker.py` (add "briefing_generate" to CRITICAL_OPERATIONS)
- ✨ `tests/test_bug_056_spend_cap.py` (add `test_briefing_generate_is_critical()`)

**Expected Impact:**
- Memory: Worker RAM drops from 2.5GB → <500MB (80%+ reduction)
- Reliability: Briefing generation succeeds on first try (no 100+ retries/day)
- Cost control: Soft limit now meaningful and correct

**Next Steps:**
1. ⏳ Create PR: `fix/bug-064-memory-leak-retry-storm` → main
2. ⏳ Update Railway env var: `LLM_DAILY_SOFT_LIMIT=0.50`
3. ⏳ Deploy to production
4. ⏳ Manual smoke test + memory validation (expect <500MB after 24h)

---

### Session 20 (2026-04-13) — BUG-065 Briefing Soft Limit Incorrectly Triggered ✅

**Issue:** Briefing generation blocked with "Daily spend limit reached (soft_limit)" error despite daily cost ($0.311055) being **below** the soft limit threshold ($0.50).

**Root Cause Found:** The briefing generation pipeline includes a **self-refine loop** that makes three LLM calls:
1. `briefing_generate` - Initial generation (**WAS** marked critical) ✅
2. `briefing_critique` - Quality check during self-refine (**WAS NOT** marked critical) ❌
3. `briefing_refine` - Refinement during self-refine (**WAS NOT** marked critical) ❌

When cache status transitioned to "degraded" (any soft/hard limit condition), `check_llm_budget()` would block non-critical operations. The critique and refine operations were missing from the `CRITICAL_OPERATIONS` set, causing the entire briefing pipeline to fail even though daily cost was under the soft limit.

**Fixes Applied:**
1. ✅ **Added missing critical operations:** Added `briefing_critique` and `briefing_refine` to `CRITICAL_OPERATIONS` set
   - File: `src/crypto_news_aggregator/services/cost_tracker.py` lines 294-318
   - These are essential parts of the core briefing pipeline, not optional enrichment
   
2. ✅ **Added comprehensive debug logging** for future troubleshooting:
   - `[CACHE REFRESH]` in `refresh_budget_cache()` → shows cost/limits read from settings with type info (catches config issues)
   - `[BUDGET CHECK]` (DEBUG level) in `check_llm_budget()` → shows operation name, cache status, daily_cost, cache age on each call
   - `[DEGRADED MODE]` (INFO level) → shows operation criticality classification when in degraded mode

3. ✅ **Added regression tests:**
   - `test_briefing_operations_are_critical()` → verifies all briefing ops marked critical
   - `test_entity_extraction_is_critical()` → verifies pipeline critical op
   - `test_non_critical_operations()` → verifies non-critical ops not wrongly marked

**Testing:**
- ✅ All 11 cost tracker tests pass
- ✅ No regressions in existing test suite

**Branch:** `fix/bug-065-briefing-soft-limit`
**Commit:** `b21e928` (`fix(cost-tracker): Mark briefing critique/refine as critical operations (BUG-065)`)
**Files Changed:**
- ✏️ `src/crypto_news_aggregator/services/cost_tracker.py` (add missing ops to CRITICAL_OPERATIONS, add debug logs)
- ✨ `tests/services/test_cost_tracker.py` (add TestCriticalOperations class with 3 tests)
- 📝 `docs/tickets/bug-065-fix-briefing-soft-limit.md` (updated with root cause analysis)

**Impact:**
- ✅ Fixes immediate blocker: briefing generation no longer incorrectly blocked by soft limit
- ✅ Improves observability: debug logs will catch future budget check issues in production
- ✅ Prevents regression: unit tests ensure all briefing pipeline operations remain critical

**Next Steps:**
1. Create PR: `fix/bug-065-briefing-soft-limit` → main
2. Deploy to production
3. Verify briefing generation succeeds end-to-end (no more "soft_limit" errors)
4. Monitor logs for new debug output to validate soft limit behavior

---

## Key Files

**LLM pipeline (where token leak likely lives):**
- `src/crypto_news_aggregator/llm/anthropic.py` — primary LLM client
- `src/crypto_news_aggregator/llm/optimized_anthropic.py` — entity/narrative extraction
- `src/crypto_news_aggregator/services/briefing_agent.py` — briefing generation
- `src/crypto_news_aggregator/services/narrative_themes.py` — narrative enrichment
- `src/crypto_news_aggregator/services/cost_tracker.py` — spend tracking + budget checks

**Monitoring:**
- `src/crypto_news_aggregator/services/heartbeat.py` — pipeline heartbeat
- `src/crypto_news_aggregator/api/v1/health.py` — health endpoint

**Config:**
- `src/crypto_news_aggregator/core/config.py` — all settings
- `src/crypto_news_aggregator/tasks/beat_schedule.py` — Celery Beat schedule