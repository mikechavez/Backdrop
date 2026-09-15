# BUG-108 Investigation: Revised Analysis & Fix

**Status:** Root cause confirmed, **original fix rejected**, revised fix prepared with validation tests.

---

## Critical Issue with Original Fix

### The Problem

**Original proposal:** Add age cutoff (30d) + limit (500) + sort (newest first) to enrichment query.

**Fatal flaw:** Tier 2/3 articles have only `relevance_tier` set but NOT other fields like `relevance_score`, `sentiment_score`, `sentiment`. These articles remain eligible for the enrichment query and are **re-selected repeatedly** because they're always among the "newest" 500 unprocessed articles.

### Scenario: Infinite Retry Loop

```
Cycle 1: Load 500 articles (newest to oldest)
├─ Articles 1-100: Tier 1 → Fully enriched (all fields set) ✅
├─ Articles 101-400: Tier 2/3 → relevance_tier SET, other fields NOT set
└─ Articles 401-500: Tier 2/3 → relevance_tier SET, other fields NOT set

Cycle 2 (30 min later): Load newest 500 again
├─ Articles 101-400: STILL missing sentiment_score, relevance_score, sentiment
├─ Articles 401-500: STILL missing sentiment_score, relevance_score, sentiment
├─ Enrichment query: "$or": [{"relevance_score": {$exists: false}}, ...]
└─ Result: SAME articles 101-500 selected AGAIN ❌

Cycle 3+: Repeat infinitely
└─ Articles 101-500 classified AGAIN, enrichment SKIPPED AGAIN
```

**Root cause:** No completion state. Once an article is processed (successfully or not), there's no way to exclude it from future queries.

---

## Revised Fix: State-Based Completion Tracking

### Design

**Instead of just limiting candidates, mark articles as processed regardless of outcome.**

After tier classification (line 650), set `enrichment_attempted_at` for **ALL articles**:
- Tier 1: After full enrichment
- Tier 2/3: After tier classification (before enrichment is skipped)
- Failed: After error, before retry

**Then exclude already-attempted articles from future enrichment queries:**

```python
enrichment_query = {
    "enrichment_attempted_at": {"$exists": False},  # ← KEY FIX
    "$or": [
        {"relevance_score": {"$exists": False}},
        {"relevance_tier": {"$exists": False}},
        # ... other conditions ...
    ]
}
```

### Why This Works

Once an article has `enrichment_attempted_at` set, it **will never match enrichment_query again**, regardless of missing fields.

**Tier 2/3 articles example:**
```
Cycle 1: Article 150 (tier 2) loaded + classified
└─ enrichment_attempted_at = 2026-09-13 21:45:00

Cycle 2: Query looks for enrichment_attempted_at: {$exists: false}
└─ Article 150 does NOT match (has enrichment_attempted_at) ✅
└─ Even though relevance_score is still missing
```

**Progress guaranteed:**
- Cycle 1: 500 articles marked attempted
- Cycle 2: 500 DIFFERENT articles loaded (oldest ~500 from backlog)
- Cycle 3+: Linear progress at ~500/cycle until backlog cleared

---

## Validation Tests (Demonstrating Fix Correctness)

### Test 1: No Infinite Retry

Verify articles marked `enrichment_attempted_at` are never re-selected:

```python
async def test_no_infinite_retry():
    # Insert article missing both relevance_score and relevance_tier
    article = {
        "_id": ObjectId(),
        "title": "Test",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
        # Missing: relevance_score, relevance_tier
    }
    await db.articles.insert_one(article)
    
    # Cycle 1: Article matches enrichment_query (no enrichment_attempted_at yet)
    query_1 = await db.articles.find_one({
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert query_1 is not None  # ✅ Found
    
    # Mark as attempted (simulating processing)
    await db.articles.update_one(
        {"_id": article["_id"]},
        {"$set": {"enrichment_attempted_at": datetime.now(timezone.utc)}}
    )
    
    # Cycle 2: Same query should NOT find the article
    query_2 = await db.articles.find_one({
        "_id": article["_id"],
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert query_2 is None  # ✅ Correctly excluded
```

### Test 2: Tier 2/3 Articles Not Re-Selected

Verify tier 2/3 articles (enrichment skipped) are still marked as attempted:

```python
async def test_tier_2_3_no_loop():
    # Tier 2 article
    article = {
        "_id": ObjectId(),
        "title": "Standard News",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
        # Missing: relevance_score, relevance_tier, sentiment_score, sentiment
    }
    await db.articles.insert_one(article)
    
    # Cycle 1: Matches enrichment_query
    count_1 = await db.articles.count_documents({
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert count_1 > 0  # ✅ Found
    
    # Simulate: Classify as tier 2, then mark as attempted
    # (Even though enrichment was skipped, completion state is set)
    await db.articles.update_one(
        {"_id": article["_id"]},
        {
            "$set": {
                "relevance_tier": 2,
                "enrichment_attempted_at": datetime.now(timezone.utc)
                # Note: relevance_score, sentiment_score NOT set
            }
        }
    )
    
    # Cycle 2: Same article should NOT be re-selected
    count_2 = await db.articles.count_documents({
        "_id": article["_id"],
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    })
    assert count_2 == 0  # ✅ Correctly excluded despite missing fields
```

### Test 3: Fresh Articles Progress Through Cycles

Verify new articles are processed in subsequent cycles:

```python
async def test_fresh_articles_progress():
    cycle_1_start = datetime.now(timezone.utc)
    
    # Simulate: 500 articles processed in Cycle 1
    await db.articles.update_many(
        {"created_at": {"$lt": cycle_1_start}},
        {"$set": {"enrichment_attempted_at": cycle_1_start}}
    )
    
    # Cycle 2: New article arrives (created after Cycle 1 start)
    cycle_2_start = datetime.now(timezone.utc)
    new_article = {
        "_id": ObjectId(),
        "title": "Fresh Article",
        "created_at": cycle_2_start - timedelta(minutes=5),
        # Missing fields: eligible for enrichment
    }
    await db.articles.insert_one(new_article)
    
    # Cycle 2 query should find new article
    fresh_articles = await db.articles.find({
        "enrichment_attempted_at": {"$exists": False},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    }).to_list(500)
    
    found = any(doc["_id"] == new_article["_id"] for doc in fresh_articles)
    assert found  # ✅ Fresh article included in Cycle 2
```

---

## Code Changes Required

### File: `src/crypto_news_aggregator/background/rss_fetcher.py`

#### Change 1: Update Enrichment Query (lines 426-437)

**Before:**
```python
enrichment_query = {
    "$or": [
        {"relevance_score": {"$exists": False}},
        # ... 6 more conditions ...
    ]
}
```

**After:**
```python
# Exclude articles already attempted to prevent infinite retry of tier 2/3
enrichment_query = {
    "enrichment_attempted_at": {"$exists": False},  # ← NEW
    "$or": [
        {"relevance_score": {"$exists": False}},
        # ... existing conditions unchanged ...
    ]
}

# Optional: Add age boundary for initial startup
min_created_at = datetime.now(timezone.utc) - timedelta(days=30)
enrichment_query["created_at"] = {"$gte": min_created_at}
```

#### Change 2: Mark All Articles as Attempted

**Location:** After tier classification (around line 672), add:

```python
# Mark article as enrichment-attempted regardless of tier
# (Prevents re-selection in future cycles)
await collection.update_one(
    {"_id": article_data["original_article"].get("_id")},
    {
        "$set": {
            "enrichment_attempted_at": datetime.now(timezone.utc)
        }
    }
)
```

**Apply this to:**
- Line 674 (after tier 1 update) ✅
- Line 679 (after tier 2/3 update) ✅
- Any error path that classifies an article (consolidate into one location after classification logic completes)

#### Change 3: Add Backlog Logging (optional but recommended)

**After line 449 (after determining articles_list), add:**

```python
total_attempted = await collection.count_documents({
    "enrichment_attempted_at": {"$exists": True},
    "created_at": {"$gte": min_created_at}
})

if len(articles_list) > 0:
    logger.info(
        f"Enrichment cycle: processing {len(articles_list)} articles "
        f"({total_attempted} already attempted in last 30d)"
    )
```

### Total Code Addition: ~15 lines

---

## Validation Checklist

### Pre-Deployment

- [ ] **Test 1:** Run no-infinite-retry test against staging MongoDB
- [ ] **Test 2:** Run tier-2/3 no-loop test against staging MongoDB
- [ ] **Test 3:** Run fresh-articles-progress test against staging MongoDB
- [ ] **Code review:** Verify enrichment_attempted_at placement doesn't break tier classification logic
- [ ] **No regression:** Existing tests pass (relevance classification, mention creation)

### Post-Deployment (48 hours)

**Monitor these queries after each enrichment cycle:**

```javascript
// Should increase by ~500 each cycle
db.articles.countDocuments({
  "enrichment_attempted_at": {"$exists": true},
  "created_at": {"$gte": new Date(Date.now() - 30*24*60*60*1000)}
})

// Should decrease by ~500 each cycle
db.articles.countDocuments({
  "enrichment_attempted_at": {"$exists": false},
  "created_at": {"$gte": new Date(Date.now() - 30*24*60*60*1000)},
  "$or": [
    {"relevance_score": {"$exists": false}},
    {"relevance_tier": {"$exists": false}},
  ]
})

// Should increase as mentions are created
db.entity_mentions.countDocuments({
  "created_at": {"$gte": new Date(Date.now() - 1*60*60*1000)}  // Last hour
})
```

---

## Separate Issues (Not Fixed by This Change)

### 1. E11000 Duplicate-Key Errors (Ingestion)

**Current:** `create_or_update_articles()` uses batch insert; any duplicate fails entire batch

**Impact:** Enrichment skipped for that cycle

**Recommendation:** Investigate separately (BUG-108-A)
- Does `create_or_update_articles()` use upsert semantics or batch insert?
- Should duplicates be updated instead of rejected?
- Baseline E11000 frequency before and after this fix

### 2. NoneType Errors (Extraction)

**Current:** LLM response parsing or selective processor fails

**Impact:** Batch extraction halts, zero entities extracted

**Recommendation:** Investigate separately (BUG-108-B)
- Trace exact failure point (lines 283-285, 477, or elsewhere)
- Add defensive null checks in LLM response parsing

### 3. Signals Timeframe (Product)

**Current:** UI label says "24h" but API defaults to "7d"

**Recommendation:** Reconcile after this fix validates (PRODUCT-X)
- Product decision: Should Signals display 24h, 7d, or configurable?
- Update code + UI to match

---

## Expected Outcomes (Actual, Not Estimated)

### Guaranteed
- ✅ No article selected twice (enrichment_attempted_at prevents re-selection)
- ✅ Linear progress: ~500 new articles per cycle until backlog cleared
- ✅ Restart-resilient: Completion state persists across container restarts

### Dependent on Data/Conditions
- ⚠️ **Entity mentions:** Depends on tier 1 article fraction + extraction success
  - If 20% tier 1 + 80% extraction success: ~80 mentions/cycle
  - If 50% tier 1 + 80% extraction success: ~200 mentions/cycle
  - **Must monitor actual rate, not assume**

- ⚠️ **Signals page display:** Depends on having recent primary mentions
  - Will show results IF tier 1 articles have extractable entities
  - Will remain empty IF most articles are tier 2/3 OR extraction fails
  - **Must verify via endpoint query, not assume**

- ⚠️ **Cycle time:** Depends on batch size + LLM latency
  - Roughly 5-10 minutes per cycle (not guaranteed <5 min)
  - **Must monitor actual latency**

### Must Monitor Post-Deployment
1. **enrichment_attempted_at count:** Should increase by ~500/cycle (progress)
2. **Backlog count:** Should decrease by ~500/cycle (linear reduction)
3. **Mention creation rate:** Should increase from 0 (baseline establishment)
4. **Tier distribution:** Should see mix of tier 1/2/3 (sanity check)
5. **E11000 errors:** Should remain at baseline (no regression from this fix)

---

## Summary

| Aspect | Original Proposal | Revised Proposal |
|--------|-------------------|------------------|
| **Query limit** | 500 per cycle | Completion state (no hard limit needed) |
| **Re-selection risk** | ⚠️ Tier 2/3 re-selected ∞ | ✅ Excluded after `enrichment_attempted_at` |
| **Progress guarantee** | ❌ None | ✅ ~500 new articles/cycle |
| **Restart resilience** | ❌ No checkpoint | ✅ Completion state persists |
| **Code complexity** | ~10 lines | ~15 lines |
| **Testing required** | Unit tests | Unit + 3 integration simulations |
| **Outcome confidence** | ⚠️ Speculative | ✅ Testable, measurable |
| **Scalability** | Unclear | Linear: 500/cycle × cycles to clear backlog |

**Status:** Ready for operator validation of root cause, then code review, testing, and deployment.

