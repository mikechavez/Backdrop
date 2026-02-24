---
ticket_id: TASK-012
title: Add MongoDB Indexes to Reduce Aggregation Memory Pressure
priority: LOW
severity: N/A
status: OPEN
date_created: 2026-02-23
branch: chore/task-012-mongodb-indexes
effort_estimate: 30 minutes
---

# TASK-012: Add MongoDB Indexes to Reduce Aggregation Memory Pressure

## Problem Statement

BUG-034's `allowDiskUse=True` fix allows aggregations to spill to disk when they exceed 32MB, but disk-based sorts are significantly slower than indexed sorts. The proper long-term fix is to add indexes that let MongoDB satisfy sort operations from the index itself, avoiding both memory pressure and disk spills.

The signal service's heaviest pipelines sort on `created_at`, `published_at`, and group by `entity` — none of which may have optimal compound indexes for the aggregation access patterns.

---

## Task

Add compound indexes optimized for the signal service's aggregation pipelines.

### Recommended Indexes

**1. `entity_mentions` — primary signal aggregation index**
```javascript
db.entity_mentions.createIndex(
  { "is_primary": 1, "created_at": -1, "entity": 1 },
  { name: "idx_mentions_primary_created_entity" }
)
```
*Covers:* `compute_trending_signals()` pipeline — matches on `is_primary`, sorts by `created_at`, groups by `entity`.

**2. `entity_mentions` — entity lookup with timestamp**
```javascript
db.entity_mentions.createIndex(
  { "entity": 1, "created_at": -1 },
  { name: "idx_mentions_entity_created" }
)
```
*Covers:* `_count_filtered_mentions()`, `calculate_mentions_and_velocity()` — filters by entity, sorts/ranges on `created_at`.

**3. `entity_mentions` — timestamp for stale signal filtering**
```javascript
db.entity_mentions.createIndex(
  { "entity": 1, "timestamp": -1 },
  { name: "idx_mentions_entity_timestamp" }
)
```
*Covers:* `get_trending_entities()` in `signal_scores.py` — checks for recent mentions via `timestamp` field.

**4. `articles` — relevance tier filtering**
```javascript
db.articles.createIndex(
  { "relevance_tier": 1, "created_at": -1 },
  { name: "idx_articles_relevance_created" }
)
```
*Covers:* `_get_high_signal_article_ids()` — filters by `relevance_tier`, ranges on `created_at`.

**5. `articles` — published_at for article sorting**
```javascript
db.articles.createIndex(
  { "published_at": -1 },
  { name: "idx_articles_published_desc" }
)
```
*Covers:* `get_recent_articles_for_entity()` in `signals.py` — sorts articles by publish date.

### Pre-Check: Existing Indexes

Before creating new indexes, check what already exists:

```javascript
db.entity_mentions.getIndexes()
db.articles.getIndexes()
db.narratives.getIndexes()
db.signal_scores.getIndexes()
```

Skip any index that already exists or is a subset of an existing compound index.

---

## Verification

```bash
# 1. Confirm indexes exist
# In mongo shell or via script:
db.entity_mentions.getIndexes()
# Should include idx_mentions_primary_created_entity and idx_mentions_entity_created

# 2. Verify aggregation uses index (optional)
db.entity_mentions.aggregate([
  {"$match": {"is_primary": true, "created_at": {"$gte": ISODate("2026-02-01")}}},
  {"$group": {"_id": "$entity", "count": {"$sum": 1}}},
  {"$sort": {"count": -1}},
  {"$limit": 20}
]).explain("executionStats")
# Check that "stage" shows "IXSCAN" not "COLLSCAN"

# 3. Load test signals page — should be noticeably faster
curl -w "\nTime: %{time_total}s\n" -s https://context-owl-production.up.railway.app/api/v1/signals/trending -o /dev/null
```

---

## Impact

- ✅ **Performance**: Indexed sorts avoid both memory pressure and disk spills
- ✅ **Cost**: Reduces MongoDB Atlas compute time for aggregations
- ✅ **Scale**: Supports continued data growth without degradation
- ⚠️ **Trade-off**: Each index adds ~10-50MB storage and marginal write overhead

---

## Acceptance Criteria

- [ ] Existing indexes audited (no redundant indexes created)
- [ ] New indexes created on `entity_mentions` and `articles`
- [ ] Signals page loads without errors
- [ ] No significant write performance regression on ingestion

---

## Related Tickets

- BUG-034: The crash that revealed memory pressure issues
- TASK-011: `allowDiskUse` audit (band-aid fix; this ticket is the proper fix)
- 50-data-model.md: Documents query performance trade-offs (batch vs parallel)