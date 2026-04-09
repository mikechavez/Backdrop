# Session Start

**Date:** 2026-04-08 (Session 6, Sprint 13)
**Status:** Sprint 13 — TASK-036 through TASK-040 complete & merged, TASK-041 burn-in active
**Branch:** feat/task-041-burn-in-setup (burn-in monitoring setup)

---

## What Happened Last

Sessions 1–5: Built LLM Gateway infrastructure (TASK-036 through TASK-040). All code merged to main and deployed to Railway.

**Completed & Merged:**
- ✅ TASK-036: LLM Gateway with async/sync modes, budget enforcement (commit 72a15f4)
- ✅ TASK-037: Tracing schema, indexes (TTL 30d), aggregation query helper (commit b6a60bd)
- ✅ TASK-038: Wire briefing_agent through gateway, 3 operation tags (commit c2976c0)
- ✅ TASK-039: Wire health endpoint through gateway, graceful spend cap handling (commit 67aff33)
- ✅ TASK-040: Dataset capture for eval datasets, pre/post refine drafts (commit 7208fa7)

**Deployed to Railway:**
- All Sprint 13 code live in production
- $6 Anthropic credits added
- llm_traces, briefing_drafts collections ready

**Current (Session 6):**
- TASK-041: 48-hour burn-in + findings doc (in progress, monitoring setup complete)

---

## Sprint 13 Goal

Unify all LLM calls behind a single gateway, achieve full cost attribution, and identify the primary cost driver with measured data.

---

## What's Next

1. **TASK-041 (48-hour burn-in):** System is actively collecting `llm_traces` data. No manual work needed until 2026-04-10 20:00 UTC.
2. **Post-burn-in:** Run `poetry run python scripts/analyze_burn_in.py` to generate cost summary
3. **Write findings doc:** `docs/sprint-13-burn-in-findings.md` with cost by operation, cost by model, refine loop stats, and Sprint 14 decision
4. **Sprint 14 planning:** Data-driven optimization decisions based on burn-in findings

---

## Known Issues / Blockers

**Active:**
- 🔴 Token leak: $5 credits burn in 1-2 days, spend cap not catching it. NeMo tracing is the fix.
- 🟡 Anthropic API balance near $0 — add credits after merge/deploy
- 🟡 TASK-035 Slack webhook not configured

**Resolved (Sprint 12):**
- ✅ BUG-054: Pipeline live
- ✅ BUG-055: Smoke briefings stopped, MongoDB pruned
- ✅ BUG-056: Spend cap code deployed
- ✅ BUG-057: Retry storm fixed
- ✅ BUG-058: Briefing generation fixed
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