---
ticket_id: TASK-013
title: Create MongoDB Indexes for Signal Pipeline Performance
priority: medium
severity: medium
status: OPEN
date_created: 2026-02-24
branch: 
effort_estimate: 15 min
---

# TASK-013: Create MongoDB Indexes for Signal Pipeline Performance

## Problem Statement

After BUG-036/037/038 move sort/limit to Python, the `$match` stages at the top of each pipeline become the critical performance gate. Without proper indexes, MongoDB scans the full `entity_mentions` collection for every signals request. These indexes ensure the `$match` stages are fast so less data enters the pipelines.

---

## Task

Create three indexes in Atlas Console (mongosh). These are **not code changes** — run directly in the Atlas UI.

### Index 1: Primary signals index
Covers `compute_trending_signals()` and `get_top_entities_by_mentions()` `$match` stages: `{is_primary: true, created_at: {$gte: ...}}`

```javascript
db.entity_mentions.createIndex(
  { is_primary: 1, created_at: -1, entity: 1 },
  { name: "signals_primary_time_entity" }
)
```

### Index 2: Entity type filter index
For when `entity_type` filter is used in signals queries.

```javascript
db.entity_mentions.createIndex(
  { is_primary: 1, entity_type: 1, created_at: -1, entity: 1 },
  { name: "signals_primary_type_time_entity" }
)
```

### Index 3: Per-entity lookup index
For `get_recent_articles_for_entity()` which matches on entity name.

```javascript
db.entity_mentions.createIndex(
  { entity: 1 },
  { name: "signals_entity_lookup" }
)
```

---

## Verification

```javascript
// In Atlas mongosh, verify indexes exist:
db.entity_mentions.getIndexes()
// Should show all three new indexes plus the default _id index

// Verify index usage with explain:
db.entity_mentions.explain("executionStats").aggregate([
  {$match: {is_primary: true, created_at: {$gte: new Date("2026-02-01")}}},
  {$limit: 1}
])
// Should show IXSCAN (not COLLSCAN) using signals_primary_time_entity
```

---

## Acceptance Criteria

- [ ] `signals_primary_time_entity` index created
- [ ] `signals_primary_type_time_entity` index created
- [ ] `signals_entity_lookup` index created
- [ ] Verify with `.getIndexes()` that all three exist
- [ ] No Atlas M0 index limit issues (M0 allows sufficient indexes)

---

## Impact

Reduces `$match` scan time from full collection scan to index lookup. Critical for keeping signal page response times under 2 seconds as data grows.

---

## Related Tickets

- BUG-036, BUG-037, BUG-038 (pipeline fixes these indexes support)