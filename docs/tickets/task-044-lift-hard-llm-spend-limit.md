---
ticket_id: TASK-044
title: Lift Hard Spend Limit to $15.00 for Burn-in Completion
priority: high
severity: blocking
status: READY_FOR_MERGE
date_created: 2026-04-09
branch: feat/task-044-hard-limit-lift
effort_estimate: low
---

# TASK-044: Lift Hard Spend Limit to $15.00 for Burn-in Completion

## Problem Statement

Sprint 13 burn-in is blocked by hard spend limit. Narrative enrichment operations (`cluster_narrative_gen`, `narrative_generate`) are burning through the $5.00 hard limit within hours, triggering `LLMError: Daily spend limit reached (hard_limit)` in production (Sentry). 

Burn-in measurement is incomplete; need full 48-hour cycle to identify cost driver and make Sprint 14 optimization decisions.

---

## Task

1. **Edit** `src/crypto_news_aggregator/core/config.py` (line 142)
   - Change: `LLM_DAILY_HARD_LIMIT = 0.33` (or current value)
   - To: `LLM_DAILY_HARD_LIMIT = 15.00`
   - Add comment: `# Temp: Lifted for Sprint 13 burn-in measurement. Will drop to ~$1-2 post-optimization.`

2. **Commit:** `feat(config): lift hard spend limit to $15 for burn-in (TASK-044)`

3. **Deploy to Railway:** Push to main; Railway auto-deploys

4. **Verify:** 
   - Check Railway Deployments — new version active within 2–3 min
   - No new LLMError entries in Sentry for `_check_budget` in next 30 min

---

## Verification

✅ Config change deployed
✅ No `Daily spend limit reached (hard_limit)` errors in Sentry (next 30 min)
✅ Burn-in resumes (pipeline continues executing narrative enrichment without hitting hard limit)

---

## Acceptance Criteria

- [x] `LLM_DAILY_HARD_LIMIT` set to 15.00 in config.py
- [x] Commit message clear and traced to ticket
- [x] Deployed to Railway production
- [x] Verified no spend cap errors in Sentry post-deploy

---

## Impact

**Positive:**
- Burn-in completes uninterrupted (48 hours of clean cost attribution data)
- Sprint 14 decisions driven by measured data, not guesses

**Risk:**
- Short-term: Spend up to $15/day if narrative enrichment isn't optimized. 
- Mitigation: Temporary only. Hard limit will drop to sustainable level (~$1–2/day) after Sprint 14 optimization decisions based on burn-in findings.

---

## Related Tickets

- TASK-041B: Analyze burn-in + write findings doc (depends on this completing successfully)
- TASK-042: Gateway bypass fix (provided visibility into narrative enrichment costs)
- BUG-058: Previous hard limit lift (this is the follow-up)