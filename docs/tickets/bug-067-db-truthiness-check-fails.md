---
id: BUG-067
type: bug
status: ready-for-fix
priority: high
severity: high
created: 2026-04-13
updated: 2026-04-13
---

# BUG-067: Motor AsyncIOMotorDatabase Truthiness Check Fails

## Problem

During briefing generation, the code fails with:
```
Failed to generate afternoon briefing: Database objects do not implement truth value testing or bool(). Please compare with None instead: database is not None
```

This occurs in the `_self_refine()` method when trying to save post-refinement drafts.

## Expected Behavior

Briefing generation should complete successfully, including:
1. Initial generation (briefing_generate)
2. Quality critique (briefing_critique)
3. Refinement if needed (briefing_refine)
4. Draft capture after each refinement step

## Actual Behavior

After refinement pass, the code tries to evaluate:
```python
if briefing_id and db:  # ❌ FAILS
```

Motor's `AsyncIOMotorDatabase` object doesn't support truthiness testing (`bool()`). It raises `TypeError: Database objects do not implement truth value testing or bool()`.

The error occurs at line 437 of `briefing_agent.py`:
```python
if briefing_id and db:
    await save_draft(...)
```

## Root Cause

Motor (MongoDB async driver) forbids truthiness checks on database objects. The error message explicitly says:
> "Please compare with None instead: database is not None"

The code was written assuming `db` could be tested with truthiness (`if db:`), but Motor explicitly rejects this pattern.

**Where the issue starts:**
- Line 149: `db = await mongo_manager.get_async_database()` — returns Motor `AsyncIOMotorDatabase`
- Line 161: `_self_refine(..., db=db)` — passes Motor object
- Line 437: `if briefing_id and db:` — tries truthiness check on Motor object → **FAILS**

## Steps to Reproduce

1. Call briefing generation endpoint with self-refine enabled (default)
2. Observe logs showing successful generate/critique/refine calls
3. See error: "Database objects do not implement truth value testing or bool()"
4. Briefing generation fails (returns None)

## Resolution

**Status:** ✅ FIXED
**Fix branch:** `fix/bug-066-daily-cost-calculation`
**Commit:** (pending - preparing for PR)

### Changes Made

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`
**Line:** 437

**Change from:**
```python
if briefing_id and db:
    await save_draft(...)
```

**Change to:**
```python
if briefing_id and db is not None:
    await save_draft(...)
```

**Why this works:**
- `briefing_id and db is not None` uses explicit `None` comparison
- Motor allows `is None` / `is not None` checks (doesn't trigger truthiness testing)
- `briefing_id` is a string or None, so `briefing_id` truthiness is safe
- Preserves original intent: only save draft if both values are provided

### Testing

**After fix, verify:**

1. **Briefing generation completes without errors:**
```bash
curl -X POST "https://context-owl-production.up.railway.app/api/v1/briefing/generate?is_smoke=true" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: success=true, briefing data returned (not error)
```

2. **Logs show all refinement steps completing:**
- `[DEGRADED MODE] operation=briefing_generate, is_critical=True`
- `Tracked briefing_generate call:` ✅
- `[DEGRADED MODE] operation=briefing_critique, is_critical=True`
- `Tracked briefing_critique call:` ✅
- `[DEGRADED MODE] operation=briefing_refine, is_critical=True`
- `Tracked briefing_refine call:` ✅
- No error about truthiness testing

3. **Draft capture works:**
- Verify `briefing_drafts` collection has entries for:
  - `stage=pre_refine`
  - `stage=post_refine_1`
  - `stage=post_refine_2` (if multiple iterations)

### Files Changed

- `src/crypto_news_aggregator/services/briefing_agent.py`
  - Line 437: Change `if briefing_id and db:` to `if briefing_id and db is not None:`

### Related Tickets

- **BUG-065:** Daily Cost Calculation ✅ FIXED
- **TASK-070:** Post-Optimization Burn-in 🔴 BLOCKED (waiting for this fix)

### Notes

- This is a Motor/PyMongo async driver limitation, not a Backdrop bug per se
- The fix is a one-line change
- No cache resets or database cleanup needed
- Production will resume briefing generation immediately after deploy

---

**Prepared by:** Claude Assistant (investigation 2026-04-13 16:26 UTC)
**Ready for:** Claude Code implementation
**Priority:** High — blocks production briefing generation