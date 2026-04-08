# Session Start

**Date:** 2026-04-08 (Session 2, Sprint 13)
**Status:** Sprint 13 in progress — TASK-036 complete, moving to TASK-037
**Branch:** feat/task-036-llm-gateway (ready for merge) → moving to feat/task-037-llm-traces-collection

---

## What Happened Last

Sprint 12 closed. Phase 1 (stability) is complete: pipeline is live, cost controls deployed (BUG-056/057/058/059 all merged), Sentry + heartbeat monitoring active. However, LLM spend still exceeds the $0.33/day target — $5 in credits burns through in 1-2 days despite spend cap code. Root cause: untraced token usage somewhere in the pipeline. Spend cap logic is deployed but can't enforce what it can't see.

**Unmerged branch:** `fix/bug-058-briefing-generation-skips` (BUG-058 + BUG-059) — needs PR, merge, deploy before Sprint 13 work begins.

**Deferred from Sprint 12:**
- TASK-028: 72-hour burn-in — premature until token leaks found
- TASK-035: Slack webhook URL not yet configured in Railway
- Prompt audit: awaiting degraded rate data

---

## Sprint 13 Goal

Integrate NVIDIA NeMo Agent Toolkit to trace, evaluate, debug, and optimize LLM calls. Produce an ADR before implementation. End state: an agent loop that self-diagnoses LLM bugs and alerts via Sentry when human attention is needed.

---

## What's Next

1. **Merge Sprint 12 tail** — PR + deploy `fix/bug-058-briefing-generation-skips`
2. **ADR: NeMo Agent Toolkit Integration** — document why, what, how, and scope
3. **Sprint 13 planning** — break ADR into tickets

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