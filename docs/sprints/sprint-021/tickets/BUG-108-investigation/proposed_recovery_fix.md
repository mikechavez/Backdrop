# BUG-108 Proposed Recovery Fix: Bounded Enrichment Pipeline

## Overview

The Signals page shows "No signals" because the entity enrichment pipeline hits an unbounded backlog of 13,496+ unenriched articles, which causes:

1. **Memory pressure** during processing
2. **Restart loops** if the process crashes mid-run
3. **Repeated batch re-processing** after each restart (no progress tracking)
4. **Missing entity mentions** if enrichment fails (E11000, NoneType, or timeout errors)

This fix bounds the enrichment pipeline to process fresh articles first, with optional historical backfill.

---

## Root Cause Summary

| Component | Issue | Evidence |
|-----------|-------|----------|
| **Backlog query** | No age cutoff, limit, or sort | `collection.find(enrichment_query).to_list(None)` loads ALL 13,496 articles |
| **Error handling** | E11000 duplicate skips entire enrichment cycle | If `create_or_update_articles()` fails, line 104 is not reached |
| **Tier classification** | Only tier 1 articles yield mentions | Tier 2-3 articles skip enrichment (lines 668-685) |
| **Progress tracking** | No checkpoint after enrichment | Restart causes full re-process of same backlog |

---

## Minimal Fix: Bounded Enrichment Query

### File: `src/crypto_news_aggregator/background/rss_fetcher.py`

**Location:** Lines 399-449 (function `process_new_articles_from_mongodb()`)

#### Change 1: Add Configuration Constants

At the top of the function, add:
```python
async def process_new_articles_from_mongodb():
    """Analyzes and enriches new articles from MongoDB that haven't been processed yet."""
    
    # Add these bounded-processing constants
    MAX_BACKLOG_PER_CYCLE = 500  # Process max 500 articles per 30-min cycle
    MAX_BACKLOG_AGE_DAYS = 30    # Don't enrich articles older than 30 days
```

#### Change 2: Replace Unbounded Query with Bounded Query

**Before (lines 426-443):**
```python
enrichment_query = {
    "$or": [
        {"relevance_score": {"$exists": False}},
        {"relevance_score": None},
        # ... other fields ...
    ]
}

articles_list = []
async for article in collection.find(enrichment_query):
    articles_list.append(article)  # ← UNBOUNDED: loads ALL matching articles
```

**After:**
```python
# Calculate age boundary for freshness prioritization
min_created_at = datetime.now(timezone.utc) - timedelta(days=MAX_BACKLOG_AGE_DAYS)

# Bounded enrichment query: age-filtered + limited
enrichment_query = {
    "created_at": {"$gte": min_created_at},  # Age cutoff
    "$or": [
        {"relevance_score": {"$exists": False}},
        {"relevance_score": None},
        # ... other fields unchanged ...
    ]
}

# Load bounded set, newest first (freshness priority)
articles_list = await collection.find(enrichment_query)\
    .sort("created_at", -1)\
    .limit(MAX_BACKLOG_PER_CYCLE)\
    .to_list(None)
```

#### Change 3: Add Backlog Logging

After logging "Processing X articles" (line 449), add:
```python
# Log backlog status for monitoring
total_backlog = await collection.count_documents(enrichment_query)
if total_backlog > MAX_BACKLOG_PER_CYCLE:
    logger.warning(
        f"⚠️  Enrichment backlog: {total_backlog} articles queued "
        f"(processing {len(articles_list)} this cycle, "
        f"next cycle in ~30min). Age window: <{MAX_BACKLOG_AGE_DAYS}d"
    )
```

---

## Validation Strategy

### Step 1: Pre-deployment Verification (Local or Staging)

**Goal:** Confirm the bounded query works and produces expected results.

**Test script:**
```python
import asyncio
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.db.mongodb import mongo_manager

async def validate_bounded_query():
    db = await mongo_manager.get_async_database()
    
    # Simulate the bounded query
    MAX_BACKLOG_PER_CYCLE = 500
    MAX_BACKLOG_AGE_DAYS = 30
    min_created_at = datetime.now(timezone.utc) - timedelta(days=MAX_BACKLOG_AGE_DAYS)
    
    enrichment_query = {
        "created_at": {"$gte": min_created_at},
        "$or": [
            {"relevance_score": {"$exists": False}},
            {"relevance_tier": {"$exists": False}},
        ]
    }
    
    # Count total backlog
    total_backlog = await db.articles.count_documents(enrichment_query)
    
    # Load bounded set
    bounded_articles = await db.articles.find(enrichment_query)\
        .sort("created_at", -1)\
        .limit(MAX_BACKLOG_PER_CYCLE)\
        .to_list(None)
    
    print(f"Total backlog (last 30d): {total_backlog}")
    print(f"Articles to process this cycle: {len(bounded_articles)}")
    print(f"Oldest article in this batch: {bounded_articles[-1]['created_at']}")
    print(f"Newest article in this batch: {bounded_articles[0]['created_at']}")
    
    # Verify age boundary
    for i, article in enumerate(bounded_articles):
        if article['created_at'] < min_created_at:
            print(f"❌ FAIL: Article {i} violates age boundary")
            return False
    
    print("✅ Bounded query validation passed")
    return True

# Run with: python -c "asyncio.run(validate_bounded_query())"
```

### Step 2: Post-deployment Monitoring (Production)

**Metrics to track:**

1. **Mention creation rate** (should increase immediately)
   - Before: 0 mentions/cycle (due to backlog restarting)
   - After: Should see mentions created within first cycle
   - Check: `entity_mentions.count_documents({"created_at": {$gte: <30min ago>}})`

2. **Backlog reduction** (should decrease over time)
   - Monitor: `articles.count_documents(enrichment_query)` per cycle
   - Should decrease by ~500 per cycle until cleared
   - Once <500, should reach equilibrium at ~0 (fresh articles only)

3. **Tier distribution** (sanity check)
   - Tier 1 (high signal): Should see some articles
   - Tier 2 (default): Majority
   - Tier 3 (low signal): Some filtered out
   - If all articles are tier 1 or all tier 3, tier classifier may be misconfigured

4. **Error rates** (regression check)
   - E11000 errors should continue at baseline (not increase)
   - NoneType errors should not increase (indicates new failures)
   - Extraction/enrichment success rate should remain stable

---

## Optional: Historical Backfill (Separate Scheduled Job)

If you have articles older than 30 days that should have been enriched, you can run a separate historical backfill.

**Do NOT implement this yet**—it requires explicit operator approval and cost budgeting.

### Design (for future consideration):

**File:** `src/crypto_news_aggregator/tasks/historical_backfill.py` (new file)

```python
@shared_task(name="historical_backfill_enrichment", bind=True)
def historical_backfill_enrichment(self, max_articles: int = 100):
    """
    One-time or periodic historical backfill for articles older than 30 days.
    
    Args:
        max_articles: Max articles to process in this run (cost cap)
    
    This task is separate from the main enrichment pipeline and must be
    explicitly triggered. It's designed to handle articles that should have
    been enriched before the bounded-pipeline fix was deployed.
    """
    # Implementation: Similar to process_new_articles_from_mongodb(),
    # but targets only articles where created_at < (now - 30d)
    # and has a cost cap (max_articles)
    pass
```

**Scheduling:** Not added to beat_schedule.py by default. Only runs via:
- Manual trigger: `celery -A tasks call historical_backfill_enrichment --args="[100]"`
- Or via admin API endpoint (requires operator approval)

---

## Acceptance Criteria

### Before Deployment

- [ ] Code review: Bounded query logic is correct (age cutoff, sort order, limit)
- [ ] Unit test: Mock MongoDB confirms query behavior
- [ ] Logs: New backlog warning message appears in test run
- [ ] No regressions: All existing tests pass

### Post-deployment (48 hours)

- [ ] **Signals page shows results** (within 1-2 enrichment cycles, ~1 hour)
- [ ] **Mention count increases** (check `entity_mentions` collection)
- [ ] **Backlog decreases** (monitor `articles` enrichment_query count)
- [ ] **Error rates stable** (E11000, NoneType unchanged from baseline)
- [ ] **Tier distribution reasonable** (mix of tier 1, 2, 3)
- [ ] **No OOM errors** (memory usage remains stable)

### Product Verification

- [ ] Product intent confirmed: Should Signals display 24h or 7d? (Reconcile UI label with API)
- [ ] Cache behavior verified (Redis hit rates, staleTime respected)
- [ ] Entity mention latency acceptable (<3s for fresh articles)

---

## Risk Assessment

### Low Risk

✅ **Bounded query** — Safe change, only affects what articles are loaded
✅ **Sort order** — Doesn't change business logic, just prioritizes freshness
✅ **Age cutoff** — 30 days matches product retention policy (from TASK-105)

### Medium Risk

⚠️  **Backlog logging** — New log line; could add noise if misconfigured
⚠️  **Partial processing** — Articles older than 30d will be skipped temporarily (need separate backfill)

### Mitigation

- Start with `MAX_BACKLOG_PER_CYCLE = 500` (conservative); can increase to 1000 if stable
- Set `MAX_BACKLOG_AGE_DAYS = 30` to match product signal retention window
- Monitor alerts for "⚠️  Enrichment backlog" warning (should only appear first few cycles)

---

## Deployment Steps (For Operator)

### Step 1: Apply Fix (Code Change)
1. Create feature branch: `fix/bug-108-bounded-enrichment`
2. Edit `src/crypto_news_aggregator/background/rss_fetcher.py`
   - Add constants (MAX_BACKLOG_PER_CYCLE, MAX_BACKLOG_AGE_DAYS)
   - Replace unbounded query with bounded query + sort + limit
   - Add backlog logging
3. Run tests: `pytest tests/background/test_rss_fetcher.py -v`
4. Create PR, get review, merge to main

### Step 2: Deploy to Production
1. Deploy new code to Railway (standard process)
2. Monitor logs for startup: Should see "Processing N articles with cost-optimized extraction"
3. Monitor for backlog warning: Should see ⚠️ message if backlog exists

### Step 3: Validate (48 hours post-deployment)
1. Check Signals page: Should show entities by 2026-09-14 00:00 UTC
2. Check entity_mentions count: Should increase significantly
3. Check enrichment backlog: Should decrease by ~500/cycle
4. Review tier distribution: Should see mix of tier 1/2/3

### Step 4: Document
1. Update CLAUDE.md or runbook with new constants and monitoring guidance
2. Optional: Schedule historical backfill task if operator approves

---

## Testing Checklist

**Unit Tests** (run locally before PR):
```bash
pytest tests/background/test_rss_fetcher.py::test_bounded_enrichment_query -v
pytest tests/background/test_rss_fetcher.py::test_backlog_logging -v
pytest tests/background/test_rss_fetcher.py -v
```

**Integration Test** (run locally with staging MongoDB):
```bash
# Start MongoDB
docker-compose -f docker-compose.yml up -d mongodb

# Run enrichment with bounded query
python -m pytest tests/background/test_rss_fetcher_enrichment.py -v -s

# Verify mentions were created
python -c "
import asyncio
from crypto_news_aggregator.db.mongodb import mongo_manager
async def check():
    db = await mongo_manager.get_async_database()
    count = await db.entity_mentions.count_documents({})
    print(f'Total mentions in DB: {count}')
asyncio.run(check())
"
```

**Smoke Test** (production, read-only):
```bash
# Hit the Signals endpoint and confirm results
curl https://api.context-owl.com/api/v1/signals/trending?limit=15&timeframe=7d

# Expected: Non-empty signals array with at least one entity
# If empty or timeout, investigate further
```

---

## Code Review Checklist

- [ ] Bounded query has age cutoff (min_created_at) and limit (MAX_BACKLOG_PER_CYCLE)
- [ ] Sort order is `-1` (newest first) for freshness priority
- [ ] Constants (MAX_BACKLOG_PER_CYCLE, MAX_BACKLOG_AGE_DAYS) are documented
- [ ] Backlog logging message is clear and actionable
- [ ] No removal of existing error handling (E11000, NoneType still logged)
- [ ] Existing mention creation logic unchanged (only the input query changes)
- [ ] No new dependencies or breaking changes

---

## Next Steps (After Deployment Validation)

1. **Investigate E11000 errors** (root cause from Part 3 of investigation)
   - Review `create_or_update_articles()` to ensure upsert semantics
   - Add handling for duplicate URLs (update instead of insert-only)

2. **Investigate NoneType errors** (root cause from Part 3 of investigation)
   - Trace 22:48 UTC logs to identify exact failure point
   - Add defensive null checks in LLM response parsing

3. **Reconcile Signals UI timeframe** (product intent decision)
   - Signals page label says "24h" but API defaults to "7d"
   - Decide: Should display 24h or 7d? Update code + UI to match

4. **Optional: Historical backfill** (after backlog reaches equilibrium)
   - Run one-time backfill for articles older than 30d if needed
   - Requires explicit cost budgeting and operator approval

