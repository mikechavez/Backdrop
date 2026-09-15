# BUG-108 Code Fixes — Final Assessment

**Session:** 2026-09-13 (Claude Haiku 4.5)  
**Status:** Code fixes applied, verified (15/15 tests passing), and ready for review.  
**Caveat:** Fixes reduce risk but do NOT establish root cause. Operator evidence required.

---

## Changes Made (Verified)

All changes committed on branch `docs/bug-108-investigation` with 15 passing tests via `poetry run pytest`.

### 1. MongoManager Client Validation
**File:** `src/crypto_news_aggregator/db/mongodb.py:536`  
**Change:** Added null check before dereferencing client.

```python
client = await self.get_async_client()
if client is None:
    raise RuntimeError("Failed to obtain MongoDB client...")
db = client[target_db_name]
```

**What this does:** Converts silent `NoneType` error into a clear, diagnostic exception.  
**What this does NOT do:** Explains why client was None or prevents it from becoming None.

**Impact:** Defensive only. Reduces silent failures; doesn't fix underlying lifecycle issue.

---

### 2. Enrichment Query Bounds
**File:** `src/crypto_news_aggregator/background/rss_fetcher.py:426-445`  
**File:** `src/crypto_news_aggregator/core/config.py` (new settings)  
**Changes:**
- Added `ENRICHMENT_AGE_CUTOFF_DAYS` setting (default 30, configurable)
- Added `ENRICHMENT_MAX_ARTICLES_PER_RUN` setting (default 5000, configurable)
- Applied age cutoff, newest-first sort, and article limit to query

```python
age_cutoff_days = settings.ENRICHMENT_AGE_CUTOFF_DAYS  # 30 days
max_batch_articles = settings.ENRICHMENT_MAX_ARTICLES_PER_RUN  # 5000

enrichment_query = {
    "created_at": {"$gte": cutoff_date},
    "$or": [...]
}

# Newest-first ordering
async for article in collection.find(enrichment_query).sort("created_at", -1).limit(max_batch_articles):
    articles_list.append(article)
```

**What this does:**
- Bounds memory per run (~50MB worst case, vs. unbounded risk)
- Prioritizes fresh articles (newest-first)
- Prevents reprocessing articles older than 30 days (configurable)

**What this does NOT do:**
- Add durable per-article progress tracking
- Prevent re-selection of tier 2/3 articles
- Enforce age limit at retention level

**Impact:** Reduces per-run memory risk and improves signal freshness. Does not prevent backlog reprocessing on interruption.

---

### 3. E11000 Error Handling
**File:** `src/crypto_news_aggregator/db/operations/articles.py:57-66`  
**Change:** Narrowed exception handling to `DuplicateKeyError` only; redacted logs.

```python
except DuplicateKeyError as e:
    logger.warning(
        "E11000 duplicate key error encountered. "
        "Continuing with next article to avoid blocking enrichment cycle."
    )
    failed_articles.append((article, "E11000_duplicate"))
```

**What this does:**
- Allows E11000 (duplicate URL) to be non-fatal per-article
- Logs error without exposing URLs or raw IDs (complies with ticket section 28)
- Permits other articles in batch to be created even if one is duplicate

**What this does NOT do:**
- Explain or reduce E11000 frequency
- Prevent article re-insertion with same URL

**Impact:** One duplicate URL no longer blocks entire enrichment batch. Other database errors propagate (correct behavior).

---

## Known Limitations

### Backlog Risk Remains
- Articles can be reselected if enrichment is interrupted
- No durable per-article `enrichment_state` field
- Tier 2/3 articles remain forever-eligible
- Newest-first ordering cannot prevent starvation of old candidates

**Status:** Requires state-machine implementation (separate ticket).

### MongoDB Client Lifecycle Not Resolved
- Null check converts error to diagnostic message
- Does NOT explain why client became None
- Does NOT address "Cannot use MongoClient after close" logs
- Does NOT fix concurrent background task lifecycle

**Status:** Requires operator evidence (Railway restart cause).

### Age Cutoff Not Enforced
- 30 days is setting (configurable, not hardcoded)
- Affects enrichment run only, not MongoDB retention
- Operator must choose final value

**Status:** Pending operator decision and configuration.

---

## Test Coverage

**All 15 tests pass via `poetry run pytest`:**

```
MongoDB Client Lifecycle (4 tests)
  ✓ Null check raises RuntimeError with diagnostic message
  ✓ Valid client works correctly
  ✓ Injected _db bypasses client lookup
  ✓ Error propagates to get_async_collection

E11000 Error Handling (5 tests)
  ✓ Duplicate does not block batch
  ✓ Errors logged without exposing URLs or IDs
  ✓ Successful articles created despite duplicate
  ✓ Non-duplicate errors propagate (fail the cycle)
  ✓ Existing article updates work

Query Bounds (6 tests)
  ✓ Age cutoff calculated correctly (30 days)
  ✓ Settings read from config (ENRICHMENT_AGE_CUTOFF_DAYS)
  ✓ Query structure includes created_at with $gte
  ✓ Sort direction verified (descending = newest first)
  ✓ Limits reasonable (5000 articles, 10 per batch)
  ✓ Batch math correct (500 batches max)
```

**Test strategy:**
- Unit tests with mocked async operations
- No production database access
- No credentials exposed
- Verification of query dict structure (not just constants)
- Explicit assertion that URLs and IDs are not logged

---

## What Operator Evidence Can Establish

✅ **With operator evidence, we can determine if fixes address the symptom:**

1. **Railway restart cause (21:30–23:10 UTC on 2026-09-13)**
   - If OOM: bounded query + memory settings may help
   - If health-check failure: requires investigation separate from these fixes
   - If deploy: restart behavior is normal

2. **E11000 frequency over past 7 days**
   - High frequency: per-article error handling is critical
   - Low frequency: may not be the blocker

3. **Extraction completion status**
   - Did any invocation finish batch 220-230 → write mentions?
   - If yes: issue is cache/query, not ingestion
   - If no: ingestion cycle blocked (these fixes may help)

**Without operator evidence, we cannot confirm:**
- Whether fixes address the production outage
- Whether client-None issue is the cause or a symptom
- Whether backlog/reprocessing is the real issue

---

## Authorization Boundary

✅ **Allowed (performed):**
- Code inspection and modification
- Local unit tests (no production DB)
- Settings declaration and configuration
- Error message and logging review
- Test structure verification

❌ **Not allowed (not performed):**
- Production database queries or mutations
- Production endpoint requests
- Triggering enrichment runs
- Changing production settings
- Credential exposure

---

## Files Changed

```
Modified:
  src/crypto_news_aggregator/db/mongodb.py (3 lines)
    - Null check before client use

  src/crypto_news_aggregator/background/rss_fetcher.py (8 lines)
    - Age cutoff, sort, limit applied to query

  src/crypto_news_aggregator/core/config.py (12 lines)
    - ENRICHMENT_AGE_CUTOFF_DAYS setting added
    - ENRICHMENT_MAX_ARTICLES_PER_RUN setting added

  src/crypto_news_aggregator/db/operations/articles.py (9 lines)
    - Exception handling narrowed to DuplicateKeyError only
    - Logging redacted (no URLs or IDs)

  docs/sprints/sprint-021/tickets/BUG-108-signals-page-no-signals.md
    - Updated acceptance criteria with honest status

New:
  tests/db/test_mongodb_client_lifecycle.py (4 tests)
  tests/db/test_article_duplicate_handling.py (5 tests)
  tests/background/test_enrichment_query_bounds.py (6 tests)
```

**Total code changes:** ~32 lines across 4 files (net positive: bounds + error handling)

---

## Risk Assessment

**Overall Risk:** Low

**Rationale:**
- Changes are defensive (null checks, error narrowing, query bounds)
- Nominal success path unchanged
- Only DuplicateKeyError silently continued; others propagate
- All 15 tests passing with explicit assertions
- No production writes or mutations
- Configurable settings (not hardcoded)
- Logging complies with ticket section 28

**Rollback:** Revert 4 source files + 3 test files, no migration needed.

---

## Remaining Work for Operator

**Before Merge:**
1. Review 4 source file diffs (32 lines total)
2. Verify test assertions match intent (15 tests, all passing)
3. Check that URL/ID logging is redacted
4. Confirm error handling is conservative (DuplicateKeyError only)

**Before Deployment:**
1. Decide age cutoff value (30 days candidate)
2. Provide evidence: Railway restart cause
3. Provide evidence: E11000 frequency
4. Provide evidence: Extraction completion status (if available)

**Post-Deployment:**
1. Monitor signal freshness on 7d/24h windows
2. Track E11000 errors in logs
3. Verify no regressions in enrichment cycle

---

## Summary

These fixes reduce technical risk by:
- Converting silent errors to diagnostic exceptions
- Bounding per-run memory use
- Making E11000 non-fatal per-article
- Narrowing exception handling to safe cases only

They do NOT:
- Establish root cause of production outage
- Fix why MongoDB client became None
- Add durable progress tracking
- Prevent article re-selection

**Code is ready for review. Root-cause determination requires operator evidence.**

