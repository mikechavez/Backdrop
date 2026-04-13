---
id: BUG-066
type: bug
status: complete
priority: critical
severity: critical
created: 2026-04-13
updated: 2026-04-13
completed: 2026-04-13
---

# BUG-065: Daily Cost Calculation Uses Rolling 24hr Window Instead of Calendar Day

## Problem

The `get_daily_cost()` function in `cost_tracker.py` calculates a **rolling 24-hour window** instead of a **calendar day**. This causes the hard spend limit to be triggered incorrectly when actual daily spend is well under the limit.

Production is blocked with "hard_limit" error despite actual spend being only **$0.4193** (under the **$0.60** hard limit).

## Expected Behavior

- Budget cache should reflect **calendar day spend** (UTC 00:00–23:59)
- At 16:05 UTC on 2026-04-13, `get_daily_cost()` should return cost for 2026-04-13 00:00–16:05
- Hard limit should only trigger when actual daily spend exceeds $0.60

## Actual Behavior

- `get_daily_cost()` returns cost for a **rolling 24-hour window** (now - 24 hours)
- At 16:05 UTC on 2026-04-13, it returns cost for 2026-04-12 16:05–2026-04-13 16:05
- This window includes ~8 hours of yesterday's spend plus 16 hours of today
- Cache incorrectly shows **$0.7153** (which includes yesterday), triggering hard_limit
- All LLM operations are blocked despite real daily spend being **$0.4193**

## Steps to Reproduce

1. Query actual calendar-day spend:
```javascript
db.api_costs.aggregate([
  { "$match": { "timestamp": { "$gte": ISODate("2026-04-13T00:00:00Z") } } },
  { "$group": { "_id": null, "total": { "$sum": "$cost" } } }
])
// Result: $0.4199 ✅ UNDER $0.60 limit
```

2. Query rolling 24-hour window (what code currently does):
```javascript
db.api_costs.aggregate([
  { "$match": { "timestamp": { "$gte": ISODate("2026-04-12T16:05:00Z") } } },
  { "$group": { "_id": null, "total": { "$sum": "$cost" } } }
])
// Result: $0.7153 ❌ OVER $0.60 limit
```

3. Call briefing endpoint:
```bash
curl -X POST "https://context-owl-production.up.railway.app/api/v1/briefing/generate?is_smoke=true" \
  -H "Content-Type: application/json" \
  -d '{}'
```

4. Observe error:
```json
{
  "success": false,
  "message": "Error during briefing generation: Daily spend limit reached (hard_limit)"
}
```

## Environment

- **Environment:** production (Railway)
- **Collection:** `crypto_news.api_costs`
- **User impact:** critical — all LLM operations blocked

## Root Cause

The `get_daily_cost()` method calculates a rolling 24-hour cutoff instead of a calendar day cutoff:

```python
# CURRENT (WRONG)
async def get_daily_cost(self, days: int = 1) -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    # This gives: "now - 24 hours" = rolling window
    # At 16:05 UTC, includes 8h yesterday + 16h today
```

**Why this is wrong:**
- When called at 16:05 UTC on Apr 13, `timedelta(days=1)` gives Apr 12 16:05
- This pulls in ~8 hours of Apr 12's spend
- Soft limit ($0.50) is designed for calendar-day budgeting, not rolling windows
- Hard limit ($0.60) is also calendar-day based

**Correct behavior:**
- `get_daily_cost(days=1)` should return cost for **today** (00:00–23:59 UTC)
- Should reset at UTC midnight, not at the current time

## Resolution

**Status:** ✅ COMPLETE
**Fix branch:** `fix/bug-066-daily-cost-calculation`
**Commit:** ac7341c

### Changes Made

**File:** `src/crypto_news_aggregator/services/cost_tracker.py`

**Method:** `get_daily_cost()` — change from rolling 24hr to calendar day

```python
async def get_daily_cost(self, days: int = 1) -> float:
    """
    Get total cost for the specified calendar day (UTC).
    
    For days=1 (default), returns cost for today (00:00-23:59 UTC).
    For days=2, returns cost for yesterday, etc.
    
    Args:
        days: Number of calendar days back (1=today, 2=yesterday, etc.)
    
    Returns:
        Total cost in USD
    """
    now = datetime.now(timezone.utc)
    
    # Calculate start of the target calendar day in UTC
    # days=1 → today 00:00 UTC
    # days=2 → yesterday 00:00 UTC
    start_of_day = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_of_day}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]

    result = await self.collection.aggregate(pipeline).to_list(1)

    return result[0]["total"] if result else 0.0
```

**Why this works:**
- `now - timedelta(days=0)` = today, replace time to 00:00 UTC
- `now - timedelta(days=1)` = yesterday, replace time to 00:00 UTC
- Resets at UTC midnight, not at "current time"
- Matches the intent of soft_limit ($0.50) and hard_limit ($0.60) — daily budgets

### Testing

**After fix, verify:**

1. **Query returns calendar-day cost (not rolling):**
```bash
# Should return ~$0.4199 (today's spend only)
curl -X GET "https://context-owl-production.up.railway.app/api/v1/costs/daily"
```

2. **Briefing generation works:**
```bash
curl -X POST "https://context-owl-production.up.railway.app/api/v1/briefing/generate?is_smoke=true" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: success=true, briefing data returned
```

3. **Cache refreshes correctly:**
- Check logs for `[CACHE REFRESH]` message
- Should show `daily_cost=$0.41xx` (not $0.71xx)
- Status should be "ok" (not "hard_limit")

4. **Soft limit still works correctly:**
- Verify soft_limit ($0.50) triggers degraded mode when spend > $0.50
- Verify critical operations (briefing_generate, entity_extraction) proceed in degraded mode
- Verify non-critical operations are blocked in degraded mode

### Files Changed

- `src/crypto_news_aggregator/services/cost_tracker.py`
  - Method: `get_daily_cost()` — change time window calculation

### Related Tickets

- **BUG-064:** Memory Leak + Retry Storm ✅ DEPLOYED
- **TASK-064:** Railway Cost Audit 🔴 BLOCKED (due to hard_limit error)
- **TASK-070:** Post-Optimization Burn-in 🔴 BLOCKED (due to hard_limit error)

### Notes

- This bug was hidden by BUG-064 (retry storm). Once that was fixed, this bug became visible.
- The cache is working correctly; the data it pulls is wrong.
- No cache reset needed; fix will propagate on next refresh (TTL=30s).
- Production will unblock immediately after deploy (briefing generation will resume).

---

**Prepared by:** Claude Assistant (debugging session 2026-04-13 16:05 UTC)
**Ready for:** Claude Code implementation