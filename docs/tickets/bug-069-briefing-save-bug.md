---
id: BUG-069
type: bug
status: fixed
priority: critical
severity: critical
created: 2026-04-13
updated: 2026-04-13
---

# Briefing Generation Logs "Saved" But Never Persists to Database

## Problem
Briefing generation completes successfully and logs "Saved briefing {id}" but the briefing document is never actually written to the `daily_briefings` collection. This causes generated briefings to be invisible on the UI despite successful LLM generation and cost being incurred.

## Expected Behavior
When `_save_briefing()` is called with a `briefing_id`, the briefing document should be:
1. Inserted into the `daily_briefings` collection
2. Returned with `published: true` (unless is_smoke=true)
3. Visible on the UI at `/api/v1/briefing` endpoint

## Actual Behavior
- Briefing generation logs "Saved briefing {id}" at line 937
- Database query shows the briefing does NOT exist in `daily_briefings`
- Briefing IS saved to `briefing_drafts` (intermediate storage)
- Cost is charged (~$0.01-0.05 per briefing) but user sees no output
- Curl request returns 200 OK but no briefing appears on UI

## Steps to Reproduce
1. Call `POST /api/v1/briefing/generate` with force=true
2. Check logs: See "Saved briefing {briefing_id}" message
3. Query MongoDB: `db.daily_briefings.findOne({ _id: ObjectId("{briefing_id}") })`
4. Result: `null` (briefing does not exist)
5. Check UI: No new briefing visible

**Example from 2026-04-13 at 18:23:**
- Log: `Saved briefing 69dd3479347a1df195e1423f (iterations: 1)`
- Query result: Not found in any collection

---

## Root Cause
**Logic error in `briefing_agent.py` lines 929-935** in the `_save_briefing()` method:

```python
if briefing_id:
    briefing_doc_id = briefing_id  # ← WRONG: Just uses the ID
else:
    briefing_doc_id = await insert_briefing(briefing_doc)  # ← RIGHT: Actually saves to DB

briefing_doc["_id"] = ObjectId(briefing_doc_id)
logger.info(f"Saved briefing {briefing_doc_id} ...")  # ← Logs success anyway
```

**Why it breaks:**
- Line 145 generates `briefing_id = str(ObjectId())`
- Line 165 calls `_save_briefing(..., briefing_id=briefing_id)`
- Inside `_save_briefing`, the `if briefing_id:` condition is **True**
- Code skips the `await insert_briefing(briefing_doc)` call
- Document never gets inserted into `daily_briefings`
- But logs "Saved briefing" anyway → **false success**

The code assumes that when `briefing_id` is provided, the save already happened elsewhere. **This assumption is wrong.** The save MUST happen in `_save_briefing()`.

---

## Changes Made

### File: `src/crypto_news_aggregator/services/briefing_agent.py`

**Before (lines 929-938):**
```python
        # Use provided briefing_id if available, otherwise generate new
        if briefing_id:
            briefing_doc_id = briefing_id
        else:
            briefing_doc_id = await insert_briefing(briefing_doc)

        briefing_doc["_id"] = ObjectId(briefing_doc_id)

        logger.info(f"Saved briefing {briefing_doc_id} (iterations: {iteration_count})")
        return briefing_doc
```

**After (lines 929-941):**
```python
        # Set the briefing ID in the document (for consistency with drafts)
        if briefing_id:
            briefing_doc["_id"] = ObjectId(briefing_id)

        # Always save to database (insert_briefing will use the _id if provided)
        briefing_doc_id = await insert_briefing(briefing_doc)

        # Ensure _id is set as ObjectId for return value
        if "_id" not in briefing_doc or isinstance(briefing_doc["_id"], str):
            briefing_doc["_id"] = ObjectId(briefing_doc_id)

        logger.info(f"Saved briefing {briefing_doc_id} (iterations: {iteration_count})")
        return briefing_doc
```

**Key changes:**
1. **Always** call `await insert_briefing(briefing_doc)` regardless of whether `briefing_id` is provided
2. Set `_id` in the document BEFORE inserting so MongoDB respects the provided ID
3. Ensures briefing is persisted to `daily_briefings` collection
4. Briefing will have `published: true` (unless is_smoke=true) and be visible on UI

**Status:** ✅ FIXED - Code change applied 2026-04-13 in Session 23

---

## Testing

### Verification Checklist
- [ ] Deploy fixed `briefing_agent.py` to production
- [ ] Run `curl -X POST http://localhost:8000/api/v1/briefing/generate?force=true`
- [ ] Check logs for "Saved briefing {id}" message
- [ ] Verify briefing appears in database:
  ```javascript
  db.daily_briefings.findOne({}, { sort: { _id: -1 } })
  ```
- [ ] Confirm briefing is visible on UI at `/briefing` endpoint
- [ ] Verify `published: true` (not a smoke test)
- [ ] Run 72-hour burn-in test (TASK-028) to ensure no regressions
- [ ] Monitor daily LLM costs to ensure they match expected spend

### Test Case
```bash
# Generate a briefing
curl -X POST http://localhost:8000/api/v1/briefing/generate?force=true

# Check it was saved
curl http://localhost:8000/api/v1/briefing

# Verify in database
mongosh $MONGO_URL
> db.daily_briefings.find({}, {sort: {_id: -1}}).limit(1)
```

Expected result: Briefing appears in database with full content and `published: true`

---

## Files Changed
- `src/crypto_news_aggregator/services/briefing_agent.py` (9 lines changed)

## Impact
- **Severity:** Critical — Briefings were not being persisted despite LLM calls completing
- **User Impact:** Users saw no briefings on UI despite costs being incurred
- **Cost Impact:** No wasted LLM calls, but lost output value
- **Regression Risk:** Low — only changes the broken logic path

---

## Follow-up Items
- [ ] TASK-070: Investigate and optimize narrative_generate costs (56% of daily budget)
- [ ] TASK-029: Add monitoring/alerting for "Saved briefing" logs that don't correspond to database entries
- [ ] Add database consistency check to briefing generation workflow