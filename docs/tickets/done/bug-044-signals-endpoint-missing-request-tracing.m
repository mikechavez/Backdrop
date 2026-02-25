---
id: BUG-044
type: bug
status: completed
priority: critical
severity: high
created: 2026-02-25
updated: 2026-02-25
completed: 2026-02-25
---

# BUG-044: Signals Endpoint Lacks Request Tracing — Cannot Diagnose 110s Cold Cache

## Problem

The `/api/v1/signals/trending` endpoint logs enrichment counts (e.g., "Batch fetched 249 articles for 50 entities") but does **not** log the request parameters (`limit`, `offset`) that produced those counts. Without a request ID tying log lines together, it is impossible to determine whether the 110s cold-cache load (BUG-043) is caused by:

1. A second caller sending `limit=50` (stale client, background job, monitoring script, another tab)
2. The backend ignoring the frontend's `limit=15` and enriching more entities than requested
3. A hardcoded enrichment cap (e.g., `article_entity_limit=50`) decoupled from the pagination limit

This ambiguity is blocking resolution of BUG-043 Fix 2.

## Expected Behavior

Every request to `/signals/trending` should log, on a single correlated trace:
- The parsed request parameters (`limit`, `offset`, `timeframe`, `entity_type`, `min_score`)
- The number of signals after pagination (`num_signals_after_pagination`)
- The number of entities sent to article enrichment (`num_entities_for_article_fetch`)
- A request ID shared across all log lines for that request

If `num_entities_for_article_fetch > requested_limit`, the bug is mechanically identified.

## Actual Behavior

Logs show enrichment output but not input parameters:
```
[Signals] Computed 100 trending signals in 2.552s
[Signals] Batch fetched 125 narratives in 4.807s
[Signals] Batch fetched 249 articles for 50 entities in 103.249s
[Signals] Total request time: 110.608s, Payload: 105.91KB
```

Access log shows `limit=50` in the URL, but there is no way to confirm this is the same request that produced the 110s timing. All log lines also appear duplicated (known issue from BUG-043 Fix 4).

## Steps to Reproduce

1. Load the Signals page in production (cold cache)
2. Observe backend logs showing "50 entities" in article fetch
3. Observe browser DevTools showing `limit=15` in the request URL
4. Attempt to determine whether the 50-entity fetch was triggered by the browser request or a different caller
5. Fail — no request ID or param logging to correlate

## Environment

- Environment: production (Railway)
- Backend: FastAPI + Uvicorn
- Database: MongoDB Atlas M0
- Frontend: Vercel (React + Vite)
- User impact: high — blocks diagnosis and resolution of BUG-043 (120s cold cache)

## Screenshots/Logs

Production logs (2026-02-25 13:14–13:16 UTC):
```
[Signals] Computed 100 trending signals in 2.552s          ← no request ID
[Signals] Batch fetched 125 narratives in 4.807s           ← no request ID
[Signals] Batch fetched 249 articles for 50 entities in 103.249s  ← 50 entities, but from which request?
[Signals] Total request time: 110.608s, Payload: 105.91KB
API_REQUEST_COMPLETED: GET /api/v1/signals/trending 200 110611.86ms
GET /api/v1/signals/trending?limit=50&offset=0 HTTP/1.1 200  ← limit=50, but is this the same request?
```

Key ambiguity: Browser sends `limit=15`, access log shows `limit=50`. Without trace IDs, these cannot be correlated.

---

## Resolution

**Status:** ✅ COMPLETED (2026-02-25)
**Branch:** `fix/bug-043-paginate-before-fetch`
**Commit:** bd7dbb8
**Effort:** 10 minutes actual

### Root Cause

Missing observability instrumentation in the signals endpoint handler.

### Implementation Summary

✅ **Added to `src/crypto_news_aggregator/api/v1/endpoints/signals.py`:**

1. **Import uuid:** Added `from uuid import uuid4` to imports (line 13)

2. **Request ID generation:** Added at top of `get_trending_signals()` handler (line 425):
   ```python
   req_id = uuid4().hex[:8]
   ```

3. **Request parameter logging:** Added immediately after req_id generation (line 428):
   ```python
   logger.info(f"[{req_id}] Signals request: limit={limit}, offset={offset}, min_score={min_score}, entity_type={entity_type}, timeframe={timeframe}")
   ```

4. **Cache hit logging:** Added when cache is hit (line 451):
   ```python
   logger.info(f"[{req_id}] Cache hit: total_count={total_count}, returning {len(paged_trending)} signals ({offset}-{offset + len(paged_trending) - 1})")
   ```

5. **Cache miss logging:** Added when cache misses (line 485):
   ```python
   logger.info(f"[{req_id}] Cache miss, computing trending signals...")
   ```

6. **Compute completion logging:** Updated to include req_id (line 492):
   ```python
   logger.info(f"[{req_id}] Computed {len(trending)} trending signals in {compute_time:.3f}s")
   ```

7. **Diagnostic enrichment plan logging:** Added new line with complete context (line 505):
   ```python
   logger.info(f"[{req_id}] Enrichment plan: requested_limit={limit}, page_items={len(paged_signals)}, article_entities={len(paged_entities)}, narrative_ids={len(paged_narrative_ids)}")
   ```
   This is the KEY diagnostic line that will immediately reveal:
   - If `article_entities > requested_limit` → enrichment ignoring pagination
   - If `article_entities = requested_limit` → pagination working correctly

8. **Batch fetch logging:** Updated both narrative and article fetch logs to include req_id (lines 509, 514):
   ```python
   logger.info(f"[{req_id}] Batch fetched {len(narratives_list)} narratives in {time.time() - batch_start:.3f}s")
   logger.info(f"[{req_id}] Batch fetched {total_articles} articles for {len(paged_entities)} entities in {time.time() - batch_start:.3f}s")
   ```

9. **Total time logging:** Updated with req_id (line 544):
   ```python
   logger.info(f"[{req_id}] Total request time: {total_time:.3f}s, Payload: {payload_size:.2f}KB")
   ```

10. **Cache store logging:** Added after cache set (line 562):
    ```python
    logger.info(f"[{req_id}] Cached {len(trending)} signals for future requests")
    ```

11. **Error logging:** Updated exception handler with req_id (line 585):
    ```python
    logger.error(f"[{req_id}] Failed to compute trending signals: {e}")
    ```

### Verification

All 11 log lines now include `[{req_id}]` prefix for full request tracing. The diagnostic line (item 7) provides the key comparison:
- **requested_limit** = what frontend sent (expected: 15)
- **page_items** = signals returned (expected: 15)
- **article_entities** = how many entities we enriched (expected: 15)
- **narrative_ids** = unique narrative IDs across paged signals

If `article_entities = 50` when `requested_limit = 15`, we've found the bug.

### Changes Required

**1. Log request params at top of handler (1 line, immediate diagnostic value):**
```python
logger.info(f"[Signals] Request params: limit={limit} offset={offset} timeframe={timeframe} entity_type={entity_type} min_score={min_score}")
```

**2. Add request ID to all log lines in the endpoint:**
```python
import uuid

req_id = uuid.uuid4().hex[:8]
logger.info(f"[Signals][{req_id}] Request params: limit={limit} offset={offset}")
logger.info(f"[Signals][{req_id}] Computed {len(trending)} trending signals in {elapsed:.3f}s")
logger.info(f"[Signals][{req_id}] candidates={len(trending)} page_items={len(paged_signals)}")
logger.info(f"[Signals][{req_id}] article_entities={len(paged_entities)} narrative_ids={len(paged_narrative_ids)}")
logger.info(f"[Signals][{req_id}] Batch fetched {n} articles for {len(paged_entities)} entities in {elapsed:.3f}s")
logger.info(f"[Signals][{req_id}] Total request time: {total:.3f}s, Payload: {size:.2f}KB")
```

**3. Log the three diagnostic numbers on one line:**
```python
logger.info(f"[Signals][{req_id}] DIAGNOSTIC: requested_limit={limit} page_items={len(paged_signals)} article_entities={len(entities_for_fetch)}")
```

If `article_entities > requested_limit`, the enrichment is ignoring pagination.

### Testing

After deploying, reproduce once on cold cache:
- If logs show `requested_limit=15` but `article_entities=50` → backend enrichment bug (hardcoded cap or pagination applied too late)
- If logs show `requested_limit=50` → second caller exists, find and fix it
- If logs show `requested_limit=15` and `article_entities=15` → Fix 1 is working, investigate why total is still slow

### Files to Change

1. `src/crypto_news_aggregator/api/v1/endpoints/signals.py` — Add request ID generation, param logging, and diagnostic line

### Related Issues

- **BUG-043** — Parent issue (120s cold cache). This ticket unblocks BUG-043 diagnosis.
- **BUG-043 Fix 4** — Duplicate log lines (separate issue, compounds the tracing problem)
- **FEATURE-048a** — Backend pagination (may or may not be deployed; this ticket will confirm)