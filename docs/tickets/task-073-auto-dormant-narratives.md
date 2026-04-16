---
ticket_id: TASK-073
title: Auto-dormant narratives when all source articles are purged
priority: medium
severity: medium
status: OPEN
date_created: 2026-04-15
branch: 
effort_estimate: 1-2 hours
---

# TASK-073: Auto-dormant narratives when all source articles are purged

## Problem Statement

Narratives reference source articles via `article_ids`, but when articles are deleted (e.g., manual purges to free MongoDB space), the narratives remain `lifecycle_state: "hot"` indefinitely. These zombie narratives have summaries that can never be re-verified or regenerated, and they remain eligible for briefing inclusion. Any of them could contain fabricated content (as discovered with the Kraken extortion narrative in BUG-084) with no way to detect it.

This was first observed after the BUG-055 MongoDB purge (Sprint 12, 516→253 MB) which deleted old articles but left their narratives active. During the Session 32 investigation, 7 zombie narratives were found with zero surviving source articles, manually marked dormant under `BUG-084-zombie-cleanup`. The problem will recur on every future article purge.

---

## Task

**Part 1 — One-time cleanup query (run manually after any article purge):**

Write a MongoDB aggregation that identifies narratives where none of the referenced `article_ids` exist in the `articles` collection, then marks them dormant. Logic:

```javascript
// Find zombie narratives: hot narratives where zero article_ids resolve to existing articles
db.narratives.aggregate([
  { $match: { lifecycle_state: "hot" } },
  { $addFields: {
    article_object_ids: {
      $map: { input: "$article_ids", as: "aid", in: { $toObjectId: "$$aid" } }
    }
  }},
  { $lookup: {
    from: "articles",
    localField: "article_object_ids",
    foreignField: "_id",
    as: "surviving_articles"
  }},
  { $match: { "surviving_articles": { $size: 0 } } },
  { $project: { title: 1, article_ids: 1 } }
])
```

Then update the results:
```javascript
db.narratives.updateMany(
  { _id: { $in: [/* IDs from aggregation */] } },
  { $set: { lifecycle_state: "dormant", dormant_since: new Date(), _disabled_by: "TASK-073-zombie-cleanup" } }
)
```

**Part 2 — Periodic automated check:**

Add a scheduled function that runs daily (or after each RSS ingestion cycle) that performs the same aggregation and auto-dormants any narratives with zero surviving source articles. Log a warning when narratives are auto-dormanted so it's visible in Railway logs. Suggested location: narrative_service.py or a new maintenance module called from the worker scheduler.

The function should:
- Query all `lifecycle_state: "hot"` narratives
- For each, check whether at least one `article_id` still exists in the `articles` collection
- If zero articles survive, set `lifecycle_state: "dormant"`, `dormant_since: new Date()`, `_disabled_by: "TASK-073-auto-cleanup"`
- Log: `"Auto-dormanted {count} zombie narrative(s) with no surviving source articles: {titles}"`

---

## Verification

1. Run the Part 1 cleanup query against production — confirm it returns zero results (since the 7 known zombies were already manually cleaned up in Session 32)
2. Manually delete a test article that is the sole source for a narrative, then run the periodic check — confirm the narrative transitions to dormant
3. Confirm the function logs the expected warning message
4. Confirm narratives with at least one surviving article are NOT affected

---

## Acceptance Criteria

- [ ] One-time cleanup query documented and tested against production
- [ ] Periodic check runs on schedule (daily or post-ingestion)
- [ ] Zombie narratives are auto-dormanted with logging
- [ ] Narratives with at least one surviving article are unaffected
- [ ] No new dependencies or LLM calls required

---

## Impact

Prevents zombie narratives (potentially containing fabricated content) from appearing in user-facing briefings. Eliminates the need for manual narrative audits after article purges. Low effort, no LLM cost impact, purely database maintenance.

---

## Related Tickets

- BUG-084: Narrative summary generator fabricates events not present in source articles (root cause discovery)
- BUG-055: SMOKE_BRIEFINGS leak + MongoDB quota full (original article purge that created the zombies)
- TASK-066: Stale narrative cleanup (Sprint 14 — deleted 233 October 2025 narratives, but did not address article reference integrity)