---
id: BUG-069
type: bug
status: ✅ FIXED & VERIFIED
priority: critical
severity: critical
created: 2026-04-13
updated: 2026-04-13
fixed_date: 2026-04-13
verification_date: 2026-04-13
---

# Briefing Document Persistence Bug

## Summary
Briefing generation was completing successfully (cost charged, LLM called) but documents were not being saved to the database. **Root cause:** conditional logic error in `_save_briefing()` that skipped the database insert operation when a `briefing_id` was provided.

**Status:** ✅ **FIXED & VERIFIED** — Code change applied 2026-04-13. Manual briefing generation tested successfully; document saves with full content to `briefing_drafts` collection.

---

## Root Cause

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`, lines 929-935

```python
# BROKEN LOGIC:
if briefing_id:
    briefing_doc_id = briefing_id  # ← Just assigns ID, doesn't insert
else:
    briefing_doc_id = await insert_briefing(briefing_doc)  # ← Only path that saves

# Result: logs "Saved briefing" even though insert was skipped
logger.info(f"Saved briefing {briefing_doc_id} ...")
```

**Why it broke:**
1. `generate_briefing()` generates `briefing_id = str(ObjectId())`
2. Calls `_save_briefing(..., briefing_id=briefing_id)`
3. Inside `_save_briefing()`, the `if briefing_id:` condition is **True**
4. Code path skips `await insert_briefing(briefing_doc)` entirely
5. Document never inserted, but function logs success anyway

**False assumption:** Code assumed that when `briefing_id` is provided, the document was already saved elsewhere. **This was wrong.** The save MUST happen inside `_save_briefing()`.

---

## Fix Applied

**Before:**
```python
if briefing_id:
    briefing_doc_id = briefing_id
else:
    briefing_doc_id = await insert_briefing(briefing_doc)

briefing_doc["_id"] = ObjectId(briefing_doc_id)
logger.info(f"Saved briefing {briefing_doc_id} (iterations: {iteration_count})")
return briefing_doc
```

**After:**
```python
# Set the briefing ID in the document BEFORE insert
if briefing_id:
    briefing_doc["_id"] = ObjectId(briefing_id)

# Always save to database (insert_briefing will use provided _id if present)
briefing_doc_id = await insert_briefing(briefing_doc)

# Ensure _id is set as ObjectId for return value
if "_id" not in briefing_doc or isinstance(briefing_doc["_id"], str):
    briefing_doc["_id"] = ObjectId(briefing_doc_id)

logger.info(f"Saved briefing {briefing_doc_id} (iterations: {iteration_count})")
return briefing_doc
```

**Key change:** Unconditionally call `await insert_briefing()` instead of skipping it when `briefing_id` is provided. MongoDB will respect the `_id` field in the document.

---

## Verification

### Manual Test (2026-04-13 12:55 CST)
✅ **Passed**

- Generated briefing via API: `POST /api/v1/briefing/generate?force=true`
- Document saved to `briefing_drafts` with ID `69dd3c569a306ff4c8f843aa`
- Full content present:
  - `narrative`: 2800+ chars ✓
  - `key_insights`: 5 items ✓
  - `entities_mentioned`: 10 entities ✓
  - `recommendations`: 3 sections ✓
  - `confidence_score`: 0.92 ✓
- Cost logged: $0.010033 ✓
- Visible on UI: ✅ Yes

### Next Verification: Scheduled Briefing
**Target:** 8:00 PM EST today (2026-04-13 20:00 EST) — watch for automatic execution

- [ ] Celery Beat schedules the task
- [ ] Task executes and logs completion
- [ ] Document appears in `briefing_drafts` at ~20:00 EST timestamp
- [ ] Document has full content (not empty)
- [ ] Cost logged to `llm_traces`

See `current-sprint.md` TASK-028 for post-deployment validation plan.

---

## Files Changed
- `src/crypto_news_aggregator/services/briefing_agent.py` (8 lines modified)

## Impact
- **Critical bug:** Generation succeeded but persistence failed silently
- **User impact:** No briefings visible on UI despite costs incurred
- **Scope:** Affects manual AND scheduled briefing generation
- **Risk of regression:** Low — only changes the previously-broken conditional path

---

## Related Issues
- **Scheduled briefing validation:** See Sprint 14 TASK-028 (72-hour burn-in test)
- **Cost accuracy:** LLM cost tracking (BUG-068) validated in same test
- **Future improvement:** Add database consistency check to catch similar persistence bugs