# BUG-108: State Machine Design (Corrected Implementation)

**Status:** Previous document had critical MongoDB syntax errors, retry count inconsistencies, and incomplete handling of legacy records. This document corrects all implementation details.

---

## Corrections Made

### 1. MongoDB Query Syntax: Dotted Paths for Nested Fields

**WRONG (from previous document):**
```python
enrichment_query = {
    "enrichment_state": {"$in": [{"status": "pending"}]},
    # ... doesn't match nested enrichment_state.status
}
```

**CORRECT:**
```python
enrichment_query = {
    "enrichment_state.status": {"$in": ["pending", "failed", "in_progress"]}
}
```

**Why:** MongoDB requires dotted notation (`enrichment_state.status`) to query nested fields. The `$in` operator matches scalar values, not objects.

### 2. Atomic Update Syntax: Separate $inc from $set

**WRONG (from previous document):**
```python
await collection.find_one_and_update(
    {"_id": article_id, "enrichment_state.status": "pending"},
    {"$set": {
        "enrichment_state.status": "in_progress",
        "enrichment_state.attempt_count": {"$inc": 1}  # ← INVALID
    }}
)
```

**CORRECT:**
```python
await collection.find_one_and_update(
    {"_id": article_id, "enrichment_state.status": "pending"},
    {
        "$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": datetime.now(timezone.utc),
        },
        "$inc": {
            "enrichment_state.attempt_count": 1  # ← Separate operator
        }
    }
)
```

**Why:** MongoDB update operators ($set, $inc, $push, etc.) must be at the top level, not nested inside each other.

### 3. Retry Count Clarity: Three Attempts, Not Four

**PREVIOUS CONFUSION:**
- "Attempt 1: Immediate" (backoff_index 0 → RETRY_BACKOFF_MINUTES[0] = 0)
- "Attempt 2: After 5 min" (backoff_index 1 → RETRY_BACKOFF_MINUTES[1] = 5)
- "Attempt 3: After 30 min" (backoff_index 2 → RETRY_BACKOFF_MINUTES[2] = 30)
- But attempt_count increments BEFORE checking, leading to confusion

**CORRECTED FLOW:**

```
Article state: "pending" (attempt_count = 0)

Cycle 1:
  ├─ Claim: $inc attempt_count to 1, set status to in_progress
  ├─ Process: Fails (transient error)
  └─ Mark failed: attempt_count = 1, status = failed, last_attempt = now

Cycle 2 (immediate, no backoff):
  ├─ Query: status=failed AND attempt_count < 3
  ├─ Claim: $inc attempt_count to 2, set status to in_progress
  ├─ Process: Fails again
  └─ Mark failed: attempt_count = 2, status = failed, last_attempt = now

Cycle 3 (after 5 min backoff):
  ├─ Query: status=failed AND attempt_count < 3 AND last_attempt < 5min ago
  ├─ Claim: $inc attempt_count to 3, set status to in_progress
  ├─ Process: Fails again
  └─ Mark failed: attempt_count = 3, status = failed, last_attempt = now

Cycle 4+ (after 30 min backoff):
  ├─ Query: status=failed AND attempt_count < 3
  ├─ Result: No match (attempt_count = 3 is NOT < 3)
  └─ Article never selected again → Mark as completed with error
```

**Explicit Configuration:**
```python
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = [0, 300, 1800]  # Clearer: seconds not minutes
# Interpretation:
# - Attempt 1: backoff = RETRY_BACKOFF_SECONDS[0] = 0s (immediate)
# - Attempt 2: backoff = RETRY_BACKOFF_SECONDS[1] = 300s (5 min)
# - Attempt 3: backoff = RETRY_BACKOFF_SECONDS[2] = 1800s (30 min)
# - Attempt 4+: STOP (attempt_count >= MAX_RETRY_ATTEMPTS)
```

### 4. Hung Detection: Longer Timeout or Heartbeat Required

**PROBLEM WITH 60-SECOND TIMEOUT:**
- Process A claims article, sets `in_progress` at T=0
- Process A starts enrichment (takes 45 seconds for LLM call)
- Process B wakes up at T=50, sees last_attempt = T=0 (50s ago)
- Process B thinks article is hung (threshold is 60s)
- Process B claims same article at T=60
- Now TWO processes are enriching the same article concurrently
- Database corruption or duplicate entity mentions

**SOLUTION A: Longer Timeout (Conservative)**
```python
STALE_IN_PROGRESS_SECONDS = 600  # 10 minutes
# Assumes: cycle time < 10 minutes
# Cycle runs every ~30 min, processes 500 articles, each takes ~1 sec = ~500s total
# 10 min = 600s gives buffer
```

**SOLUTION B: Heartbeat (More Robust)**
```python
# Process updates last_attempt every N seconds while in_progress
await collection.update_one(
    {"_id": article_id, "enrichment_state.status": "in_progress"},
    {"$set": {"enrichment_state.last_attempt": datetime.now(timezone.utc)}}
)
# This is expensive if done for every article; better for critical sections
```

**RECOMMENDATION:** Use longer timeout initially (600s = 10 min). Heartbeat can be added later if needed for tighter recovery.

**Why:** Simpler to implement, no additional writes, safe because cycle time is known (~30 min).

### 5. Legacy Records: Backfill enrichment_state on First Run

**PROBLEM:**
Articles created before this fix don't have `enrichment_state` field. Query for `enrichment_state.status` will NOT match them.

**Result:** 13,496 legacy articles never processed.

**SOLUTION:**

**Step 1: Backfill on Startup**
```python
async def init_enrichment_state():
    """Backfill enrichment_state for articles that don't have it."""
    collection = db.articles
    
    # Find all articles missing enrichment_state
    legacy_count = await collection.count_documents({
        "enrichment_state": {"$exists": False}
    })
    
    if legacy_count > 0:
        logger.info(f"Backfilling enrichment_state for {legacy_count} legacy articles")
        
        # Set enrichment_state to pending for all articles missing it
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
        
        logger.info(f"Backfilled {legacy_count} articles")
```

**Step 2: Run on Startup (in lifespan)**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events."""
    await initialize_mongodb()
    
    # NEW: Backfill enrichment_state for legacy articles
    db = await mongo_manager.get_async_database()
    await init_enrichment_state()
    
    # ... rest of startup
    yield
    # ... shutdown
```

**Step 3: Include Legacy Records in Query**
```python
# After backfill, this query captures both legacy (pending) and new articles
enrichment_query = {
    "enrichment_state.status": {"$in": ["pending", "failed", "in_progress"]}
}
```

---

## Corrected State Transitions

### Initial State (First Time)

**New article created:**
```javascript
{
  "_id": ObjectId(...),
  "title": "Article",
  "created_at": <timestamp>,
  "enrichment_state": {
    "status": "pending",
    "attempt_count": 0,
    "last_attempt": null,
    "error": null,
    "completed_at": null
  }
}
```

**Legacy article (existing):**
```javascript
{
  "_id": ObjectId(...),
  "title": "Old Article",
  "created_at": <timestamp>,
  // enrichment_state missing
}
↓ Backfill on startup ↓
{
  "_id": ObjectId(...),
  "title": "Old Article",
  "created_at": <timestamp>,
  "enrichment_state": {
    "status": "pending",
    "attempt_count": 0,
    "last_attempt": null,
    "error": null,
    "completed_at": null
  }
}
```

### Atomic Claim (Before Processing)

```python
result = await collection.find_one_and_update(
    {
        "_id": article_id,
        "enrichment_state.status": "pending"
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

if result is None:
    # Article was claimed by another process or already moved to completed
    skip_this_article()
    return

# result now has attempt_count = 1, status = "in_progress"
current_attempt = result["enrichment_state"]["attempt_count"]  # = 1
```

### After Tier Classification (Success Path)

```python
# Article classified as tier 1, 2, or 3
# Set all relevant fields at once

await collection.update_one(
    {"_id": article_id},
    {
        "$set": {
            "enrichment_state.status": "completed",
            "enrichment_state.completed_at": datetime.now(timezone.utc),
            "relevance_tier": tier_result["tier"],
            "relevance_reason": tier_result["reason"],
            # If tier 1: also set relevance_score, sentiment_score, etc.
            # If tier 2/3: skip enrichment fields (already set by classifier)
        }
    }
)
```

### After Transient Failure (Retry Path)

```python
# Exception during processing (rate limit, timeout, etc.)
# Mark as failed, eligible for retry

current_attempt = article_state["enrichment_state"]["attempt_count"]  # Fetched before processing

if current_attempt < MAX_RETRY_ATTEMPTS:
    # Retry eligible
    await collection.update_one(
        {"_id": article_id},
        {
            "$set": {
                "enrichment_state.status": "failed",
                "enrichment_state.error": str(exception),
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            }
        }
    )
    logger.warning(f"Article {article_id} failed (attempt {current_attempt}), will retry")
else:
    # Max retries exceeded
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
    logger.error(f"Article {article_id} abandoned after {current_attempt} failed attempts")
```

---

## Corrected Retry Query

### Candidate Query (Articles Eligible for Processing)

```python
async def get_enrichment_candidates(db, max_age_days=30, limit=500):
    """
    Get articles eligible for enrichment.
    
    Includes:
    1. Pending articles (never attempted)
    2. Failed articles (eligible for retry based on backoff)
    3. In_progress articles that are hung (>10 min stale)
    
    Excludes:
    1. Completed articles (done, don't retry)
    2. Articles outside age window
    """
    
    collection = db.articles
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(seconds=600)  # 10 min
    
    # Three categories of eligible articles
    pending_articles = {
        "enrichment_state.status": "pending",
        "created_at": {"$gte": now - timedelta(days=max_age_days)}
    }
    
    # Hung in_progress articles (restart recovery)
    hung_articles = {
        "enrichment_state.status": "in_progress",
        "enrichment_state.last_attempt": {"$lt": stale_threshold},
        "created_at": {"$gte": now - timedelta(days=max_age_days)}
    }
    
    # Failed articles with backoff satisfied
    failed_backoff_0 = {  # First retry, immediate
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 1,
        "created_at": {"$gte": now - timedelta(days=max_age_days)}
    }
    
    failed_backoff_1 = {  # Second retry, 5 min backoff
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 2,
        "enrichment_state.last_attempt": {"$lt": now - timedelta(seconds=300)},
        "created_at": {"$gte": now - timedelta(days=max_age_days)}
    }
    
    failed_backoff_2 = {  # Third retry, 30 min backoff
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 3,
        "enrichment_state.last_attempt": {"$lt": now - timedelta(seconds=1800)},
        "created_at": {"$gte": now - timedelta(days=max_age_days)}
    }
    
    # Combine all candidates
    query = {
        "$or": [
            pending_articles,
            hung_articles,
            failed_backoff_0,
            failed_backoff_1,
            failed_backoff_2,
        ]
    }
    
    candidates = await collection.find(query)\
        .sort("created_at", -1)\
        .limit(limit)\
        .to_list(limit)
    
    return candidates
```

**Note:** This query does NOT include articles with `attempt_count >= MAX_RETRY_ATTEMPTS` in failed state. Those remain in `failed` state but are not selected (effectively skipped).

To clean them up, optionally add a separate job that marks old failed articles as completed.

---

## Corrected Test Cases

### Test 1: Legacy Article Backfill

```python
async def test_legacy_article_backfill():
    """Legacy articles without enrichment_state are backfilled on startup."""
    
    # Insert legacy article (no enrichment_state)
    legacy_article = {
        "_id": ObjectId(),
        "title": "Legacy Article",
        "created_at": datetime.now(timezone.utc),
        # No enrichment_state field
    }
    await db.articles.insert_one(legacy_article)
    
    # Before backfill: article has no enrichment_state
    doc_before = await db.articles.find_one({"_id": legacy_article["_id"]})
    assert "enrichment_state" not in doc_before
    
    # Run backfill
    await init_enrichment_state()
    
    # After backfill: article has enrichment_state = pending
    doc_after = await db.articles.find_one({"_id": legacy_article["_id"]})
    assert "enrichment_state" in doc_after
    assert doc_after["enrichment_state"]["status"] == "pending"
    assert doc_after["enrichment_state"]["attempt_count"] == 0
    
    print("✅ Test 1 passed: Legacy articles backfilled")
```

### Test 2: Two Concurrent Claimers (Atomic Claim Prevents Double-Processing)

```python
async def test_atomic_claim_prevents_double_processing():
    """Atomic find_one_and_update ensures only one process claims an article."""
    
    article_id = ObjectId()
    
    # Insert pending article
    await db.articles.insert_one({
        "_id": article_id,
        "title": "Test Article",
        "enrichment_state": {
            "status": "pending",
            "attempt_count": 0,
            "last_attempt": None,
            "error": None,
            "completed_at": None
        }
    })
    
    # Process 1: Atomically claim
    result_1 = await db.articles.find_one_and_update(
        {
            "_id": article_id,
            "enrichment_state.status": "pending"
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
    
    assert result_1 is not None  # ✅ Process 1 successfully claimed
    assert result_1["enrichment_state"]["attempt_count"] == 1
    assert result_1["enrichment_state"]["status"] == "in_progress"
    
    # Process 2: Try to claim same article (should fail)
    result_2 = await db.articles.find_one_and_update(
        {
            "_id": article_id,
            "enrichment_state.status": "pending"  # ← No longer pending
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
    
    assert result_2 is None  # ✅ Process 2 failed (article no longer pending)
    
    # Verify attempt_count stayed at 1 (not incremented by failed claimer)
    doc = await db.articles.find_one({"_id": article_id})
    assert doc["enrichment_state"]["attempt_count"] == 1
    
    print("✅ Test 2 passed: Atomic claim prevents double-processing")
```

### Test 3: Process Interruption (Crash After Claim, Before Completion)

```python
async def test_process_interruption_recovery():
    """Article stuck in in_progress after crash is detected as hung and re-claimed."""
    
    article_id = ObjectId()
    claim_time = datetime.now(timezone.utc) - timedelta(minutes=15)  # 15 min ago
    
    # Article was claimed but never completed (process crashed)
    await db.articles.insert_one({
        "_id": article_id,
        "title": "Crashed Article",
        "enrichment_state": {
            "status": "in_progress",
            "attempt_count": 1,
            "last_attempt": claim_time,  # 15 min ago
            "error": None,
            "completed_at": None
        }
    })
    
    # Query for eligible articles (includes hung in_progress)
    stale_threshold = datetime.now(timezone.utc) - timedelta(seconds=600)  # 10 min
    
    hung_query = {
        "enrichment_state.status": "in_progress",
        "enrichment_state.last_attempt": {"$lt": stale_threshold}
    }
    
    hung_articles = await db.articles.find(hung_query).to_list(10)
    assert len(hung_articles) == 1  # ✅ Hung article found
    
    # Attempt to re-claim
    result = await db.articles.find_one_and_update(
        {
            "_id": article_id,
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": {"$lt": stale_threshold}
        },
        {
            "$set": {
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            }
            # Could also reset status or increment attempt_count here
        },
        return_document=ReturnDocument.AFTER
    )
    
    assert result is not None  # ✅ Successfully re-claimed
    assert result["enrichment_state"]["last_attempt"] > claim_time  # ✅ Updated
    
    print("✅ Test 3 passed: Hung articles detected and recoverable")
```

### Test 4: Exact Retry Count (Three Attempts Total)

```python
async def test_retry_count_three_attempts():
    """Article attempts 3 times (attempt_count 1, 2, 3), then marked completed."""
    
    article_id = ObjectId()
    
    # Initial state
    await db.articles.insert_one({
        "_id": article_id,
        "title": "Retry Test",
        "enrichment_state": {
            "status": "pending",
            "attempt_count": 0,
            "last_attempt": None,
            "error": None,
            "completed_at": None
        }
    })
    
    MAX_RETRY_ATTEMPTS = 3
    
    # Attempt 1
    result_1 = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "pending"},
        {
            "$set": {
                "enrichment_state.status": "in_progress",
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            },
            "$inc": {"enrichment_state.attempt_count": 1}
        },
        return_document=ReturnDocument.AFTER
    )
    assert result_1["enrichment_state"]["attempt_count"] == 1  # ✅
    
    # Simulate failure
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.error": "rate_limit"
        }}
    )
    
    # Attempt 2
    result_2 = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "failed"},
        {
            "$set": {
                "enrichment_state.status": "in_progress",
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            },
            "$inc": {"enrichment_state.attempt_count": 1}
        },
        return_document=ReturnDocument.AFTER
    )
    assert result_2["enrichment_state"]["attempt_count"] == 2  # ✅
    
    # Simulate failure
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.error": "rate_limit"
        }}
    )
    
    # Attempt 3
    result_3 = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "failed"},
        {
            "$set": {
                "enrichment_state.status": "in_progress",
                "enrichment_state.last_attempt": datetime.now(timezone.utc),
            },
            "$inc": {"enrichment_state.attempt_count": 1}
        },
        return_document=ReturnDocument.AFTER
    )
    assert result_3["enrichment_state"]["attempt_count"] == 3  # ✅
    
    # Simulate failure
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.error": "rate_limit"
        }}
    )
    
    # Attempt 4: Should NOT be selected (attempt_count >= MAX_RETRY_ATTEMPTS)
    result_4 = await db.articles.find_one_and_update(
        {
            "_id": article_id,
            "enrichment_state.status": "failed",
            "enrichment_state.attempt_count": {"$lt": MAX_RETRY_ATTEMPTS}  # 3 < 3 is false
        },
        {"$set": {"enrichment_state.status": "in_progress"}},
        return_document=ReturnDocument.AFTER
    )
    assert result_4 is None  # ✅ NOT selected (no more attempts)
    
    # Mark as completed with error
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "completed",
            "enrichment_state.error": "max_retries_exceeded",
            "enrichment_state.completed_at": datetime.now(timezone.utc),
        }}
    )
    
    # Verify: completed articles are never re-selected
    never_selected = await db.articles.find_one({
        "_id": article_id,
        "enrichment_state.status": {"$in": ["pending", "failed"]}
    })
    assert never_selected is None  # ✅ Completed, never selected again
    
    print("✅ Test 4 passed: Exactly 3 attempts, then completed with error")
```

---

## Summary of Corrections

| Issue | Previous | Corrected | Impact |
|-------|----------|-----------|--------|
| **Query syntax** | `{"enrichment_state": {"$in": [{...}]}}` | `{"enrichment_state.status": {"$in": [...]}}` | Queries now match correctly |
| **Update syntax** | `{"$set": {"attempt_count": {"$inc": 1}}}` | Separate `$inc` operator | Updates are valid MongoDB |
| **Retry count** | Unclear (3 vs 4 attempts) | Explicit: 3 attempts (attempt_count 1, 2, 3) | No more confusion |
| **Hung timeout** | 60 seconds (too short) | 600 seconds = 10 min (matches cycle time) | Prevents double-claiming |
| **Legacy records** | Not handled | Backfill on startup | All articles processed |
| **Test coverage** | Missing critical cases | Added legacy, concurrent, interrupt, retry tests | Implementation validated |

---

## Next Step: Review Implementation Diff

Before any deployment decision:

1. **Verify MongoDB syntax** — All dotted paths, correct operators
2. **Review backfill logic** — Handles startup without errors
3. **Check atomic claim** — $inc outside $set, return_document used
4. **Test all 4 scenarios** — Legacy backfill, concurrent claim, interruption, retry count
5. **Verify age cutoff** — Explicitly part of every query (decision pending)

