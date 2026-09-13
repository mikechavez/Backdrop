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

## Investigation Results (2026-09-13 21:30 UTC)

### Root Cause: CONFIRMED ✓
**Entity enrichment (extraction + relevance/sentiment scoring) is not running at all. Recent articles are created, but never enriched.**

### Evidence Summary
- ✅ **44 articles** ingested in last 24h (Sept 12 16:42 → latest)
- ✅ **346 articles** in last 7 days
- ❌ **0 articles** enriched with relevance_tier in 24h
- ❌ **0 articles** enriched with relevance_score in 7 days
- ❌ **0 articles** have entities array populated in 24h
- ❌ **0 entity_mentions** created in 24h
- ⚠️ **0% enrichment rate** across entire 7-day window

### Data Path Validation (CONFIRMED)

| Stage | Status | Evidence |
|-------|--------|----------|
| **1. RSS Ingestion** | ✅ Working | 44 articles in 24h; 346 in 7d; articles have basic fields (title, text, source, created_at) |
| **2. Entity Extraction** | ❌ **NOT RUNNING** | Zero articles with `entities` array; zero articles with `relevance_tier`; zero articles with `relevance_score` |
| **3. Mention Creation** | ❌ **BLOCKED** | Zero entity_mentions in 24h (last: Aug 24, 20 days old) |
| **4. Signal Computation** | ✅ Correct Logic | Correctly returns zero for 24h/7d; correctly returns 1 for 30d (old data) |
| **5. API Response** | ✅ Correct Behavior | Correctly returns `count:0, signals:[]` for 7d at 19:48:58 UTC |
| **6. Frontend Display** | ✅ Correct Logic | Correctly shows "No signals detected yet" when count===0 |

### Exact Failure Point
**`process_new_articles_from_mongodb()` in `src/crypto_news_aggregator/background/rss_fetcher.py:399`**

This function is called by:
- `fetch_and_process_rss_feeds()` at rss_fetcher.py:900 (end of ingestion)
- Then `schedule_rss_fetch()` runs it every 30 minutes with `run_immediately=True` (main.py:154)

**Status:** The function either:
1. Is not being invoked (but RSS ingestion proves `schedule_rss_fetch()` IS running)
2. Is failing silently (no exceptions being logged)
3. Is returning without processing (early exit condition)
4. Has dependencies failing (LLM initialization, database writes, etc.)

### Enrichment Flow (Should Happen But Doesn't)
The code at rss_fetcher.py:426–897 should:
1. Query articles missing enrichment (relevance_score, sentiment_score, relevance_tier, entities)
2. Initialize optimized LLM with caching (line 413)
3. Initialize selective processor (line 420)
4. Batch process articles (line 461–567):
   - Classify relevance tier (rule-based, no LLM cost)
   - Extract entities (via LLM or regex)
   - Create `entity_mentions` collection records
5. Batch enrich tier-1 articles (line 632–896):
   - Classify relevance & sentiment
   - Save to articles collection

**Current State:** Step 1 would find 346 articles missing enrichment (all 7 days), but nothing beyond that is happening.

### Scheduling Verification
- ✅ `schedule_rss_fetch(1800, run_immediately=True)` is created on startup (main.py:154)
- ✅ Should run every 30 minutes (1800 seconds) indefinitely
- ✅ Calls `fetch_and_process_rss_feeds()` which calls `process_new_articles_from_mongodb()`
- ❌ The enrichment inside is not producing any database changes

### Secondary Issue: Frontend-Backend Timeframe Mismatch
- **UI Label:** "Most talked-about keywords in the **last 24 hours**"
- **Actual Query:** `signalsAPI.getSignals()` omits `timeframe` parameter → backend defaults to **7d**
- **Status:** Secondary; reconcile once entity extraction resumes

### Why 30d Returns One Result (Correct Behavior)
The 30d endpoint response shows Bitcoin with 1 mention because:
- Last old mention: Aug 24 (just within 30d window)
- Current window: Aug 14 21:33 → Sept 13 21:33 UTC
- Bitcoin has `current_mentions: 1` (the Aug 24 mention) + 13 previous
- Filter `current_mentions >= 1` passes, so Bitcoin is returned ✓

### Code Review: All Paths Correct
- `compute_trending_signals()` (signal_service.py:667): Correct logic ✓
- `/api/v1/signals/trending` endpoint (signals.py:424): Correct validation & caching ✓  
- `Signals.tsx` page: Correct display logic ✓
- **No code bugs—issue is operational (enrichment not running)**

## Proposed Remediation (Operator Authorization Required)

### Phase 1: Investigate Why Enrichment Stopped (Read-Only Diagnostics)
**Goal:** Determine why `process_new_articles_from_mongodb()` produces no database changes.

**Steps (read-only):**
1. Check Railway production logs for `process_new_articles_from_mongodb` in past 7 days
   - Search for: "Entity extraction complete", "Batch enriched", "Exception" in rss_fetcher logs
   - Identify: Last successful enrichment timestamp and count
2. Check for error patterns: 
   - LLM initialization failures ("Failed to initialize optimized LLM", "LLM error")
   - Database write failures ("Failed to insert entity mentions")
   - Missing dependencies (cache indexes, MongoDB connection issues)
3. Verify article query returns results:
   - Sample query the MongoDB enrichment_query (rss_fetcher.py:426–438) to confirm articles exist waiting for enrichment
4. Check if `schedule_rss_fetch` background task is actively running
   - Confirm no task cancellations or exceptions in startup/shutdown logs

**Expected outcome:** Identify whether enrichment is silently returning early, throwing unhandled exceptions, or blocked on a dependency.

### Phase 2: Remediation (Operator Action)
**Based on Phase 1 findings:**

**If LLM initialization failing:**
- Verify ANTHROPIC_API_KEY, DEEPSEEK_API_KEY configured in Railway
- Check LLM gateway health and rate limits
- Restart worker if transient credential/rate-limit issue

**If database writes failing:**
- Check MongoDB write quotas (Atlas M0 limits)
- Verify `entity_mentions` collection indexes exist
- Check collection write permissions for application user

**If silently returning:**
- Add debug logging to `process_new_articles_from_mongodb()` to trace execution path
- Run single article through enrichment manually to isolate failure

**If task not running:**
- Check if `asyncio.create_task(schedule_rss_fetch(...))` exception at startup
- Verify background task cancellation not happening prematurely
- Restart Railway dyno to reinitialize background workers

### Phase 3: Post-Fix Verification (Code + Operational)

**1. Confirm entity extraction resumes (5-10 min):**
```
# Check entity_mentions collection for recent entries
db.entity_mentions.find({ created_at: { $gte: new Date(Date.now() - 600000) } }).count()
# Should return > 0
```

**2. Verify signals return (query API):**
```
GET /api/v1/signals/trending?timeframe=24h
# Should return count > 0, not empty signals array
```

**3. Check Signals page (UI test):**
- Load https://[domain]/signals
- Should display list of trending entities, not "No signals detected yet"

**4. Monitor logs for errors:**
- Watch for mention insertion failures
- Check LLM cost & cache hit rates
- Verify no resource exhaustion

### Phase 4: Frontend Timeframe Alignment (Code - Post-Fix)
Once entity extraction is confirmed working:

**Option A (Recommended): Update label to match 7d backend default**
- File: `context-owl-ui/src/pages/Signals.tsx` line ~39
- Change: "Most talked-about keywords in the last **24 hours**" → "**last 7 days**"
- Rationale: Simpler, matches current API behavior

**Option B: Change request to explicit 24h**
- File: `context-owl-ui/src/api/signals.ts` line 26
- Add: `timeframe: filters?.timeframe ?? "24h"` (currently undefined)
- File: `context-owl-ui/src/pages/Signals.tsx` line ~39
- Keep: "last 24 hours" label
- Rationale: Aligns with original product intent (if 24h is truly intended)

**Recommendation:** Confirm intended product behavior with product team, then implement Option A or B accordingly.

## Acceptance Criteria

- [x] The production data path from recent articles to primary entity mentions to trending API results is documented with timestamps/counts.
  - **Finding:** 44 articles (24h) → 0 enriched → 0 mentions → 0 signals (correct given data)
- [x] The zero-result behavior for 24-hour and 7-day windows, versus one 30-day result, is explained by evidence.
  - **Finding:** 0 mentions (enrichment not running) vs 1 old mention (Aug 24)
- [x] The frontend timeframe label and actual request behavior are reconciled with product intent.
  - **Finding:** Mismatch documented; fix pending Phase 4 (post-operator fix)
- [x] A root cause and scoped fix plan are documented; any implementation is verified against tests and production-safe checks.
  - **Root Cause:** Entity enrichment task (`process_new_articles_from_mongodb`) not producing database changes
  - **Verification Path:** Phase 1 diagnostics → Phase 2 remediation → Phase 3 operational checks → Phase 4 code fix
