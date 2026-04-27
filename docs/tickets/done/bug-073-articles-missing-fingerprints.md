---
id: BUG-073
type: bug
status: open
priority: high
severity: high
created: 2026-04-14
updated: 2026-04-14
---

# Articles Missing Fingerprints — Deduplication Broken

## Problem

Articles ingested via RSS feeds are being saved to MongoDB with `fingerprint: null`, breaking the deduplication system. This allows duplicate articles across feeds to be stored multiple times, wasting storage and LLM processing quota on enrichment of identical content.

**Impact:** 
- Deduplication layer completely non-functional
- Same article from multiple feeds = multiple database records
- All narrative enrichment runs on duplicates (cost waste)
- April 14 ingestion shows: 5 articles with `fingerprint: null` (100% of inserts)

## Expected Behavior

All articles inserted into MongoDB should have a valid fingerprint (MD5 hash of normalized title + content). Fingerprints enable:
1. Duplicate detection across feeds
2. Prevention of re-processing identical content
3. Cost control on LLM enrichment

## Actual Behavior

Articles are inserted with `fingerprint: null`, indicating:
```javascript
db.articles.find({
  created_at: { $gte: new Date("2026-04-14T00:00:00Z") },
  fingerprint: { $ne: null, $exists: true }
}).count()
// Returns: 0
```

All 5 articles on April 14 lack fingerprints. Last fingerprinted articles: April 9.

## Steps to Reproduce

1. Trigger RSS feed fetch (happens every 3 hours via Celery Beat)
2. Wait for articles to be inserted into MongoDB
3. Query MongoDB: `db.articles.findOne({created_at: {$gte: new Date("2026-04-14T00:00:00Z")}})`
4. Observe: `fingerprint: null`

## Environment

- **Environment:** production (Railway)
- **Affected component:** RSS ingestion pipeline
- **User impact:** high — deduplication completely broken
- **First observed:** April 14, 2026 (~2 AM UTC)
- **Scope:** All articles ingested after last fingerprinted articles (April 9)

## Logs/Evidence

**MongoDB aggregation (April 13–14 timeline):**
```
{ _id: '2026-04-14 03:00', count: 2 },  ← All have fingerprint: null
{ _id: '2026-04-14 02:00', count: 2 },
{ _id: '2026-04-14 01:00', count: 2 },
{ _id: '2026-04-14 00:00', count: 3 },
{ _id: '2026-04-13 23:00', count: 3 },
...
```

**Duplicate fingerprints query:**
```javascript
db.articles.aggregate([
  { $match: { created_at: { $gte: new Date("2026-04-14T00:00:00Z") } } },
  { $group: { _id: "$fingerprint", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }
])
// Returns: [{ _id: null, count: 9, sources: [...] }]
// ↑ All duplicates have null fingerprint
```

---

## Resolution

**Status:** ✅ FIXED - Ready for PR  
**Fixed:** 2026-04-13  
**Branch:** `fix/bug-073-fingerprint-generation`  
**Commit:** pending (staged, ready to commit)

### Root Cause

`src/crypto_news_aggregator/db/operations/articles.py:34` inserts articles **directly into MongoDB without calling `ArticleService.create_article()`**, which is the only code path that generates fingerprints.

**Current flow (broken):**
```
RSS Fetcher → create_or_update_articles() → collection.insert_one() ❌ NO FINGERPRINT
```

**Should be:**
```
RSS Fetcher → create_or_update_articles() → ArticleService.create_article() ✅ GENERATES FINGERPRINT
```

The `ArticleService.create_article()` method (line 165–168 of `services/article_service.py`) properly:
1. Generates fingerprint via `_generate_fingerprint(title, content)`
2. Checks for duplicates via `_is_duplicate()`
3. Only inserts if not a duplicate
4. Stores fingerprint before insertion

### Changes Made

**File:** `src/crypto_news_aggregator/db/operations/articles.py`

**Before:**
```python
from typing import List
from datetime import datetime, timezone
from crypto_news_aggregator.models.article import ArticleCreate, ArticleInDB
from crypto_news_aggregator.db.mongodb import mongo_manager


async def create_or_update_articles(articles: List[ArticleCreate]):
    """Creates new articles or updates existing ones in the database."""
    db = await mongo_manager.get_async_database()
    collection = db.articles

    for article in articles:
        # Ensure URL is a string before database operations
        if hasattr(article, "url") and not isinstance(article.url, str):
            article.url = str(article.url)
        existing_article = await collection.find_one({"source_id": article.source_id})
        if existing_article:
            # Update metrics if the article already exists
            await collection.update_one(
                {"_id": existing_article["_id"]},
                {"$set": {"metrics": article.metrics.model_dump()}},
            )
        else:
            # Insert new article
            # Prepare article data for database insertion
            article_data = article.model_dump()
            # Add required fields for database storage
            article_data.update(
                {
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            await collection.insert_one(article_data)
```

**After:**
```python
from typing import List
from datetime import datetime, timezone
from crypto_news_aggregator.models.article import ArticleCreate, ArticleInDB
from crypto_news_aggregator.services.article_service import get_article_service


async def create_or_update_articles(articles: List[ArticleCreate]):
    """Creates new articles or updates existing ones in the database."""
    article_service = get_article_service()

    for article in articles:
        # Ensure URL is a string before database operations
        if hasattr(article, "url") and not isinstance(article.url, str):
            article.url = str(article.url)

        # Prepare article data for database insertion
        article_data = article.model_dump()
        article_data.update(
            {
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

        # Use ArticleService for proper fingerprinting and deduplication
        # This will:
        # 1. Generate fingerprint (MD5 hash of normalized title + content)
        # 2. Check for duplicates by fingerprint
        # 3. Only insert if not a duplicate
        # 4. Update duplicate metadata if duplicate exists
        result = await article_service.create_article(article_data)

        if result:
            # Article was created successfully
            pass
        else:
            # Article was a duplicate — no-op
            pass
```

**Key changes:**
- Replaced `mongo_manager.get_async_database()` → `get_article_service()`
- Removed direct `collection.insert_one()` call
- All article creation now flows through `ArticleService.create_article()`
- Deduplication by fingerprint is now enabled for ALL articles
- Duplicate metadata updates still work (via `_update_duplicate_metadata()`)

### Testing

**Pre-deployment verification:**
1. Deploy fix to staging
2. Run 1 fetch cycle manually
3. Query new articles: `db.articles.find({created_at: {$gte: new Date("2026-04-14T05:00:00Z")}}).limit(1)`
4. Verify: `fingerprint` field is NOT null (should be 32-character hex string)

**Post-deployment verification:**
1. Monitor articles inserted in first 3 hours
2. Run fingerprint count: `db.articles.find({fingerprint: null, created_at: {$gte: new Date()}}).count()` → should return **0**
3. Run duplicate check: `db.articles.aggregate([{$match: {fingerprint: {$ne: null}}}, {$group: {_id: "$fingerprint", count: {$sum: 1}}}, {$match: {count: {$gt: 1}}}])` → should return **0 results** (no duplicates)
4. Verify narrative enrichment only runs on tier-1 articles (from BUG-070)

**Metrics to monitor (first 24h post-fix):**
- Articles ingested per hour (should return to 50+/hour, not 2-3)
- Fingerprint null count (should be 0)
- Duplicate rejection rate (track via logs)
- LLM traces for `narrative_generate` (should only see tier-1 articles)

### Files Changed

- `src/crypto_news_aggregator/db/operations/articles.py` — Use ArticleService instead of direct MongoDB insert

### Related Issues

- **BUG-070:** `MAX_RELEVANCE_TIER = 1` (filters to tier-1 only for narrative enrichment)
- **BUG-071:** Compressed `NARRATIVE_SYSTEM_PROMPT` (reduces token count)
- **BUG-072:** LLM cache wiring (enables cache hit detection)

These three fixes are ineffective if articles lack fingerprints, as deduplication prevents cost savings from being realized.

---

## Deployment Notes

- **Requires restart:** Yes (new import)
- **Database migration:** No (adds fingerprints going forward; doesn't retroactively fix April 14 articles)
- **Backward compatibility:** Yes (ArticleService handles null fingerprints gracefully)
- **Rollback plan:** Revert to previous version; articles inserted before fix remain without fingerprints until manually regenerated