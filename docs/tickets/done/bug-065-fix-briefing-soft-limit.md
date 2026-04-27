---
id: BUG-065
type: bug
status: OPEN
priority: CRITICAL
severity: HIGH
created: 2026-04-13
updated: 2026-04-13
---

# BUG-065: Soft Limit Incorrectly Triggered Despite Being Under Threshold

## Problem

Briefing generation is being blocked with "Daily spend limit reached (soft_limit)" error even though:
- **Actual daily cost:** $0.311055 (verified via MongoDB query)
- **Soft limit setting:** $0.50 (verified in Railway environment)
- **Status:** Daily cost is **below** the soft limit, should NOT be blocked

This is preventing briefing generation on 2026-04-13 despite the system being well under budget.

## Expected Behavior

When daily cost ($0.31) < soft limit ($0.50):
- `check_llm_budget("briefing_generate")` should return `(True, "ok")` or `(True, "degraded")` if critical
- Briefing generation should proceed normally
- Operation should succeed

## Actual Behavior

When attempting to generate briefing via `/api/v1/briefing/generate`:
```
Daily spend limit reached (soft_limit)
LLMError
```

Despite:
- MongoDB shows 146 traces from today with total cost $0.311055
- Environment variable `LLM_DAILY_SOFT_LIMIT=0.50` is set
- FastAPI/Celery processes were restarted after env var update

## Steps to Reproduce

1. Verify daily cost is under soft limit:
   ```javascript
   db.llm_traces.aggregate([
     { "$match": { "timestamp": { "$gte": ISODate("2026-04-13T00:00:00Z") } } },
     { "$group": { "_id": null, "total": { "$sum": "$cost" } } }
   ])
   // Result: { total: 0.311055 }
   ```

2. Verify soft limit is set:
   ```bash
   # Railway → FastAPI → Variables
   # LLM_DAILY_SOFT_LIMIT = 0.50
   ```

3. Attempt to generate briefing:
   ```bash
   curl -X POST https://your-api/api/v1/briefing/generate
   ```

4. Observe: "Daily spend limit reached (soft_limit)" error

## Root Cause Analysis

**PRIMARY CAUSE FOUND:** The briefing pipeline includes three LLM calls:
1. `briefing_generate` (generation) - **IS marked as critical**
2. `briefing_critique` (quality check during self-refine) - **WAS NOT marked as critical** ❌
3. `briefing_refine` (refinement during self-refine) - **WAS NOT marked as critical** ❌

When the cache status is "degraded" (soft limit exceeded or any error), non-critical operations are blocked. The critique/refine operations are part of the core briefing pipeline but were missing from `CRITICAL_OPERATIONS` set in `cost_tracker.py:304-309`, causing them to be incorrectly blocked.

**SECONDARY ISSUE:** Debug logging was insufficient to identify the root cause. Added comprehensive logging:
- `[CACHE REFRESH]` in `refresh_budget_cache()` to show cost/limits read from settings
- `[BUDGET CHECK]` in `check_llm_budget()` to show cache state on each call
- `[DEGRADED MODE]` to show operation classification decision

## Environment

- **Environment:** production (Railway)
- **Service:** FastAPI + Celery worker
- **Database:** MongoDB Atlas
- **Date:** 2026-04-13
- **User impact:** HIGH — briefings cannot be generated

## Evidence

### MongoDB Query Results
```javascript
db.llm_traces.countDocuments({
  "timestamp": { "$gte": ISODate("2026-04-13T00:00:00Z") }
})
// Result: 146

db.llm_traces.aggregate([
  { "$match": { "timestamp": { "$gte": ISODate("2026-04-13T00:00:00Z") } } },
  { "$group": { "_id": null, "total": { "$sum": "$cost" } } }
])
// Result: [ { _id: null, total: 0.311055 } ]
```

### Environment Variables (Verified)
- **FastAPI:** `LLM_DAILY_SOFT_LIMIT=0.5` ✅
- **Celery Worker:** `LLM_DAILY_SOFT_LIMIT=0.50` ✅
- **Processes:** Restarted after env update ✅

---

## Debugging Required

Add these debug logs to identify the root cause:

### 1. In `check_llm_budget()` — cost_tracker.py:
```python
logger.info(
    f"[BUDGET CHECK] operation={operation}, status={status}, "
    f"daily_cost=${_budget_cache['daily_cost']:.4f}, age={age:.1f}s"
)
# When degraded:
logger.info(
    f"[DEGRADED MODE] operation={operation}, is_critical={is_critical}"
)
```

### 2. In `refresh_budget_cache()` — cost_tracker.py:
```python
logger.info(
    f"[CACHE REFRESH] daily_cost=${daily_cost:.4f}, "
    f"soft_limit=${soft_limit:.2f}, hard_limit=${hard_limit:.2f}"
)
```

### 3. Run manual briefing and capture:
```bash
# After deploying debug logs:
curl -X POST https://your-api/api/v1/briefing/generate

# Watch logs for:
# - [CACHE REFRESH] — what limits are being read?
# - [BUDGET CHECK] — what is the cached daily_cost and status?
# - [DEGRADED MODE] — is operation critical or not?
```

## Related Tickets

- BUG-064: Memory Leak + Retry Storm (fixed, deployed)
- TASK-064: Railway Cost Audit (blocked by this issue)
- TASK-070: Post-Optimization Burn-in (blocked by this issue)

## Acceptance Criteria

- [x] Root cause identified (critique/refine ops not marked critical)
- [x] Debug logs added for investigation support
- [x] Fix implemented: Added `briefing_critique` and `briefing_refine` to CRITICAL_OPERATIONS
- [x] Unit tests added to verify critical operations list
- [x] All critical operations tests pass
- [ ] Manual briefing succeeds with daily cost under soft limit (in production)
- [ ] Celery scheduled briefing tasks execute normally (in production)

## Files Involved

- `src/crypto_news_aggregator/services/cost_tracker.py` — `check_llm_budget()`, `refresh_budget_cache()`
- `src/crypto_news_aggregator/llm/gateway.py` — calls `check_llm_budget()` before LLM calls
- `src/crypto_news_aggregator/core/config.py` — reads `LLM_DAILY_SOFT_LIMIT`

---

**Status:** OPEN — Awaiting debug logs to identify root cause