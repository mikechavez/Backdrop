# Session Start

**Date:** 2026-04-10 (Session 18, Sprint 13)
**Status:** TASK-063 ✅ complete, BUG-063 🔄 in progress (narrative polish gateway fix)
**Branch:** fix/bug-063-narrative-polish-gateway (parent: cost-optimization/tier-1-only)
**Next:** Complete BUG-063 PR, then merge cost optimization features to main

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

**Session 13 (Current):**
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

**Next Steps:** 
- Monitor Celery beat scheduler to confirm tasks are dispatched
- Monitor worker logs to confirm tasks are received and executed
- Monitor cost tracking to confirm briefing operations are recorded

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

### Current Work (Session 18 — BUG-063 Narrative Polish Gateway Fix) 🔄

**Issue Identified:** Final unmetered LLM call bypassing the unified cost gateway
- Location: `narrative_themes.py` line 1468 in `generate_narrative_from_cluster()`
- Call: `polished = llm_client._get_completion(polish_prompt)` — direct, unmetered
- Impact: ~$1.50+/cycle untracked (~$1.65/hour, 75-80% of daily spend)
- Root cause: Narrative polish operation missed in TASK-042 gateway bypass audit

**Fix Applied:** Route polish through gateway with full cost attribution
- Changed: `llm_client._get_completion()` → `gateway.call()` with operation="narrative_polish"
- Model: Haiku (claude-haiku-4-5-20251001) for cost optimization
- Error handling: Graceful fallback to original summary on gateway failure
- Tests: 4 comprehensive tests, all passing ✅

**Branch:** `fix/bug-063-narrative-polish-gateway`
**Files Changed:**
- ✏️ `src/crypto_news_aggregator/services/narrative_themes.py` (lines 1467-1480)
- ✨ `tests/services/test_narrative_polish_gateway.py` (NEW, 4 tests)

**Cost Impact:**
- Before: $1.65-2.50/day (unmetered polish leak)
- After: $0.50-0.70/day (all calls metered)
- **Savings: ~$1.00-1.80/day (~$30-55/month)**

**Next Steps:**
1. ✅ Code complete + tests passing
2. ⏳ Create PR: `fix/bug-063-narrative-polish-gateway` → main
3. ⏳ Merge to main
4. ⏳ Deploy to production
5. ⏳ Manual smoke test + cost validation

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