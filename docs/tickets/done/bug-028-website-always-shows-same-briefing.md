bug-028-website-always-shows-same-briefing

---
id: BUG-028
type: bug
status: resolved
priority: high
severity: high
created: 2026-02-10
updated: 2026-02-10
---

# Website Always Shows the Same Briefing

## Problem

The briefings page on the frontend always displays the same briefing text regardless of how many new briefings have been generated. New briefings are being saved to MongoDB successfully, but the website never reflects them.

## Expected Behavior

`GET /api/v1/briefings` returns the most recently generated briefing, updating each time a new briefing is saved.

## Actual Behavior

`GET /api/v1/briefings` always returns the same document — typically the first briefing ever inserted — regardless of newer documents in the database.

## Steps to Reproduce

1. Trigger a new briefing via `POST /api/v1/briefings/generate`
2. Wait for successful generation (response includes `briefing_id`)
3. Load or refresh the briefings page
4. Observe: page still shows the old briefing text
5. Confirm in MongoDB that a new document exists with a newer `generated_at` timestamp:
   ```bash
   db.daily_briefings.find(
     { published: true, is_smoke: { $ne: true } },
     { type: 1, generated_at: 1 }
   ).sort({ generated_at: -1 }).limit(5)
   ```

## Environment

- Environment: production
- Browser/Client: all (server-side bug)
- User impact: high — users never see fresh briefings

---

## Resolution

**Status:** Fixed
**Fixed:** 2026-02-10
**Branch:** `fix/bug-027-remove-afternoon-scheduled-briefing`
**Commits:** 39ac7ab, 3bd4d8f

### Root Cause

`get_latest_briefing()` in `db/operations/briefing.py` uses Motor's `collection.find_one()` with a `sort` keyword argument. Motor's async `find_one` does **not** reliably honor the `sort` parameter — it is silently ignored in many versions, causing the query to return an arbitrary document (typically the natural order first document, i.e. the oldest insert) rather than the newest.

This is a known Motor footgun: `find_one(filter, sort=[...])` behaves inconsistently. The correct pattern for sorted single-document retrieval in Motor is `find(filter).sort(...).limit(1)`.

The bug is in `get_latest_briefing()` only. The `get_briefing_by_type_and_date()` function (used by `/morning` and `/evening` endpoints) is unaffected since it uses a date-range filter rather than relying on sort order for correctness.

### Changes Made

**`src/crypto_news_aggregator/db/operations/briefing.py`**  
Replace `find_one` with `find().sort().limit(1)` in `get_latest_briefing()`:

```python
# BEFORE (broken — sort is silently ignored by Motor):
async def get_latest_briefing() -> Optional[Dict[str, Any]]:
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    briefing = await collection.find_one(
        _get_production_briefings_filter(),
        sort=[("generated_at", -1)]
    )

    return briefing


# AFTER (correct — sort is applied via the cursor chain):
async def get_latest_briefing() -> Optional[Dict[str, Any]]:
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    cursor = collection.find(
        _get_production_briefings_filter()
    ).sort("generated_at", -1).limit(1)

    results = await cursor.to_list(length=1)
    return results[0] if results else None
```

No changes required to the API endpoint (`briefing.py`) or the frontend — this is purely a database query fix.

### Testing

1. Confirm multiple briefings exist in MongoDB with different timestamps:
   ```bash
   db.daily_briefings.find(
     { published: true, is_smoke: { $ne: true } },
     { type: 1, generated_at: 1 }
   ).sort({ generated_at: -1 }).limit(5)
   ```

2. Call the API and verify the returned `generated_at` matches the newest document:
   ```bash
   curl http://localhost:8000/api/v1/briefings | jq '.briefing.generated_at'
   ```

3. Generate a new briefing and immediately re-fetch — the new `generated_at` should appear:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/briefings/generate" \
     -H "Content-Type: application/json" \
     -d '{"type": "morning", "force": true}'

   curl http://localhost:8000/api/v1/briefings | jq '.briefing.generated_at'
   # Should match the timestamp from the generate response
   ```

4. Verify the `/history` endpoint is unaffected (it uses `find()` with cursor correctly already).

### Files Changed

- `src/crypto_news_aggregator/db/operations/briefing.py`