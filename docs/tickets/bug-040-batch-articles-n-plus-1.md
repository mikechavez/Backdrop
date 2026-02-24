---
id: BUG-040
type: bug
status: completed
priority: critical
severity: high
created: 2026-02-24
updated: 2026-02-24
merged: 2026-02-24T21:28:24Z
branch: fix/bug-040-batch-articles-n-plus-1
commit: f40812c
pr: "185"
---

# BUG-040: get_recent_articles_batch() N+1 Query Causes 45s+ Signals Load Time

## Problem

`get_recent_articles_batch()` in `signals.py` fires **50 separate aggregation pipelines** (one per entity) via `asyncio.gather()`. Each pipeline includes a `$lookup` join from `entity_mentions` to `articles`. On Atlas M0, this takes 45+ seconds for 50 entities, making the signals page effectively unusable (52s total request time).

Despite using `asyncio.gather()` for concurrency, Atlas M0's connection pool and compute limits serialize these queries in practice.

**Logs showing the problem:**
```
[Signals] Computed 50 trending signals in 1.519s          ← fast (BUG-036 fix working)
[Signals] Batch fetched 126 narratives in 5.154s          ← ok
[Signals] Batch fetched 249 articles for 50 entities in 45.751s  ← 🔴 BLOCKER
[Signals] Total request time: 52.426s                      ← unusable
```

## Expected Behavior

Signals page loads in <5 seconds total.

## Actual Behavior

Signals page takes 52+ seconds to load. The articles batch fetch alone takes 45+ seconds.

## Root Cause

The current `get_recent_articles_batch()` calls `get_recent_articles_for_entity()` once per entity via `asyncio.gather`:

```python
# CURRENT CODE (N+1 pattern) — signals.py, get_recent_articles_batch()
async def get_recent_articles_batch(entities: List[str], limit_per_entity: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    if not entities:
        return {}

    tasks = [get_recent_articles_for_entity(entity, limit=limit_per_entity) for entity in entities]
    results = await asyncio.gather(*tasks)
    return {entity: articles for entity, articles in zip(entities, results)}
```

Each `get_recent_articles_for_entity()` call runs a full `$match → $addFields → $lookup → $unwind → $group → $project` pipeline. With 50 entities, that's 50 round trips to Atlas, each with a `$lookup` join.

**Caller** (`get_trending_signals()`, same file, ~line 475):
```python
articles_by_entity = await get_recent_articles_batch(entities, limit_per_entity=5)
```
The caller does NOT change — only the implementation of `get_recent_articles_batch()` changes.

## Environment
- Environment: production (Railway + Atlas M0)
- User impact: critical — signals page takes 52s to load

---

## Resolution

### Change to `get_recent_articles_batch()`

**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

Replace the entire `get_recent_articles_batch()` function body. The new implementation runs **one single aggregation** that matches all entities at once using `$match: {entity: {$in: entities}}`, then partitions, sorts, and limits in Python.

**Complete replacement function:**

```python
async def get_recent_articles_batch(entities: List[str], limit_per_entity: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    Batch fetch recent articles for multiple entities in a SINGLE aggregation pipeline.

    Replaces the previous N+1 approach (one pipeline per entity) which caused 45s+ load
    times on Atlas M0 with 50 entities. This runs one pipeline for all entities, then
    partitions and limits in Python.

    Args:
        entities: List of entity names to fetch articles for
        limit_per_entity: Maximum number of articles per entity (default 5)

    Returns:
        Dict mapping entity name to list of article dicts
    """
    if not entities:
        return {}

    db = await mongo_manager.get_async_database()
    mentions_collection = db.entity_mentions

    # Single pipeline for ALL entities at once
    pipeline = [
        # Match mentions for any of the requested entities
        {"$match": {"entity": {"$in": entities}}},

        # Convert article_id string to ObjectId if needed
        {"$addFields": {
            "article_oid": {"$cond": [
                {"$eq": [{"$type": "$article_id"}, "string"]},
                {"$toObjectId": "$article_id"},
                "$article_id"
            ]}
        }},

        # Join with articles collection
        {"$lookup": {
            "from": "articles",
            "localField": "article_oid",
            "foreignField": "_id",
            "as": "article"
        }},

        # Unwind the article array
        {"$unwind": "$article"},

        # Deduplicate by entity + article URL, use $max for latest published_at
        {"$group": {
            "_id": {"entity": "$entity", "url": "$article.url"},
            "title": {"$first": "$article.title"},
            "url": {"$first": "$article.url"},
            "source": {"$first": "$article.source"},
            "published_at": {"$max": "$article.published_at"},
            "entity": {"$first": "$entity"},
        }},

        # Project only the fields we need
        {"$project": {
            "_id": 0,
            "entity": 1,
            "title": 1,
            "url": 1,
            "source": 1,
            "published_at": 1,
        }}
    ]

    # Run single aggregation (post-$group results are small: ~5-20 articles per entity)
    all_articles = await mentions_collection.aggregate(pipeline).to_list(length=20000)

    # Partition by entity, sort by published_at desc, limit per entity — all in Python
    result: Dict[str, List[Dict[str, Any]]] = {entity: [] for entity in entities}
    for doc in all_articles:
        entity = doc.get("entity", "")
        if entity in result:
            result[entity].append({
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "source": doc.get("source", ""),
                "published_at": doc.get("published_at").isoformat() if doc.get("published_at") else None,
            })

    # Sort each entity's articles by published_at desc and limit
    for entity in result:
        result[entity].sort(key=lambda x: x["published_at"] or "", reverse=True)
        result[entity] = result[entity][:limit_per_entity]

    return result
```

### Key Design Decisions

1. **`$group` key is `{entity, url}`** — same dedup logic as the per-entity version (BUG-032 fix preserved)
2. **`$max` for `published_at`** — same pattern as BUG-038 fix; doesn't rely on pre-sort order
3. **No `$sort` or `$limit` in pipeline** — Atlas M0 safe (same pattern as BUG-036/037/038)
4. **`.to_list(length=20000)`** — generous cap; real data is ~250-1000 docs (5-20 per entity × 50 entities)
5. **Python partition/sort/limit is instant** on this data size
6. **Pipeline reuses same `$addFields` / `$lookup` / `$unwind` pattern** as `get_recent_articles_for_entity()` (single-entity version) — proven working in BUG-038

### What NOT to Change

- **`get_recent_articles_for_entity()`** (single-entity version, lines ~134-210) — keep as-is, still used by the `/signals` (top 20) endpoint via `get_signals()`
- **`get_trending_signals()` caller code** (~line 475) — no changes needed, same function signature and return type
- **No new imports needed** — `mongo_manager`, `Dict`, `List`, `Any` already imported at top of file

### Why This Is Safe

- Post-`$group` results are small (~5-20 articles per entity × 50 entities = ~250-1000 docs)
- No `$sort` or `$limit` in the pipeline (Atlas M0 safe)
- `$group` key is `{entity, url}` — same dedup logic as the per-entity version
- Python partition/sort/limit is instant on this data size

### Expected Performance

| Step | Before | After (expected) |
|------|--------|-------------------|
| Trending signals | 1.5s | 1.5s (unchanged) |
| Narratives batch | 5-7s | 5-7s (unchanged) |
| **Articles batch** | **45.7s** | **1-3s** |
| **Total** | **52.4s** | **~10s** |

### Testing

1. Deploy and hit `/api/v1/signals/trending?timeframe=7d&limit=50`
2. Check Railway logs for `[Signals] Batch fetched ... articles` time — should be <5s
3. Verify total request time <10s
4. Confirm articles are still newest-first per entity
5. Confirm no duplicate articles per entity
6. Run existing test suite: `pytest tests/api/test_signals.py tests/api/test_signals_caching.py`

### Files Changed
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py` — replace `get_recent_articles_batch()` function body only