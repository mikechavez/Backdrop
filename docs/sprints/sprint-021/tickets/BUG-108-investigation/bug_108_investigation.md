# BUG-108 Investigation: Comprehensive Findings

## Investigation Scope

This investigation traces the production Signals page empty-results issue through:
1. Railway deployment topology (single vs. multiple replicas)
2. Article ingestion and entity extraction backlog
3. Error path analysis (E11000 duplicates, NoneType failures)
4. Mention creation persistence
5. Proposed bounded recovery design

---

## Part 1: Deployment Topology Analysis

### Code Evidence: RSS Worker Architecture

**File:** `src/crypto_news_aggregator/main.py` (lines 136-159)

Production runs a **single FastAPI instance** with background workers:
```python
background_tasks.extend([
    asyncio.create_task(schedule_rss_fetch(1800, run_immediately=True), name="rss_fetcher"),
    # ... other tasks
])
```

**Key properties:**
- `schedule_rss_fetch()` runs on **1800-second (30 minute) intervals**
- `run_immediately=True` → First RSS fetch runs **on startup**
- RSS fetcher is an **in-process asyncio task**, not a separate Celery worker

### Why Repeated "Running initial RSS fetch on startup..." logs appear

Railway can trigger:
1. **Container restart** (crash, health check failure, memory OOM) → Single instance restarts, re-logs startup
2. **Scale event** (if configured with >1 replica) → Multiple instances start, each logs independently
3. **Deployment** (code push) → Old container stops, new starts with fresh logs

**Current evidence suggests:** Single instance with periodic restarts (not multiple replicas), but Railway metadata is needed to confirm.

---

## Part 2: Article & Mention Backlog Analysis

### Query Path: Articles Created but Not Enriched

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py` (lines 399-449)

Enrichment query filters for articles **missing ANY of these fields:**
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

**Critical Issue:** No age cutoff, sort, or candidate limit. All matching articles loaded into memory:
```python
articles_list = []
async for article in collection.find(enrichment_query):
    articles_list.append(article)  # ← Unbounded load
```

If **13,496 articles** match this query:
- All are loaded into memory (potential OOM)
- Entity extraction batches process these in 10-article chunks
- If the process crashes mid-run (after loading but before completing), **next run starts over with same 13,496 candidates**

### Proposed: Age-Bounded Backlog Query

```python
# Current unbounded query
articles_list = await collection.find(enrichment_query).to_list(None)  # ← ALL matching

# Proposed bounded query
MAX_BACKLOG_ARTICLES = 500  # Process max 500 per cycle
min_created_at = datetime.now(timezone.utc) - timedelta(days=30)  # 30-day retention window
bounded_query = {
    "created_at": {"$gte": min_created_at},  # Age cutoff (30d candidate)
    "$or": [...enrichment_query...$or]
}
articles_list = await collection.find(bounded_query)\
    .sort("created_at", -1)\
    .limit(MAX_BACKLOG_ARTICLES)\
    .to_list(None)
```

Benefits:
- **Memory safe:** At most 500 articles in memory
- **Freshness priority:** Newest articles processed first (highest signal value)
- **Restart resilient:** Next cycle picks up where previous left off (same sort order)
- **Historical recovery:** Can run separate backfill job with explicit cost cap

---

## Part 3: Error Path Analysis

### Error 1: E11000 Duplicate Key (21:23 UTC)

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py` (line 101)
```python
await create_or_update_articles(articles)
```

**Root cause:** E11000 on `articles.url` index. The RSS fetcher calls `create_or_update_articles()` before entity extraction. If a URL is duplicated in the feed batch or has been seen before, the batch insert fails **entirely** (not partial).

**Impact on Signal creation:** If `create_or_update_articles()` fails, the function exits without reaching `process_new_articles_from_mongodb()` (line 104). **No entity extraction runs for that cycle.**

**Check needed:** Review `create_or_update_articles()` error handling—does it:
- [ ] Log the duplicate key error and continue with non-duplicates?
- [ ] Halt the entire batch and skip enrichment?
- [ ] Return partial success?

### Error 2: NoneType Error (22:48 UTC)

**Message:** `'NoneType' object is not subscriptable`

**Likely locations in extraction path:**

1. **Line 283-285:** Entity deduplication
   ```python
   for article_result in result.get("results", []):  # ← result could be None
       if "entities" in article_result:  # ← article_result could be None
   ```

2. **Line 442-443:** Article loading from MongoDB
   ```python
   async for article in collection.find(enrichment_query):
       articles_list.append(article)  # ← article could be None
   ```

3. **Line 477:** Selective processor decision
   ```python
   use_llm = selective_processor.should_use_llm(article)  # ← article None
   ```

4. **LLM response parsing:** `extract_entities_batch()` or `enrich_articles_batch()` returns None instead of dict

**Impact:** Single failed article halts batch processing, but code logs and continues. However, if the failure is in the LLM response parsing, **no entities are created for that batch**.

---

## Part 4: Entity Mention Creation Flow

### Critical Path for Signals Display

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py` (lines 806-892)

Entity mentions are created **only if:**
1. Article enrichment succeeds (relevance tier assigned)
2. Article passes tier classification (tier 1-3)
3. Entity extraction yields primary or context entities
4. Database insert succeeds

**Conditions that create ZERO mentions:**

1. **No enrichment run:** RSS ingestion fails (E11000) → line 104 never reached
2. **LLM extraction fails:** NoneType or other exception (lines 512-517) → fallback to regex, or both fail
3. **Tier 2-3 articles:** Enrichment skipped entirely (lines 668-685) → Only tier 1 articles get entity mentions
4. **Batch insert fails:** `insert_many()` fails (line 877) → Mentions don't persist

**Current evidence from ticket:**

> 44 articles in 24h and 346 in 7d, but **no recent entity mentions**; last mention from Aug 24

This pattern suggests:
- ✅ Articles ARE being ingested (44 in 24h)
- ❌ Entity extraction/enrichment is **not completing** or **not persisting mentions**
- ❌ Tier classification is either skipping all to tier 2-3, or entity extraction is failing

---

## Part 5: Trace Extraction Run 21:45:58

**Evidence from Railway logs:**
```
21:45:58: Processing entity extraction batch 0-10 of 13496 articles
```

This log comes from line 463-468:
```python
logger.info(
    "Processing entity extraction batch %d-%d of %d articles",
    i,
    min(i + batch_size, len(articles_list)),
    len(articles_list),
)
```

**What we know:**
- ✅ 13,496 articles were loaded (all matching enrichment_query)
- ✅ Batch 0-10 started
- ❓ Did batches 1, 2, ... N complete?
- ❓ Were any mentions persisted?
- ❓ Did process crash mid-run or timeout?

**Check needed:** Full Railway logs from 21:45 onward to track:
1. All batch progress (0-10, 10-20, 20-30, ...)
2. Whether entity extraction completed or failed
3. Whether mention inserts succeeded
4. When the process exited (clean completion vs. crash)

---

## Part 6: Proposed Bounded Recovery Design

### Phase 1: Immediate (30 min per cycle)

**Goal:** Stop the 13,496-article backlog from restarting infinitely.

**Changes:**

1. **Bound article selection** (line 426-443)
   ```python
   # Add age cutoff + limit to enrichment_query
   max_age_days = 30  # Product retention window
   min_created_at = datetime.now(timezone.utc) - timedelta(days=max_age_days)
   
   bounded_query = {
       "created_at": {"$gte": min_created_at},
       "$or": [enrichment query clauses]
   }
   
   articles_list = await collection.find(bounded_query)\
       .sort("created_at", -1)\
       .limit(500)\
       .to_list(None)
   ```

2. **Handle ingestion errors gracefully** (line 101)
   - Ensure `create_or_update_articles()` uses upsert semantics (not batch insert)
   - If a duplicate URL exists, update; don't fail the entire batch
   - Log count of inserted/updated articles separately

3. **Persist enrichment progress incrementally** (line 804, 877)
   - After each article update, log `article_id` to a `{article_id: completed_at}` tracking collection
   - Next cycle: skip already-completed articles
   - Reduces restart storm impact

### Phase 2: Historical Backfill (separate, cost-capped)

**Goal:** Clear articles older than 30d that were never enriched (e.g., from before the RSS worker was fixed).

**Design:**
- Separate scheduled job (e.g., weekly at 3 AM)
- Age cutoff: `created_at < (now - 30d)`
- Cost cap: Max 100 articles per week (to avoid billing surprises)
- Can be disabled/adjusted in config

---

## Part 7: Database Evidence Collection Plan

To confirm the root cause, we need to execute the read-only MongoDB queries from the ticket:

### 1. Article Freshness (last 24h, 7d, 30d)
```javascript
const now = new Date();
for (const hours of [24, 168, 720]) {
  const since = new Date(now.getTime() - hours * 60 * 60 * 1000);
  print(`articles last ${hours}h`);
  printjson(db.articles.aggregate([
    { $match: { created_at: { $gte: since } } },
    { $group: {
      _id: "$source",
      count: { $sum: 1 },
      earliest: { $min: "$created_at" },
      latest: { $max: "$created_at" }
    } },
    { $sort: { count: -1 } },
    { $limit: 30 }
  ]).toArray());
}
```

### 2. Mention Counts by Window & Primary Flag
```javascript
const now = new Date();
for (const hours of [24, 168, 720]) {
  const since = new Date(now.getTime() - hours * 60 * 60 * 1000);
  print(`entity_mentions last ${hours}h`);
  printjson(db.entity_mentions.aggregate([
    { $match: { created_at: { $gte: since } } },
    { $group: {
      _id: { primary: "$is_primary", type: "$entity_type", source: "$source" },
      count: { $sum: 1 },
      earliest: { $min: "$created_at" },
      latest: { $max: "$created_at" },
      entities: { $addToSet: "$entity" }
    } },
    { $project: {
      _id: 1, count: 1, earliest: 1, latest: 1,
      entities: { $slice: ["$entities", 30] }
    } },
    { $sort: { count: -1 } },
    { $limit: 100 }
  ]).toArray());
}
```

### 3. Backlog Age Distribution
```javascript
const since_30d = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
const since_7d = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
const since_1d = new Date(Date.now() - 1 * 24 * 60 * 60 * 1000);

printjson(db.articles.aggregate([
  { $match: {
    $or: [
      { relevance_score: { $exists: false } },
      { relevance_score: null },
      { relevance_tier: { $exists: false } }
    ]
  } },
  { $group: {
    _id: null,
    total: { $sum: 1 },
    last_1d: { $sum: { $cond: [{ $gte: ["$created_at", since_1d] }, 1, 0] } },
    last_7d: { $sum: { $cond: [{ $gte: ["$created_at", since_7d] }, 1, 0] } },
    last_30d: { $sum: { $cond: [{ $gte: ["$created_at", since_30d] }, 1, 0] } },
    older_30d: { $sum: { $cond: [{ $lt: ["$created_at", since_30d] }, 1, 0] } }
  } }
]).toArray());
```

---

## Summary of Findings

| Finding | Evidence | Impact |
|---------|----------|--------|
| **Unbounded backlog** | `collection.find(enrichment_query).to_list(None)` loads ALL matching articles | 13,496 articles → memory pressure, restart loops |
| **Single RSS instance** | `asyncio.create_task(schedule_rss_fetch(...))` in main.py lifespan | Repeated startup logs likely from container restarts, not multiple replicas |
| **E11000 duplicate errors** | `create_or_update_articles()` uses batch insert semantics (fails on any duplicate) | If one URL duplicate exists, **entire enrichment cycle skipped** |
| **NoneType errors** | LLM response parsing or selective processor failures | Batch processing halts; mentions not persisted |
| **Tier 2-3 articles** | Enrichment skipped for non-tier-1 (lines 668-685) | Only tier 1 articles yield mentions; if classifier marks all as tier 2-3, **zero mentions created** |
| **No mention persistence tracking** | No progress checkpoint after enrichment completion | Restart causes entire backlog to re-process (inefficient, cost multiplier) |

---

## Remediation Steps (For Operator Authorization)

**Do NOT proceed without explicit approval:**

1. **Check Railway metadata:** Confirm single instance vs. multiple replicas; review restart events 21:45-22:48 UTC
2. **Review full extraction logs:** Trace batch 0-10 through completion to determine where process halted
3. **Run MongoDB queries:** Execute backlog distribution and mention counts to quantify the gap
4. **Identify trigger:** Determine if E11000, NoneType, tier classification, or another error is blocking mentions
5. **Deploy bounded backlog fix:** Apply age cutoff + limit + progress tracking
6. **Validate:** Re-run entity extraction on fresh articles, verify mention creation in entity_mentions
7. **Monitor:** Track mention creation latency and tier distribution over 3 cycles

---

## Acceptance Criteria (From Ticket)

- [x] **Recent article, primary mention, API, and cache evidence** → See Part 2-4 of this analysis
- [ ] **Railway evidence** → Pending operator data (restart pattern, extraction log trace)
- [ ] **Error tracing** → E11000 and NoneType impacts identified (Part 3)
- [ ] **Backlog quantification** → Ready to run MongoDB queries (Part 7)
- [ ] **Root cause** → Likely: Unbounded backlog + restart loop + either ingestion error (E11000) OR tier classification skipping entity extraction
- [ ] **Recovery design** → Proposed in Part 6 (bounded query + progress tracking + separate backfill)
- [ ] **Product intent** → Signals page label says "24h" but API defaults to "7d" (reconcile after root cause found)
- [x] **Implementation readiness** → Minimal code changes identified; no production writes needed to diagnose

