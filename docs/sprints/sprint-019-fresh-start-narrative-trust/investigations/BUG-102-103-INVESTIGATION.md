# Investigation: Why 3 Narratives Cleared `needs_summary_update` Without Setting `last_summary_generated_at`

**Date**: 2026-05-10 22:25:19-22:25:20 UTC  
**Narratives Affected**:
1. Bitcoin Holds $75K (68f32d197082f49df56956c6)
2. Senate Banking Committee (695eb4b3ce758d67abd6e8f4)
3. LayerZero Admits Mistakes (698baa105278ec9e19bf2a19)

**Finding**: `needs_summary_update=false` + `last_summary_generated_at=null`

---

## Root Cause Analysis

### Write Paths That Clear `needs_summary_update`

1. **narrative_refresh.py (line 136)** — SYNC point
   - Sets: `needs_summary_update=False` AND `last_summary_generated_at=datetime.now()`
   - ✅ Sets both fields atomically
   - ❌ NOT the culprit (refresh ran at 22:25:23, after updates at 22:25:19)

2. **narrative_service.py (line 1224)** — INGESTION point
   - Sets: `needs_summary_update=False` + `last_summary_generated_at=datetime.now()`
   - Called only during NEW narrative creation (line 1386-1402)
   - ❌ NOT called for existing narratives being updated
   - **KEY ISSUE**: Parameter NOT passed to `upsert_narrative()` function

3. **narrative_service.py (line 1401)** — UPSERT point
   - Function: `upsert_narrative()` (db/operations/narratives.py:64)
   - When updating existing narrative, line 252-253:
     ```python
     if needs_summary_update is not None:
         update_data["needs_summary_update"] = needs_summary_update
     ```
   - **⚠️ CRITICAL FINDING**: Function call at line 1386-1402 does NOT pass `needs_summary_update` parameter
   - Result: If called on existing narrative, field is NOT updated (remains null or existing value)

### Other Write Paths (Consolidation)

4. **narrative_service.py (_merge_narratives, line 1761-1773)** — CONSOLIDATION point
   - Merges two narratives, updates survivor with article_ids, article_count, etc.
   - **KEY BUG**: Does NOT set or preserve `needs_summary_update` field
   - Does NOT set `last_summary_generated_at`
   - If called on a flagged narrative, flag is silently dropped

---

## Timeline: 22:25:19-22:25:20

**What should have happened** (by your request):
- All 5 narratives flagged with `needs_summary_update=true`
- Refresh task queued at 22:25:23
- Refresh task processes the 5 flagged narratives
- All 5 updated with fresh summaries and timestamps

**What actually happened**:
1. **22:25:19-22:25:20** - External process updates 3 narratives, clears flag, leaves timestamp null
2. **22:25:23** - Refresh task starts, sees only 2 narratives with `needs_summary_update=true`
3. **22:25:27-22:25:33** - Refresh processes only SEC + Coinbase (the 2 visible)
4. Result: 2 refreshed successfully, 3 in inconsistent state

**Who cleared the 3 flags?** Unknown - not the refresh task (which hadn't started yet)

---

## Suspected Code Path: detect_narratives Race Condition

**Hypothesis**: An ingestion/clustering task ran between 22:25:19-22:25:20 and updated those 3 narratives.

**Evidence**:
- `last_updated` timestamps match exactly: 22:25:19-22:25:20 UTC
- Zero logs in worker/web showing who did it
- Pattern matches `detect_narratives()` behavior

**If correct**:
1. `detect_narratives()` runs periodically
2. Finds existing narratives for Bitcoin, Senate Banking, LayerZero
3. Calls `upsert_narrative()` to update them
4. Does NOT pass `needs_summary_update=None` (not included in call)
5. Field not in update_data, so it's not updated
6. But something ELSE clears it to false...

**Critical Gap**: The `upsert_narrative()` call at line 1386-1402 does NOT include `needs_summary_update` parameter, but our data shows these narratives DO have `needs_summary_update=false`, which means something explicitly set it.

---

## The Real Bug: Three Related Issues

### BUG-102 Severity: Missing `needs_summary_update` in upsert_narrative() call

**File**: `src/crypto_news_aggregator/services/narrative_service.py`  
**Line**: 1386-1402  
**Issue**: When calling `upsert_narrative()` after LLM generation, the function does NOT pass `needs_summary_update` parameter.

```python
narrative['needs_summary_update'] = False  # Set locally at line 1224
narrative['last_summary_generated_at'] = datetime.now(timezone.utc)
# ...
narrative_id = await upsert_narrative(
    # ... other params ...
    # ❌ MISSING: needs_summary_update=needs_summary_update
)
```

**Impact**: If narrative is updated (not created), `needs_summary_update` won't be set in DB because the parameter is missing.

### BUG-103: _merge_narratives() Drops `needs_summary_update`

**File**: `src/crypto_news_aggregator/services/narrative_service.py`  
**Line**: 1761-1773 (_merge_narratives)  
**Issue**: When merging narratives, the update does NOT preserve or set `needs_summary_update`:

```python
await narratives_collection.update_one(
    {"_id": survivor_id},
    {
        "$set": {
            "article_ids": combined_articles,
            "article_count": combined_article_count,
            "avg_sentiment": combined_sentiment,
            "timeline_data": combined_timeline,
            "lifecycle_state": combined_state,
            "last_updated": datetime.now(timezone.utc)
            # ❌ MISSING: "needs_summary_update", "last_summary_generated_at"
        }
    }
)
```

**Impact**: Merged narratives lose their refresh flag, violating BUG-102's guarantee.

---

## Remaining Mystery

**Why do the 3 narratives have `needs_summary_update=false`?**

The `upsert_narrative()` function at line 252-253 only sets the field if explicitly provided. If not provided, it's left alone. So either:

1. **detect_narratives() is explicitly setting it to false** somewhere we haven't found
2. **A different write path we haven't identified** is clearing the flag
3. **The consolidate_narratives() task** cleared them (but it didn't run at 22:25)

---

## Recommended Fixes

### Fix 1: Pass `needs_summary_update` to upsert_narrative() (BUG-102 extension)

**File**: `src/crypto_news_aggregator/services/narrative_service.py`  
**Line**: 1386-1402

```python
narrative_id = await upsert_narrative(
    # ... existing params ...
    needs_summary_update=narrative.get('needs_summary_update', False)
)
```

### Fix 2: Preserve `needs_summary_update` in _merge_narratives()

**File**: `src/crypto_news_aggregator/services/narrative_service.py`  
**Line**: 1761-1773

```python
await narratives_collection.update_one(
    {"_id": survivor_id},
    {
        "$set": {
            # ... existing fields ...
            "needs_summary_update": survivor.get("needs_summary_update", False),
            "last_summary_generated_at": survivor.get("last_summary_generated_at")
        }
    }
)
```

### Fix 3: Add audit logging for all narrative updates

Log whenever `needs_summary_update` changes to track the source of unexpected mutations.

---

## Classification

- **Type**: Code bug + race condition + missing parameter
- **Root Cause**: BUG-102 fix incomplete; missing parameter in upsert call
- **Severity**: High (silently loses refresh flags)
- **Should be added to**: BUG-102 ticket as extended scope, or new BUG-103

