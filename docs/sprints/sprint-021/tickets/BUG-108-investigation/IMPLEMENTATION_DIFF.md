# BUG-108: Implementation Diff for Code Review

**Purpose:** Show exact code changes required so you can review before deployment decision.

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`

---

## Change 1: Add Schema and Initialization Function

**Location:** After imports, before `_STOPWORDS`

```python
# Add near top of file after imports

async def init_enrichment_state(db):
    """Backfill enrichment_state for articles created before this fix.
    
    Called once on startup. Idempotent: safe to call multiple times.
    """
    collection = db.articles
    
    # Count articles missing enrichment_state
    legacy_count = await collection.count_documents({
        "enrichment_state": {"$exists": False}
    })
    
    if legacy_count == 0:
        logger.debug("No legacy articles to backfill")
        return
    
    logger.info(f"Backfilling enrichment_state for {legacy_count} legacy articles")
    
    # Backfill: set enrichment_state to pending for all missing
    await collection.update_many(
        {"enrichment_state": {"$exists": False}},
        {"$set": {
            "enrichment_state": {
                "status": "pending",
                "last_attempt": None,
                "attempt_count": 0,
                "error": None,
                "completed_at": None
            }
        }}
    )
    
    logger.info(f"✅ Backfilled {legacy_count} articles with enrichment_state")
```

---

## Change 2: Call Backfill on Startup

**Location:** In `lifespan()` function (main.py), after MongoDB initialization

**File:** `src/crypto_news_aggregator/main.py` (NOT rss_fetcher.py)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage lifespan events for the web server."""
    logger.info("--- Web Server Lifespan Startup ---")
    await initialize_mongodb()
    logger.info("Web server workers connected to MongoDB.")
    
    # NEW: Initialize enrichment_state for legacy articles (before enrichment starts)
    db = await mongo_manager.get_async_database()
    from .background.rss_fetcher import init_enrichment_state
    try:
        await init_enrichment_state(db)
    except Exception as e:
        logger.warning(f"Failed to backfill enrichment_state: {e}")
        # Non-fatal: enrichment will still work, just won't process legacy articles
    
    # ... rest of startup code unchanged ...
    yield
    # ... shutdown code unchanged ...
```

---

## Change 3: Update Enrichment Query

**Location:** `process_new_articles_from_mongodb()` function, around line 426

**BEFORE:**
```python
enrichment_query = {
    "$or": [
        {"relevance_score": {"$exists": False}},
        {"relevance_score": None},
        {"relevance_score": 0.0},
        {"sentiment_score": {"$exists": False}},
        {"sentiment_score": None},
        {"sentiment_score": 0.0},
        {"sentiment": {"$exists": False}},
        {"relevance_tier": {"$exists": False}},
        {"relevance_tier": None},
    ]
}

articles_list = []
async for article in collection.find(enrichment_query):
    articles_list.append(article)
```

**AFTER:**
```python
# Configuration
MAX_BACKLOG_PER_CYCLE = 500
MAX_RETRY_ATTEMPTS = 3
STALE_IN_PROGRESS_SECONDS = 600  # 10 minutes
MAX_BACKLOG_AGE_DAYS = 30  # Operator decision: 30, unlimited, or progressive

# Calculate time boundaries
now = datetime.now(timezone.utc)
min_created_at = now - timedelta(days=MAX_BACKLOG_AGE_DAYS)
stale_threshold = now - timedelta(seconds=STALE_IN_PROGRESS_SECONDS)

# Build eligibility query: articles ready for processing
enrichment_query = {
    "created_at": {"$gte": min_created_at},  # Age boundary
    "$or": [
        # Category 1: Never attempted
        {"enrichment_state.status": "pending"},
        # Category 2: Hung in_progress (restart recovery)
        {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": {"$lt": stale_threshold}
        },
        # Category 3: Failed, ready for retry based on backoff
        # Retry 1: immediate (no backoff)
        {
            "enrichment_state.status": "failed",
            "enrichment_state.attempt_count": 1
        },
        # Retry 2: after 5 min (300s)
        {
            "enrichment_state.status": "failed",
            "enrichment_state.attempt_count": 2,
            "enrichment_state.last_attempt": {"$lt": now - timedelta(seconds=300)}
        },
        # Retry 3: after 30 min (1800s)
        {
            "enrichment_state.status": "failed",
            "enrichment_state.attempt_count": 3,
            "enrichment_state.last_attempt": {"$lt": now - timedelta(seconds=1800)}
        },
    ]
}

# Fetch candidates
articles_list = await collection.find(enrichment_query)\
    .sort("created_at", -1)\
    .limit(MAX_BACKLOG_PER_CYCLE)\
    .to_list(MAX_BACKLOG_PER_CYCLE)

# Log backlog status
total_eligible = await collection.count_documents(enrichment_query)
if total_eligible > MAX_BACKLOG_PER_CYCLE:
    logger.info(
        f"⚠️  Enrichment backlog: {total_eligible} articles eligible "
        f"(processing {len(articles_list)} this cycle, "
        f"next cycle in ~30min). Age window: <{MAX_BACKLOG_AGE_DAYS}d"
    )
```

---

## Change 4: Atomic Claim Before Processing

**Location:** Before processing each article (new code, around line 461)

**AFTER (new section before the existing batch loop):**
```python
# NEW: Atomic article claim to prevent double-processing
async def try_claim_article(article_id, current_status="pending"):
    """Atomically claim an article for processing.
    
    Returns article if claim succeeded, None if already claimed.
    Only increments attempt_count if claim succeeds.
    """
    result = await collection.find_one_and_update(
        {
            "_id": article_id,
            "enrichment_state.status": current_status
        },
        {
            "$set": {
                "enrichment_state.status": "in_progress",
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            },
            "$inc": {
                "enrichment_state.attempt_count": 1
            }
        },
        return_document=ReturnDocument.AFTER
    )
    return result
```

**Then modify the processing loop:**

**BEFORE (line ~461):**
```python
for article in batch:
    article_id = article.get("_id")
    # ... process article ...
```

**AFTER:**
```python
for article in batch:
    article_id = article.get("_id")
    current_status = article.get("enrichment_state", {}).get("status", "pending")
    
    # Atomically claim the article (prevents double-processing if concurrent)
    claimed = await try_claim_article(article_id, current_status)
    if claimed is None:
        logger.debug(f"Article {article_id} already claimed by another process, skipping")
        continue
    
    # Use the claimed version (has updated last_attempt and attempt_count)
    article = claimed
    article_id = str(article.get("_id"))
    current_attempt = article.get("enrichment_state", {}).get("attempt_count", 1)
    
    try:
        # ... process article (entity extraction, tier classification, etc.) ...
```

---

## Change 5: Mark Article as Completed After Tier Classification

**Location:** After tier classification, around line 672

**BEFORE:**
```python
# Old code just updates tier
await collection.update_one(
    {"_id": article_data["original_article"].get("_id")},
    {
        "$set": {
            "relevance_tier": classification["tier"],
            "relevance_reason": classification["reason"],
            "updated_at": datetime.now(timezone.utc),
        }
    }
)
```

**AFTER:**
```python
# NEW: Mark as completed (state machine) in addition to tier assignment
article_id = article_data["original_article"].get("_id")
tier = classification["tier"]

update_doc = {
    "$set": {
        "enrichance_tier": tier,
        "relevance_reason": classification["reason"],
        "updated_at": datetime.now(timezone.utc),
        # NEW: Mark enrichment as completed (regardless of tier)
        "enrichment_state.status": "completed",
        "enrichment_state.completed_at": datetime.now(timezone.utc),
    }
}

await collection.update_one({"_id": article_id}, update_doc)

# If tier 1, enrichment will continue and set more fields
# If tier 2/3, enrichment is skipped, but status is still marked completed
# (prevents infinite re-selection even though some fields are missing)
```

---

## Change 6: Mark Article as Failed on Transient Error

**Location:** Around existing error handling (new error path)

**ADD new except block:**
```python
except Exception as e:
    # Transient error during processing
    article_id = str(article.get("_id"))
    current_attempt = article.get("enrichment_state", {}).get("attempt_count", 1)
    
    if current_attempt < MAX_RETRY_ATTEMPTS:
        # Retry eligible: mark as failed, will be retried with backoff
        await collection.update_one(
            {"_id": article_id},
            {
                "$set": {
                    "enrichment_state.status": "failed",
                    "enrichment_state.error": f"{type(e).__name__}: {str(e)[:100]}",
                    "enrichment_state.last_attempt": datetime.now(timezone.utc),
                }
            }
        )
        logger.warning(
            f"Article {article_id} enrichment failed (attempt {current_attempt}/{MAX_RETRY_ATTEMPTS}): {type(e).__name__}. Will retry."
        )
    else:
        # Max retries exceeded: mark as completed with error (stop retrying)
        await collection.update_one(
            {"_id": article_id},
            {
                "$set": {
                    "enrichment_state.status": "completed",
                    "enrichment_state.error": f"max_retries_exceeded after {current_attempt} attempts",
                    "enrichment_state.completed_at": datetime.now(timezone.utc),
                }
            }
        )
        logger.error(
            f"Article {article_id} enrichment abandoned after {current_attempt} failed attempts."
        )
    
    # Don't re-raise; continue with next article in batch
    continue
```

---

## Change 7: Import Statements

**Add to imports at top of file:**
```python
from pymongo import ReturnDocument
from datetime import datetime, timezone, timedelta
```

---

## Summary of Changes

| Location | Type | Lines | Purpose |
|----------|------|-------|---------|
| Top of file | New function | ~20 | `init_enrichment_state()` backfill legacy articles |
| main.py lifespan | New code | ~5 | Call backfill on startup |
| Query building | Replaced | ~40 | Support state machine + retry backoff |
| Processing loop | New code | ~8 | Atomic claim prevents double-processing |
| Tier classification | Modified | ~8 | Mark as completed (not just tier) |
| Error handling | New code | ~30 | Handle transient vs. max-retry failures |
| Imports | New | ~2 | Add ReturnDocument, datetime utilities |

**Total additions/changes:** ~115 lines (some existing lines modified)

---

## Decision Points in Code

These require your decision before implementation:

1. **`MAX_BACKLOG_AGE_DAYS = 30`**
   - Option A: Set to `None` for unlimited (process all historical)
   - Option B: Set to `30` for fresh articles only (recommended)
   - Option C: Set to `90` for progressive (needs additional logic)
   - **DECISION REQUIRED**

2. **`STALE_IN_PROGRESS_SECONDS = 600`**
   - 600 seconds = 10 minutes
   - Should match expected cycle time (<10 min safe, longer safer)
   - Prevents double-claiming if process hangs
   - **Can adjust if cycle time analysis shows different value needed**

3. **`MAX_RETRY_ATTEMPTS = 3`**
   - How many times should transient failures be retried?
   - 3 attempts with 0/5/30 min backoff seems reasonable
   - **Can adjust if different retry policy desired**

---

## Testing This Diff

Before any deployment:

1. **Run 4 unit tests locally:**
   - Test 1: Legacy article backfill
   - Test 2: Atomic claim prevents double-processing
   - Test 3: Process interruption recovery
   - Test 4: Exact retry count (3 attempts)
   - See `STATE_MACHINE_CORRECTED.md` for test code

2. **Verify MongoDB syntax:**
   - All queries use dotted paths for nested fields
   - All updates use separate `$set` and `$inc` operators
   - `find_one_and_update` uses `return_document=ReturnDocument.AFTER`

3. **Check for regressions:**
   - Entity extraction logic unchanged
   - Tier classification logic unchanged
   - Mention creation logic unchanged
   - Only adds state tracking and retry policy

---

## Deployment Decision Gate

**Before deploying this code:**

- [ ] Railway evidence received (topology, extraction trace, E11000 baseline)
- [ ] Backlog age cutoff decided (A/B/C)
- [ ] This diff reviewed for correctness
- [ ] 4 unit tests pass locally
- [ ] No regressions in existing functionality

**Once all checks pass:** Ready for code review, merge, and deployment.

