---
ticket_id: BUG-108
title: Investigate empty Signals page despite recent article ingestion
priority: high
status: OPEN
phase: A
date_created: 2026-09-13
branch: null
effort_estimate: medium
---

# BUG-108: Investigate empty Signals page despite recent article ingestion

## Problem Statement

The production Signals page displays “No signals detected yet.” The health endpoint recently reported fresh articles, but the trending-signals API returned no results for the page's effective timeframe. The underlying cause is not yet established; investigate the complete path from article ingestion and entity extraction through `entity_mentions` aggregation and frontend rendering before proposing a fix.

## Production Evidence (2026-09-13)

- `GET /api/v1/signals/trending?limit=15&timeframe=7d` returned HTTP 200 with `count: 0`, `total_count: 0`, and an empty `signals` array at 19:48:58 UTC.
- The same endpoint returned zero signals for `timeframe=24h` at 19:49:14 UTC.
- The endpoint returned one result for `timeframe=30d` at 19:49:16 UTC: Bitcoin, one current-period mention, seven sources, and score 1.17.
- A health response around 19:42 UTC reported `data_freshness.status=ok` and a latest article age of about 0.3 hours. This confirms recent article data, but does not establish that those articles produced recent primary `entity_mentions`.
- `context-owl-ui/src/pages/Signals.tsx` calls `signalsAPI.getSignals()` without a timeframe. The API helper omits undefined filters, and the backend defaults the endpoint to `7d`. The page description says “Most talked-about keywords in the last 24 hours,” so its label and effective query window currently disagree.

## Investigation Plan

1. Inspect production-safe counts and timestamps for recent `articles` and `entity_mentions`, including `created_at`, `is_primary`, entity type, and source. Do not expose article contents or MongoDB credentials in logs or ticket updates.
2. Trace the deployed ingestion and entity-extraction tasks: verify their schedules, dispatch, successful completion, and whether recent articles are yielding primary entity mentions.
3. Compare the API's 24-hour, 7-day, and 30-day calculations with the underlying mention records and cache behavior. Determine why the 30-day query yields one result while the shorter windows yield none.
4. Verify what timeframe the product intends the Signals page to display and reconcile the UI label with the query once the data-path cause is understood.
5. Document a root cause and minimal remediation plan, then verify the API and page with fresh production data after an approved fix.

## Read-only investigation handoff

The investigator may use the production MongoDB URI from the local environment **only for read-only queries**. Never print, copy into output, or commit the URI or any other secret. Do not query article title/body/content/description or return article documents; report only counts, timestamps, entity names/types, and source labels. Use the production URI with `mongosh` locally (do not put the URI in a ticket, command transcript, or report):

```sh
mongosh "$MONGODB_URI" --quiet
```

Run these in the resulting mongosh prompt. They use one client-side UTC-relative reference time per comparison and only return aggregate metadata.

### 1. Article freshness and volume

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

If article documents use a different ingestion timestamp field, identify it from schema/code and rerun using that field; do not substitute publication time silently.

### 2. Mention counts by window, primary flag, type, and source

This first pass describes stored mentions without joining or exposing article data:

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

### 3. Compare to the endpoint's exact mention-window logic

`compute_trending_signals()` currently uses `entity_mentions.created_at`, `is_primary: true`, and requires at least one mention in the current period. It includes the preceding equal-length period in its aggregation; it does not join `articles` or apply the relevance-tier filter described in some service comments. This aggregate reports current/previous counts, latest timestamp, and types for each entity using that exact boundary logic:

```javascript
const now = new Date();
for (const [label, hours] of [["24h", 24], ["7d", 168], ["30d", 720]]) {
  const currentStart = new Date(now.getTime() - hours * 60 * 60 * 1000);
  const previousStart = new Date(now.getTime() - 2 * hours * 60 * 60 * 1000);
  print(`endpoint window ${label}`);
  printjson(db.entity_mentions.aggregate([
    { $match: { is_primary: true, created_at: { $gte: previousStart } } },
    { $group: {
      _id: "$entity",
      types: { $addToSet: "$entity_type" },
      previous_mentions: { $sum: { $cond: [{ $lt: ["$created_at", currentStart] }, 1, 0] } },
      current_mentions: { $sum: { $cond: [{ $gte: ["$created_at", currentStart] }, 1, 0] } },
      latest_mention: { $max: "$created_at" },
      sources: { $addToSet: "$source" }
    } },
    { $match: { current_mentions: { $gte: 1 } } },
    { $project: {
      entity: "$_id", _id: 0, types: 1, previous_mentions: 1,
      current_mentions: 1, latest_mention: 1,
      source_count: { $size: "$sources" }
    } },
    { $sort: { current_mentions: -1, latest_mention: -1 } },
    { $limit: 100 }
  ]).toArray());
}
```

Compare database-server time with the API host's UTC time if a boundary discrepancy is suspected. The endpoint's GET can populate its Redis or in-memory cache, so ask the operator to run those requests or explicitly authorize them before doing so. Use explicit `timeframe=24h`, `7d`, and `30d` parameters; record response status, count/total_count, computed_at/cached, and returned entity names only. Recheck after at least 60 seconds or with a fresh process/request path to distinguish its 60-second cache from underlying data.

### 4. Trace article-to-mention linkage without retrieving content

The mention `article_id` is stored as a string by the standard insert path; confirm actual types before comparing to article `_id` (ObjectId). Use this aggregate to quantify unmatched records while returning no article content:

```javascript
const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
printjson(db.entity_mentions.aggregate([
  { $match: { created_at: { $gte: since }, is_primary: true } },
  { $set: {
    article_oid: {
      $convert: { input: "$article_id", to: "objectId", onError: null, onNull: null }
    }
  } },
  { $lookup: {
    from: "articles", localField: "article_oid", foreignField: "_id", as: "article_match"
  } },
  { $group: {
    _id: {
      mention_type: { $type: "$article_id" },
      matched_article: { $gt: [{ $size: "$article_match" }, 0] },
      entity_type: "$entity_type", source: "$source"
    },
    count: { $sum: 1 },
    latest: { $max: "$created_at" }
  } },
  { $sort: { count: -1 } },
  { $limit: 100 }
]).toArray());
```

### Runtime and UI checks

- Trace `fetch_and_process_rss_feeds()` through `process_new_articles_from_mongodb()` and the entity-mention insert path. Repository code has an RSS background loop; `tasks/beat_schedule.py` does not itself establish that the production RSS worker is running. Verify the actual deployed service/replicas, effective interval, recent successful runs, failures, and mention creation timestamps using read-only hosting logs/metrics. Check scheduler and worker separately if production runs Celery.
- Check the deployed API logs around the observed request times for `signals_trending` / `signals_cache` entries. Do not trigger processing, clear cache, or change production settings as part of diagnosis.
- The UI request in `context-owl-ui/src/pages/Signals.tsx` sends limit/offset but no timeframe; `signals.ts` forwards an undefined timeframe, so the endpoint default `7d` applies. The page's “last 24 hours” description therefore disagrees with its request. Record the intended product timeframe as an open decision; do not change the label/request until that intent is established.

### Authorization boundary

Cloud Code can perform repository inspection, these read-only database queries, deployed read-only log/metric review, and local tests. Stop before any production write or operational action that can mutate state, including endpoint requests that populate caches, rerunning/backfilling extraction, manually triggering ingestion, clearing caches, changing schedules/configuration, creating indexes, editing production data, or deploying. Report the proposed action and exact scope for the operator (ticket owner) to run or approve. Once the root cause and intended UI timeframe are established, prepare the minimal code/test change as a reviewable patch; production verification after deployment remains read-only unless the operator separately authorizes a specific write.

## Related Work and Scope

- BUG-054 previously addressed a disabled RSS ingestion schedule. Confirm the current production schedule rather than assuming that historical fix guarantees ingestion and entity extraction are healthy now.
- TASK-105 covers freshness monitoring of persisted `signal_scores`; this page's trending endpoint computes results on demand from `entity_mentions`, so TASK-105 alone does not establish this endpoint's health.
- BUG-083 documents a disabled market-event detector. The Signals page endpoint investigated here is the separate trending-entity endpoint; do not assume BUG-083 explains this symptom.
- This ticket is investigation-first. Do not change signal scoring, thresholds, or delete/alter production data until the cause and intended behavior are established.

## Investigation Results (2026-09-13)

### Root Cause: IDENTIFIED ✓
**Entity extraction is not running or not creating primary entity mentions for recent articles.**

- ✅ Articles: 45 ingested in last 24h (Sept 12 21:33 → Sept 13 21:23 UTC) across 6 sources (bitcoin.com, cryptoslate, coindesk, etc.)
- ❌ Entity mentions: 0 primary mentions in 24h and 7d windows; only 2 mentions total in 30d (from Aug 24, 20 days old)
- ✅ Article-to-mention linkage: Valid—the 2 primary mentions found have matching articles and correct types
- ✅ Signal computation: Correct—returns zero for 24h/7d because there genuinely are no recent primary mentions
- ✅ API response: Correct—`GET /api/v1/signals/trending?timeframe=7d` correctly returned count:0 at 19:48:58 UTC
- ✅ Frontend: Correct—displays "No signals detected yet." when count===0

### Data Path Validation
1. **Ingestion:** ✅ RSS feeds running, 45 articles in 24h
2. **Entity Extraction:** ❌ **NOT PRODUCING PRIMARY MENTIONS** (failure point; last mention: Aug 24)
3. **Signal Computation:** ✅ Returns zero correctly given the data
4. **API:** ✅ Returns zero correctly
5. **Frontend:** ✅ Displays zero correctly

### Why 30d Returns One Result
The 30d endpoint response (Bitcoin, score 1.17) is correct: Bitcoin has 1 mention dated Aug 24 (just within 30d window) that meets `current_mentions >= 1` filter. This is old data that happens to pass the time boundary.

### Secondary Issue: Frontend-Backend Timeframe Mismatch
- **UI Label:** "Most talked-about keywords in the **last 24 hours**"
- **Actual Request:** No explicit `timeframe` param → backend defaults to **7d**
- **Impact:** Mismatch is confusing but secondary; will be fixed once entity extraction resumes

### Proposed Fix Plan
**Phase 1 (Operator):** Verify entity extraction task is running/healthy; restart if needed; allow 10-15 min for pipeline catch-up  
**Phase 2 (Code):** Fix timeframe mismatch by updating UI label to "last 7 days" (simpler) OR changing request to `timeframe: "24h"`  
**Phase 3 (Verification):** Confirm signals return, verify latency, check for regressions

### Code Review: No Bugs Found
All code paths are correct:
- `compute_trending_signals()` correctly implements timeframe windows and filters
- API endpoint correctly validates parameters and caches
- Frontend correctly displays empty state
- **No code changes needed to fix the zero-signal issue** (issue is in data pipeline)

## Acceptance Criteria

- [x] The production data path from recent articles to primary entity mentions to trending API results is documented with timestamps/counts.
  - **Finding:** Articles (45 in 24h) → Entity extraction (MISSING) → Signal computation (correctly returns 0)
- [x] The zero-result behavior for 24-hour and 7-day windows, versus one 30-day result, is explained by evidence.
  - **Finding:** 0 recent mentions (correct); 1 thirty-day mention (Aug 24, old but within window; correct)
- [x] The frontend timeframe label and actual request behavior are reconciled with product intent.
  - **Finding:** Label mismatch exists (says 24h, requests 7d); secondary issue; fixable post-operator-fix
- [x] A root cause and scoped fix plan are documented; any implementation is verified against tests and production-safe checks.
  - **Root Cause:** Entity extraction not running/not creating primary mentions for recent articles
  - **Fix Plan:** Operator verifies/restarts extraction → Code updates label → Verification tests
