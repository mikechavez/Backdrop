# BUG-108 Revised Fix Proposal: State-Based Completion Tracking

**Issue with original proposal:** 500-article limit + newest-first sort causes articles to be re-selected indefinitely.

---

## Problem with Original Proposal

### Query Logic Flaw

**Current enrichment query (line 426-437):**
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
```

**Original proposal applied:**
```python
articles_list = await collection.find(enrichment_query)\
    .sort("created_at", -1)\
    .limit(500)\
    .to_list(None)
```

**The problem:**
- Tier 2/3 articles get `relevance_tier` set (line 672) but NOT other fields like `relevance_score`, `sentiment_score`, `sentiment`
- These tier 2/3 articles remain in the enrichment_query because fields are still missing
- Next cycle: Same tier 2/3 articles are still in newest 500, selected again
- Result: **Infinite loop re-selecting same tier 2/3 articles**

**Scenario:**
1. Cycle 1: Load 500 articles (newest to oldest)
   - Batch 1-100: Tier 1 → Fully enriched (all fields set)
   - Batch 101-400: Tier 2/3 → Tier assigned, but other fields NOT set
   - Batch 401-500: Tier 2/3 → Tier assigned, but other fields NOT set

2. Cycle 2 (30 min later): Load newest 500 again
   - Batch 101-400 (tier 2/3): STILL missing sentiment_score, relevance_score, sentiment
   - STILL in enrichment_query
   - SELECTED AGAIN as "newest" unprocessed articles
   - Tier classification runs AGAIN on same articles
   - Still no enrichment (tier 2/3 skipped per line 668)

3. Cycle 3+: Same articles selected repeatedly → **Infinite retry loop**

---

## Root Cause: No Completion State

The code has **no mechanism to mark articles as "processed"** or "skip-eligible":

- Tier 1 articles: Fully enriched (relevance_score, sentiment_score, sentiment, themes, entities all set)
- Tier 2/3 articles: Only relevance_tier set; other fields remain missing
- Failed articles: No fields set; same error likely recurs next cycle
- Enrichment query: Still matches them all next cycle

**Result:** No progress across restarts; same candidates selected repeatedly.

---

## Revised Fix: State-Based Completion Tracking

### Design Principle

**Instead of limiting candidates, mark them as processed:**

1. After tier classification (regardless of tier): Set an `enrichment_attempted` flag or `enrichment_completed_at` timestamp
2. Exclude already-attempted articles from future queries
3. Bound by age (30d) for initial startup only; then rely on completion state for steady-state

### Implementation

#### Change 1: Add Completion State Flag

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`

After tier classification (line 674), add:
```python
# Mark article as enrichment-attempted (prevents infinite retry)
await collection.update_one(
    {"_id": article_data["original_article"].get("_id")},
    {
        "$set": {
            "enrichment_attempted_at": datetime.now(timezone.utc)
        }
    }
)
```

This applies to **ALL articles** (tier 1, 2, 3, and failed) after they're processed once.

#### Change 2: Update Enrichment Query

**File:** Same location (lines 426-437)

```python
# Exclude articles already attempted (prevents re-selection on restart)
enrichment_query = {
    "enrichment_attempted_at": {"$exists": False},  # ← NOT attempted yet
    "$or": [
        {"relevance_score": {"$exists": False}},
        {"relevance_tier": {"$exists": False}},
        # ... keep other field conditions ...
    ]
}
```

**Optional: Age boundary for initial startup only**
```python
# On first run: Only consider articles from last 30 days
# Protects against old backlog consuming all cycles
min_created_at = datetime.now(timezone.utc) - timedelta(days=30)
enrichment_query["created_at"] = {"$gte": min_created_at}

# After first cycle: Once backlog is bounded, query drops age boundary
# (steady-state processes fresh articles as they arrive, oldest attempted articles already excluded)
```

#### Change 3: Bound Initial Backlog Processing

On startup, process in bounded batches:

```python
MAX_BACKLOG_PER_CYCLE = 500  # Process max 500 candidates per cycle

articles_list = await collection.find(enrichment_query)\
    .sort("created_at", -1)\
    .limit(MAX_BACKLOG_PER_CYCLE)\
    .to_list(None)
```

After `enrichment_attempted_at` is set, the `enrichment_query` naturally excludes those articles, so limit of 500 becomes the rate of **progress** (500 new articles per cycle), not re-processing.

---

## Query Simulation: Demonstrating Progress

### Scenario: Verify Articles Don't Get Re-Selected

**Before fix is deployed:**

Cycle 1 query (unbounded):
```javascript
db.articles.countDocuments({
  "$or": [
    {"relevance_score": {"$exists": false}},
    {"relevance_tier": {"$exists": false}},
  ]
})
// Result: 13,496 (all candidates)

db.articles.find({
  "$or": [
    {"relevance_score": {"$exists": false}},
    {"relevance_tier": {"$exists": false}},
  ]
}).sort({created_at: -1}).limit(5).project({_id: 1, created_at: 1, relevance_tier: 1, relevance_score: 1}).toArray()
// Result: 5 newest articles, all missing either field
```

**After fix is deployed and Cycle 1 completes:**

All 500 processed articles now have `enrichment_attempted_at` set:
```javascript
db.articles.countDocuments({
  "enrichment_attempted_at": {"$exists": true}
})
// Result: 500 (cycle 1 processed)

db.articles.countDocuments({
  "enrichment_attempted_at": {"$exists": false},
  "created_at": {"$gte": new Date(Date.now() - 30*24*60*60*1000)},
  "$or": [
    {"relevance_score": {"$exists": false}},
    {"relevance_tier": {"$exists": false}},
  ]
})
// Result: 12,996 (13,496 - 500 completed = new candidates eligible for Cycle 2)
```

**Cycle 2 query:**
```javascript
db.articles.find({
  "enrichment_attempted_at": {"$exists": false},  // ← KEY: Excludes cycle 1
  "created_at": {"$gte": new Date(Date.now() - 30*24*60*60*1000)},
  "$or": [
    {"relevance_score": {"$exists": false}},
    {"relevance_tier": {"$exists": false}},
  ]
}).sort({created_at: -1}).limit(5).project({_id: 1, created_at: 1, enrichment_attempted_at: 1}).toArray()
// Result: 5 DIFFERENT (older) articles, none with enrichment_attempted_at
// Cycle 1 articles are NOT re-selected ✅
```

**Key property:** Once an article has `enrichment_attempted_at` set, it will **never match the enrichment_query again**, regardless of missing fields.

---

## Test Simulation: Verify Bounded Progress

### Test 1: Same Article NOT Selected Twice

```python
async def test_no_infinite_retry():
    """Verify articles marked enrichment_attempted are excluded from future queries."""
    
    db = await mongo_manager.get_async_database()
    
    # Insert test articles
    test_article = {
        "_id": ObjectId(),
        "title": "Test Article",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "source": "test",
        # Missing relevance_score and relevance_tier (eligible for enrichment)
    }
    await db.articles.insert_one(test_article)
    
    # Simulate Cycle 1: Query finds the article
    query_cycle_1 = await db.articles.find_one({
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert query_cycle_1 is not None, "Article should be eligible in Cycle 1"
    assert query_cycle_1["_id"] == test_article["_id"]
    
    # Mark as enrichment_attempted (as code would do after classification)
    await db.articles.update_one(
        {"_id": test_article["_id"]},
        {"$set": {"enrichment_attempted_at": datetime.now(timezone.utc)}}
    )
    
    # Simulate Cycle 2: Query should NOT find the same article
    query_cycle_2 = await db.articles.find_one({
        "_id": test_article["_id"],
        "enrichment_attempted_at": {"$exists": False},  # ← Should fail now
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert query_cycle_2 is None, "Article should NOT be eligible in Cycle 2 after enrichment_attempted is set"
    
    print("✅ Test passed: Articles marked enrichment_attempted are excluded from future cycles")
```

### Test 2: Tier 2/3 Articles DON'T Create Infinite Loop

```python
async def test_tier_2_3_no_retry_loop():
    """Verify tier 2/3 articles (enrichment skipped) are still marked as attempted."""
    
    db = await mongo_manager.get_async_database()
    
    # Insert tier 2 article (missing multiple fields)
    tier_2_article = {
        "_id": ObjectId(),
        "title": "Standard Crypto News",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
        "source": "test",
        # No relevance_score, relevance_tier, sentiment_score, sentiment
    }
    await db.articles.insert_one(tier_2_article)
    
    # Cycle 1: Article matches enrichment_query
    count_cycle_1 = await db.articles.count_documents({
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert count_cycle_1 > 0, "Tier 2 article should be in enrichment_query"
    
    # Code path: Classifier runs, determines tier 2
    # Tier 2 enrichment is SKIPPED (line 668-685)
    # BUT enrichment_attempted_at is STILL SET (after classification)
    await db.articles.update_one(
        {"_id": tier_2_article["_id"]},
        {
            "$set": {
                "relevance_tier": 2,
                "enrichment_attempted_at": datetime.now(timezone.utc)
                # Note: relevance_score, sentiment_score NOT set (skipped for tier 2)
            }
        }
    )
    
    # Cycle 2: Same tier 2 article should NOT be re-selected
    # even though relevance_score is still missing
    count_cycle_2 = await db.articles.count_documents({
        "_id": tier_2_article["_id"],
        "enrichment_attempted_at": {"$exists": False},  # ← This check excludes it
        "$or": [
            {"relevance_score": {"$exists": False}},  # ← This is still true, but...
            {"relevance_tier": {"$exists": False}},   # ← ...this is now false
        ]
    })
    assert count_cycle_2 == 0, "Tier 2 article should NOT be re-selected even though some fields missing"
    
    print("✅ Test passed: Tier 2/3 articles marked as attempted, no infinite retry")
```

### Test 3: Fresh Articles Progress Through Cycles

```python
async def test_fresh_articles_progress():
    """Verify new articles (created after cycle started) are processed in later cycles."""
    
    db = await mongo_manager.get_async_database()
    
    # Cycle 1: Process 500 articles (all from before "now")
    cycle_1_start = datetime.now(timezone.utc)
    
    # Simulate: 500 articles processed
    await db.articles.update_many(
        {"created_at": {"$lt": cycle_1_start}},
        {"$set": {"enrichment_attempted_at": cycle_1_start}}
    )
    
    # Cycle 2 (30 min later): New articles ingested after Cycle 1 started
    cycle_2_start = datetime.now(timezone.utc)
    
    new_article = {
        "_id": ObjectId(),
        "title": "Fresh Article",
        "created_at": cycle_2_start - timedelta(minutes=5),  # After cycle 1 start
        "source": "test",
    }
    await db.articles.insert_one(new_article)
    
    # Cycle 2 query should find new article
    fresh_articles = await db.articles.find({
        "enrichment_attempted_at": {"$exists": False},
        "created_at": {"$lt": cycle_2_start},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    }).to_list(500)
    
    article_ids = [doc["_id"] for doc in fresh_articles]
    assert new_article["_id"] in article_ids, "Fresh article should be in Cycle 2 query"
    
    print("✅ Test passed: Fresh articles progress through cycles as expected")
```

---

## Revised Implementation Checklist

### Pre-Deployment Verification

- [ ] **Query simulation:** Run the 3 test scenarios above against staging MongoDB
- [ ] **No infinite loop:** Verify articles marked `enrichment_attempted_at` are never re-selected
- [ ] **Tier 2/3 handling:** Confirm tier 2/3 articles marked as attempted even though enrichment skipped
- [ ] **Fresh articles:** Confirm new articles ingested after cycle start are processed in next cycle

### Code Changes

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`

- [ ] Add `enrichment_attempted_at` field SET after tier classification (apply to ALL articles regardless of tier)
- [ ] Update enrichment query to exclude articles with `enrichment_attempted_at` already set
- [ ] Optional: Add age boundary (30d) for initial startup protection
- [ ] Add logging: Count of attempted vs. new candidates per cycle

### Validation Post-Deployment

- [ ] **Cycle 1 (30 min):** 500 articles processed, all get `enrichment_attempted_at` set
- [ ] **Cycle 2 (60 min):** New 500 articles selected (different set), backlog decreases by 500
- [ ] **Cycle N:** Progress continues at ~500/cycle until backlog cleared
- [ ] **No re-selection:** Run this query and verify count stays constant or decreases, never increases:
  ```javascript
  db.articles.countDocuments({
    "enrichment_attempted_at": {"$exists": true}
  })
  ```
- [ ] **Mentions increasing:** Entity mention count per cycle increases (was 0, now >0)

---

## Separate Issue: E11000 Duplicate Errors

**Not fixed by this proposal.** This is a separate ingestion error that should be investigated independently:

**Current behavior:**
- Line 101: `await create_or_update_articles(articles)` uses batch insert
- If any URL duplicate exists, entire batch fails
- Line 104 not reached → Enrichment skipped for that cycle

**Investigation needed:**
1. Is `create_or_update_articles()` using `insert_many()` (all-or-nothing) or upsert semantics?
2. How often do E11000 errors occur? (Baseline before fix)
3. Should duplicates be updated instead of rejected?

**Recommended separate ticket:** BUG-108-A: Fix E11000 duplicate-key handling in ingestion pipeline

---

## Expected Outcomes (After Fix + 48 Hours)

### Bounded by Article Completeness, Not Fixed Estimates

- **Entity mentions created:** Depends on tier 1 article count and successful extraction
  - If 20% of articles are tier 1: 500/cycle × 20% × 80% success = ~80 mentions/cycle
  - If 50% tier 1: ~200 mentions/cycle
  - Actual number will vary with content and errors; monitor to establish baseline
  
- **Signals page results:** Will show IF:
  - Recent primary mentions exist (depends on tier distribution and extraction success)
  - Tier 1 articles have extractable entities
  - Signals endpoint has non-empty results for current timeframe
  - Should verify via endpoint query, not assumed

- **Enrichment cycle time:** Depends on batch size and LLM latency
  - Tier 1 enrichment: 10 articles × 5s per batch = ~50s
  - Tier 2/3 classification: 500 articles × 0.1s = ~50s
  - Total: ~5-10 minutes per cycle (not guaranteed <5 min)

- **Backlog reduction:** Predictable
  - Cycle 1: 13,496 → 12,996 (500 marked attempted)
  - Cycle 2: 12,996 → 12,496
  - Linear decrease at 500/cycle until cleared (~27 cycles = ~13.5 hours to clear backlog)

### Monitoring Requirements

**Must track to validate fix, not estimate:**
1. **Mention count per cycle:** Query DB after each enrichment cycle
2. **Article tiers distribution:** How many tier 1 vs tier 2/3?
3. **Extraction success rate:** How many articles yield entities?
4. **`enrichment_attempted_at` growth:** Should increase by 500/cycle
5. **Backlog reduction:** Should decrease by 500/cycle
6. **E11000 error frequency:** Baseline before and after (separate concern)

---

## Summary of Changes

| Aspect | Original Proposal | Revised Proposal |
|--------|-------------------|------------------|
| **Query limit** | 500 per cycle | Remove; rely on completion state |
| **Completion state** | None | Add `enrichment_attempted_at` flag |
| **Re-selection risk** | ⚠️ Tier 2/3 re-selected forever | ✅ Excluded after one attempt |
| **Progress guarantee** | ❌ No | ✅ Yes: 500 new articles/cycle |
| **Restart resilience** | ❌ No checkpoint | ✅ Yes: Completion state persists |
| **Code complexity** | ~10 lines | ~15 lines |
| **Testing required** | Unit tests | Unit + integration simulation tests |
| **E11000 handling** | Not addressed | Separate ticket |

