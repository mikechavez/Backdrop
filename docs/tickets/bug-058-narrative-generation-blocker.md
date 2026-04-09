---
id: BUG-058
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-09
updated: 2026-04-09
---

# Narrative Generation Blocked by Soft Spend Limit + Detection Error

## Problem
Soft spend limit ($0.25/day) hit at 03:26:19 UTC during TASK-028 burn-in, blocking all `narrative_generate` LLM calls. Additionally, `narrative_service.py:1206` throws `'list' object has no attribute 'get'` when detecting narratives, preventing graceful error handling. Result: 356 articles ingested and clustered, but no LLM enrichment occurs. Signal computation frozen; briefing generation downstream fails.

## Expected Behavior
- Soft spend limit allows complete narrative generation pipeline during 72-hour burn-in (estimated cost: $0.80–$1.20)
- Narrative detection handles soft-limit errors gracefully without crashing
- Signal computation resumes; briefing generation resumes; burn-in completes

## Actual Behavior
- 03:26:19 UTC: Soft limit hit at $0.2624
- Gateway blocks all `narrative_generate` calls with `Daily spend limit reached (soft_limit)`
- Narrative detection error: `'list' object has no attribute 'get'` in detect_narratives()
- `signal_scores` collection remains empty (last update before 03:26)
- Briefing tasks queue but cannot execute; no signal data available
- Celery beat continues spawning tasks; all fail downstream

## Steps to Reproduce
1. Deploy Backdrop with hard limit $15.00, soft limit $0.25
2. Ingest 356 articles via RSS (completes ✅)
3. Trigger narrative clustering (creates ~120 clusters ✅)
4. Wait for scheduled narrative detection cycle (03:26 UTC)
5. Observe: spend hits $0.2624, `narrative_generate` blocked, detection error thrown, signal computation never runs, briefing generation blocked

## Environment
- Environment: production (Backdrop on Railway)
- Browser/Client: N/A (backend service)
- User impact: critical — entire briefing pipeline dead during validation

## Screenshots/Logs
```
2026-04-09T03:26:19.524437809Z [inf] WARNING - Soft limit active: blocking non-critical operation 'narrative_generate'
2026-04-09T03:26:19.592669404Z [inf] ERROR - Error generating narrative for cluster: Daily spend limit reached (soft_limit)
2026-04-09T03:26:20.400232566Z [inf] ERROR - Error in detect_narratives: 'list' object has no attribute 'get'
2026-04-09T03:26:20.407 - src.crypto_news_aggregator.worker - INFO - No narratives detected in this cycle
```

---

## Resolution

**Status:** Open
**Fixed:** TBD
**Branch:** feature/BUG-058-narrative-blocker
**Commit:** TBD

### Root Cause

**Issue 1: Aggressive Soft Spend Limit**
- `SOFT_SPEND_LIMIT` set to $0.25, intended as validation threshold only
- Actual burn-in cost: ~$0.80–$1.20 for 356 articles + narrative clustering
- Soft limit should be operational circuit breaker, not hard blocker
- Fix: Raise to $1.00 (still 15x below $15 hard limit)

**Issue 2: Type Error in Narrative Detection**
- Location: `src/crypto_news_aggregator/services/narrative_service.py:1206`
- `detect_narratives()` calls `.get()` on result without checking if result is dict
- When narrative generation fails with soft-limit error, returns list or exception; code assumes dict
- Fix: Add `isinstance()` type guard before calling `.get()`

### Changes Made

**File 1: `src/crypto_news_aggregator/core/config.py`**
- Change `SOFT_SPEND_LIMIT = 0.25` to `SOFT_SPEND_LIMIT = 1.00`
- Justification: Soft limits should allow normal burn-in ops; $1.00 still 15x below hard limit

**File 2: `src/crypto_news_aggregator/services/narrative_service.py`**
- Find error handling around line 1206 in `detect_narratives()`
- Add type guard: `if isinstance(result, dict):` before calling `.get()`
- Handle non-dict responses (list, exception) gracefully:
  ```python
  if isinstance(result, dict):
      data = result.get('error')
  elif isinstance(result, list):
      logger.error(f"Narrative generation returned list: {result}")
      data = None
  else:
      logger.error(f"Unexpected result type: {type(result)}")
      data = None
  ```
- Confirm `LLMError` with soft-limit is caught and logged, not propagated

### Testing

- [ ] Config change deployed: `SOFT_SPEND_LIMIT` = 1.00 verified in production
- [ ] Error handler fixed: No `'list' object has no attribute 'get'` on next cycle
- [ ] Narrative detection resumes: Monitor 03:40 UTC cycle (next scheduled)
- [ ] Spend tracking: Verify cost stays within $1.00 soft limit during burn-in
- [ ] Signal flow verified: `signal_scores` collection updates with recent timestamps
- [ ] Briefing generation resumes: Morning/afternoon/evening tasks complete
- [ ] No cascading errors: Check logs for downstream failures

### Files Changed
- `src/crypto_news_aggregator/core/config.py` (soft limit value)
- `src/crypto_news_aggregator/services/narrative_service.py` (error handler type guard)