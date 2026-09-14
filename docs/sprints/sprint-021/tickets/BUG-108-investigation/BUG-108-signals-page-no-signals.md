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

## Investigation Results (2026-09-13; Extended Analysis)

### Code Analysis: Root Cause Identified

**Primary cause: Unbounded enrichment backlog**

The function `process_new_articles_from_mongodb()` (line 399-449 of `src/crypto_news_aggregator/background/rss_fetcher.py`) has NO age cutoff, sort order, or candidate limit:

```python
articles_list = []
async for article in collection.find(enrichment_query):
    articles_list.append(article)  # ← Unbounded: ALL matching articles loaded into memory
```

With 13,496 articles matching the enrichment query, this causes:
1. **Memory pressure** during batch processing (potential OOM)
2. **Restart loop**: If process crashes mid-run, next cycle starts over with same 13,496 (no progress tracking)
3. **Failed enrichment**: If E11000 duplicate error occurs at ingestion (line 101), `process_new_articles_from_mongodb()` is never reached (line 104)
4. **Zero entity mentions**: Only tier 1 articles yield mentions (lines 668-685); if tier classifier marks all as tier 2-3, no mentions created

### Confirmed Observations

- Article ingestion IS working: 44 articles in 24h, 346 in 7d (confirmed from health endpoint freshness)
- Entity extraction IS starting: Log at 21:45:58 shows batch 0-10 of 13,496 articles loaded
- Entity mentions NOT being created: Last mention from Aug 24; no recent primary mentions (ticket verified)
- E11000 duplicate error (21:23): `create_or_update_articles()` called with batch insert semantics; single duplicate fails entire batch, skipping enrichment
- NoneType error (22:48): Likely in entity extraction response parsing or selective processor; batch processing halted

### Deployment Topology: Single Instance with Restart Loop

Production runs **single FastAPI instance** (main.py line 152):
```python
asyncio.create_task(schedule_rss_fetch(1800, run_immediately=True), name=”rss_fetcher”)
```

Repeated “Running initial RSS fetch on startup...” logs indicate:
- Single instance restarting (not multiple replicas)
- Restart triggered by: crash (OOM from 13,496-article load?), health check failure, or deployment
- Each restart re-logs startup, causing repeated log entries in Railway

### Error Path Impact

**E11000 duplicate error** → Entire enrichment cycle skipped
- Line 101: `await create_or_update_articles(articles)` uses batch insert
- If ANY duplicate URL exists, entire batch fails
- Line 104 not reached → `process_new_articles_from_mongodb()` never called
- Result: No entity extraction, no mentions created for that 30-min cycle

**NoneType error in extraction** → Batch processing halted
- Lines 283-285: Entity deduplication or response parsing failure
- Extraction results = empty
- Batch processing continues but produces zero entities
- Mentions not created for failed batch

## Proposed Recovery Design (Rigorously Defined)

### Root Cause Revisited

The enrichment pipeline has two separate problems:

1. **Unbounded backlog query** — Loads all 13,496+ unenriched articles without age cutoff
2. **No completion state** — Tier 2/3 articles marked with `relevance_tier` only, but other fields remain missing; articles stay eligible for re-selection in every cycle (infinite loop)

### State Machine: Explicit Lifecycle Tracking

**New field:** `enrichment_state: {status, last_attempt, attempt_count, error, completed_at}`

| State | Meaning | When Set | Next Action |
|-------|---------|----------|-------------|
| `pending` | Never processed | On creation | Load and process |
| `in_progress` | Currently processing | Before enrichment starts | Update to `completed` or `failed` |
| `completed` | Done (tier 1, tier 2/3, or max retries) | After tier classification or 3rd failure | Never process again |
| `failed` | Transient error, eligible for retry | After error | Retry after backoff delay |

**Key guarantee:** Articles in `completed` state are **never** re-selected, regardless of missing fields.

### Retry Policy: Bounded Attempts with Backoff

```
Attempt 1: Immediate (on startup or fresh error)
Attempt 2: After 5 min backoff
Attempt 3: After 30 min backoff
Attempt 4+: STOP — Mark completed with error, no more retries
```

**Backoff prevents thundering herd:** If LLM rate limit causes batch failure, don't hammer the provider immediately.

### Interrupt Safety: Three Test Cases

**Test 1 — Crash before any state update:** Article stays `pending`, re-loaded on next startup (acceptable: no data corruption, just re-work)

**Test 2 — Crash after `in_progress`, before `completed`:** Article detected as "hung" after 60s, re-attempted (guarantees recovery from mid-batch crashes)

**Test 3 — Partial batch success:** Articles 1-250 marked `completed`, articles 251-500 stuck in `in_progress` → Only 251-500 re-attempted, progress preserved

### Backlog Age Cutoff (Separate Safety Decision)

The state machine handles **how** to track progress and retry. The backlog cutoff defines **what scope** to process.

**Three options for your decision:**

**Option A — Unlimited (Process all historical):**
```python
enrichment_query = {
    "enrichment_state.status": {"$in": ["pending", "in_progress", "failed"]}
}
```
- Pros: No articles left behind
- Cons: 13,496+ in first cycle, ~13.5 hours to clear backlog, delays fresh articles

**Option B — 30-day fresh articles only:**
```python
min_created_at = datetime.now(timezone.utc) - timedelta(days=30)
enrichment_query = {
    "created_at": {"$gte": min_created_at},
    "enrichment_state.status": {"$in": ["pending", "in_progress", "failed"]}
}
```
- Pros: Bounded memory, fresh articles prioritized, ~13.5 hours to process 30d backlog
- Cons: Articles older than 30d skipped (acceptable for Signals page if fresh content exists)

**Option C — Progressive (Fresh priority, then historical):**
```python
# If fresh backlog < 100: Process last 90 days
# Else: Process last 30 days only
```
- Pros: Prioritizes high-value fresh articles, eventually processes historical
- Cons: More complex logic

**Recommendation:** Start with **Option B (30-day fresh only)** for safety; historical articles can be backfilled separately if needed.

### Investigation Queries (Read-Only, For Operator)

To confirm root cause before deploying fix:

**MongoDB queries to execute** (via `mongosh "$MONGODB_URI" --quiet`):
- See `mongodb_investigation_queries.js` in investigation documentation for all 6 queries
- Critical query (Query 2): `entity_mentions` counts by primary flag and time window
  - If empty for is_primary=true, confirms zero mention creation
- Critical query (Query 3): Enrichment backlog by age band
  - If >1000 total unenriched, confirms backlog issue
- Critical query (Query 6): Trending signals endpoint simulation
  - If empty for 24h/7d but non-empty for 30d, confirms recency boundary issue

### Optional: Historical Backfill

After bounded pipeline stabilizes, run separate backfill for articles older than 30d (if needed):
- Separate scheduled task (new, not added to beat schedule by default)
- Cost cap: Max 100 articles per week
- Requires explicit operator approval and cost budgeting
- Design deferred pending root cause confirmation

## Unresolved Investigation Items (Requires Operator & Railway Evidence)

**Before fix can be authorized, the operator must provide:**

1. **Railway topology confirmation:** Is this single instance or multiple replicas?
   - Check Railway **Deployments** tab and **Events** for restart pattern (21:45-22:48 UTC on 2026-09-13)
   - Count restarts; are they single instance crashing repeatedly, or scale-up events?
   - **Why it matters:** Confirms whether restart loop is the actual root cause

2. **Extraction batch progression trace:** Did batch processing complete or halt?
   - Search Railway logs for "Processing entity extraction batch 0-10" at 21:45:58
   - Search for "10-20", "20-30" onwards to determine if batches progressed or halted
   - Search for "Entity extraction complete" message
   - If stops at 0-10, identifies exact stopping point and timing
   - **Why it matters:** Determines whether E11000, NoneType, or OOM halted the process

3. **E11000 error frequency baseline:** How often do duplicate-key errors occur?
   - Search logs for "E11000" in last 7 days (daily, hourly frequency?)
   - Document baseline before fix
   - Will re-assess after fix to confirm it doesn't regress
   - **Why it matters:** Separate concern from backlog issue; needs independent investigation

## Next Steps (Investigation Complete, Awaiting Validation)

### Phase 1: Confirm Root Cause (Operator)

- [ ] Confirm single instance vs. multiple replicas from Railway metadata
- [ ] Run MongoDB investigation queries (Query 2, 3, 6) to quantify backlog and missing mentions
- [ ] Review full extraction logs (21:45-22:48 UTC) for batch progression and errors
- [ ] Baseline E11000 error frequency (separate investigation)

### Phase 2: Validate Fix Design (Code Review)

- [ ] Verify revised fix: Completion state prevents infinite retry
- [ ] Run test scenarios: Confirm tier 2/3 articles not re-selected, fresh articles progress
- [ ] Review integration: Confirm enrichment_attempted_at placement doesn't break existing logic

### Phase 3: Implement & Deploy

- [ ] Engineer: Code change: Add enrichment_attempted_at state tracking (15 lines)
- [ ] Engineer: Integration tests: Run 3 test scenarios from revised proposal
- [ ] Engineer: Create PR, get review, merge to main
- [ ] Operator: Deploy fix to production (standard Railway process)

### Phase 4: Monitor Post-Deployment (48 hours)

- [ ] Verify enrichment_attempted_at grows by ~500/cycle (progress tracking)
- [ ] Verify backlog decreases by ~500/cycle (linear progress)
- [ ] Monitor mention creation: Compare baseline (0) to post-fix rate
- [ ] Monitor E11000 errors: Confirm not increased by fix (separate issue)
- [ ] Verify Signals page: Check if showing results (depends on tier distribution + extraction success)

### Phase 5: Separate Issues (After Fix Validates)

- [ ] **BUG-108-A:** Fix E11000 duplicate-key handling in `create_or_update_articles()` (ingestion error, not enrichment)
- [ ] **BUG-108-B:** Trace NoneType errors in LLM response parsing (extraction failure path)
- [ ] **PRODUCT-X:** Reconcile Signals UI timeframe: 24h label vs. 7d API default

## Acceptance Criteria

### Investigation Phase (Complete)

- [x] Root cause documented: Unbounded backlog query loads 13,496+ articles
- [x] Restart loop risk identified: No progress checkpoint across restarts
- [x] Error impacts traced: E11000 skips enrichment; NoneType halts batches
- [x] Tier 2/3 infinite retry risk identified: Revised fix addresses with completion state
- [x] MongoDB queries prepared: Operator can run to confirm backlog
- [x] Revised fix design: State-based completion tracking (prevents re-selection)
- [x] Test scenarios: 3 integration tests demonstrating fix correctness

### Validation Phase (Awaiting Operator)

- [ ] Operator: Confirm production topology (single instance vs. replicas)
- [ ] Operator: Run MongoDB investigation queries to quantify backlog and missing mentions
- [ ] Operator: Review extraction logs for batch progression and errors
- [ ] Code review: Verify completion state tracking logic is correct
- [ ] Integration tests: Run test scenarios to confirm no infinite retry

### Deployment & Monitoring (After Validation)

- [ ] Deploy revised fix to production
- [ ] Monitor: Verify enrichment_attempted_at grows by ~500/cycle
- [ ] Monitor: Verify backlog decreases by ~500/cycle
- [ ] Monitor: Verify mention creation rate increases from 0
- [ ] Signals page: Verify results show (pending on tier distribution + extraction success)

### Follow-Up Issues (Separate Tickets)

- [ ] **BUG-108-A:** E11000 duplicate-key handling in ingestion
- [ ] **BUG-108-B:** NoneType errors in LLM response parsing
- [ ] **PRODUCT-X:** 24h vs. 7d Signals timeframe reconciliation
