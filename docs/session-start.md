# Session Start

**Date:** 2026-04-09 (Session 10, Sprint 13)
**Status:** BUG-060 fixed, soft limit $3.00 insufficient — enrichment consuming budget
**Branch:** fix/bug-058-soft-limit-and-type-error (merged)
**Blocker:** Soft limit still hit by background enrichment; briefing generation blocked by narrative_generate non-critical flag

---

## What Happened Last

Sessions 1–5: Built complete LLM control layer (TASK-036 through TASK-041) + hard limit lift (TASK-044).

**Completed & Merged:**
- ✅ TASK-036: LLM Gateway with async/sync modes, budget enforcement, fire-and-forget trace writes (commit 72a15f4)
- ✅ TASK-037: Tracing schema, indexes (TTL 30d), aggregation query helper (commit b6a60bd)
- ✅ TASK-038: Wired briefing_agent.py through gateway with operation tags (commit c2976c0)
- ✅ TASK-039: Wired health.py through gateway (commit 67aff33)
- ✅ TASK-040: Dataset capture for pre/post refine drafts (commit 7208fa7)
- ✅ TASK-041: 48-hour burn-in + findings doc (merged)
- ✅ TASK-044: Lift hard spend limit to $15 for burn-in (merged, commit 7eb5129)
- ✅ TASK-042: Gateway bypass fix — all LLM calls wired through gateway (merged)
- ✅ TASK-041A: Restart burn-in with clean baseline (merged)

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
- ❌ **NEW BLOCKER FOUND:** Enrichment consuming budget, blocking briefing
  - **Symptom:** Briefing generation fails with "Daily spend limit reached (soft_limit)"
  - **Root cause:** Background enrichment pipeline runs continuously, consuming budget before briefing
  - **Issue:** `narrative_generate` classified as non-critical, gets blocked at soft limit
  - **But:** Briefing also needs narrative_generate, so soft limit blocks entire briefing
  - **Options for next session:**
    1. Raise soft limit to $5-10 to allow both enrichment + briefing
    2. Add narrative_generate to CRITICAL_OPERATIONS when called from briefing
    3. Disable/throttle enrichment during burn-in

**Previous (Session 9):**
- ✅ BUG-058: Raised soft limit to $1.00, fixed TypeError in narrative detection (commit 641e120)

**Next Session:** Decide on enrichment budget strategy and implement fix

---

## Sprint 13 Goal

Unify all LLM calls behind a single gateway, achieve full cost attribution, and identify the primary cost driver with measured data.

---

## What's Next

**Session 11 (Next):**
1. Decide enrichment budget strategy (raise soft limit vs critical ops vs throttle)
2. Implement fix to unblock briefing generation
3. Verify briefing generates successfully
4. Monitor burn-in to completion (2026-04-10 ~02:48 UTC)

**After burn-in completes (2026-04-10 ~20:00 UTC):**
1. Run `poetry run python scripts/analyze_burn_in.py` to generate cost summary
2. Write TASK-041B findings doc: `docs/sprint-13-burn-in-findings.md`
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