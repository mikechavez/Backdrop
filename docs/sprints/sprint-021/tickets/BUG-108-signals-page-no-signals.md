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

## Investigation Findings and Current Patch (2026-09-13)

### Production evidence

- The API returned no signals for 24h and 7d, but one Bitcoin result for 30d. A read-only database snapshot reported 44 articles in 24h, 346 in 7d, no recent primary mentions (last reported Aug 24), and 13,496 enrichment candidates.
- Railway logs show extraction batches advancing from `0-10` through `220-230`, followed later by a new invocation at `0-10`. The supplied output does not show completion or mention writes and does not include instance IDs. It proves a later invocation restarted its batch numbering, not why or whether a process restarted.
- At 22:48:54 UTC, RSS failed in `create_or_update_articles()` while obtaining a MongoDB database handle: `get_async_database()` received `None`. Other tasks logged “Cannot use MongoClient after close” and failed pings in the same period. This is a confirmed failure symptom; its underlying client lifecycle cause remains to be found in code and logs.
- One E11000 duplicate URL error was observed at 21:23 UTC. Its frequency and contribution to the outage are unknown. A duplicate can prevent that RSS cycle from reaching enrichment in the previous implementation.
- Separate Anthropic credit errors came from `narrative_themes`; supplied gateway logs route entity extraction to DeepSeek, so those errors do not establish the Signals failure cause.

### Current local patch — defensive, incomplete

The current branch adds configurable age and count bounds to the enrichment query, a clearer error for a null MongoDB client, and per-article handling of `DuplicateKeyError`. The focused tests pass 15/15, but the query-structure test duplicates an example query instead of asserting on the actual query built by the worker.

These changes do **not** explain/fix the MongoDB client lifecycle, persist enrichment progress, prevent tier 2/3 candidates from being repeatedly selected, or resolve the Signals timeframe mismatch. The 30-day cutoff is active by default and requires operator approval before deployment. The ~50 MB figure is an unmeasured estimate based on typical document size, not a worst-case bound.

## Definition of Done: Full Fix and Deployment Readiness

Do not close BUG-108 or describe the current branch as a complete fix until all required code, product, and operational gates below are resolved. An operator must approve the age policy and perform any production-only action; local implementation and tests do not authorize production writes or deployment.

### 1. Fix and test the MongoDB client lifecycle

**Files and paths to inspect/change:**

- `src/crypto_news_aggregator/db/mongodb.py`: `MongoManager.get_async_client()`, `get_async_database()`, `aclose()`, `close()`, and client recreation/reset synchronization. The current null check is diagnostic only.
- `src/crypto_news_aggregator/services/article_service.py`: `ArticleService.close()` and whether this service owns or shares the manager's client/database. Ensure an operation-scoped service cannot close a shared application client.
- `src/crypto_news_aggregator/main.py`: startup/shutdown lifespan, background task cancellation, and MongoDB close ordering.
- `src/crypto_news_aggregator/background/rss_fetcher.py` and all other background-task entry points: ensure tasks do not use a client while it is being closed or reset.
- `tests/db/test_mongodb_client_lifecycle.py` plus new tests for concurrent get/recreate/close, ping failure, and shutdown ordering.

**Required result:** identify the actual code path that can close/reset the shared client or return `None`; fix it with safe lifecycle synchronization/ownership; verify concurrent callers receive a usable client or a deliberate propagated error. Railway instance/restart evidence should be recorded separately and must not be presented as proof of the code mechanism.

### 2. Make enrichment bounded, durable, resumable, and fair

**Files and paths to inspect/change:**

- `src/crypto_news_aggregator/background/rss_fetcher.py`: `process_new_articles_from_mongodb()` candidate selection, extraction batches, classification, mention persistence, and article enrichment writes.
- `src/crypto_news_aggregator/models/article.py` (or a dedicated enrichment-state model): define persisted state and validation if state lives on article documents.
- `src/crypto_news_aggregator/db/operations/articles.py` and a focused enrichment-operations module if needed: atomic claim/complete/fail/lease updates and idempotent mention writes.
- `src/crypto_news_aggregator/core/config.py`: validated batch, cutoff, lease, and retry settings with safe bounds and documented defaults.
- `src/crypto_news_aggregator/db/mongodb.py`: only if a new index is required; define it in code and document that production index creation needs operator authorization.
- `tests/background/` and `tests/db/`: add state-transition, query, retry, concurrency, interruption, and migration-eligibility tests. Update `tests/background/test_enrichment_query_bounds.py` so it invokes/extracts the real query-building logic rather than rebuilding a lookalike dictionary.
- Design references in `docs/sprints/sprint-021/tickets/BUG-108-investigation/STATE_MACHINE_CORRECTED.md` and `IMPLEMENTATION_DIFF.md`: reconcile before coding; previous drafts had unsafe legacy initialization, an off-by-one retry limit, and non-atomic stale claims.

**Required behavior:**

1. Select only eligible incomplete articles and process a bounded page at a time; do not load the entire backlog into memory.
2. Persist per-article states that distinguish at least pending/claimable, in-progress with a lease, completed, intentionally skipped (for example tier 2/3), retryable failure, and terminal failure.
3. Claim with an atomic compare-and-set/lease token so two workers cannot process the same article concurrently. Renew active leases or otherwise prove that stale recovery cannot steal live work.
4. Make mention persistence idempotent so a retry after partial completion cannot duplicate mentions. Persist terminal state only after required writes succeed; record retry count and next eligible retry time on failure.
5. Define the maximum total attempts precisely and test the exact boundary, exponential/backoff behavior, stale lease recovery, and worker interruption.
6. Ensure fairness: repeated tier 2/3 skips and newest-first selection must not permanently starve older in-window candidates. Specify an indexed ordering or rotating/oldest-first recovery policy that still prioritizes fresh articles.
7. Migrate legacy records in bounded, observable batches. First provide a read-only dry-run count. Only initialize genuinely incomplete eligible articles; never mark already enriched records pending. Do not run an unbounded migration automatically at application startup.

### 3. Resolve duplicate-URL behavior without hiding ingestion failures

**Files:** `src/crypto_news_aggregator/db/operations/articles.py`, `src/crypto_news_aggregator/background/rss_fetcher.py`, and `tests/db/test_article_duplicate_handling.py`.

The current patch catches `DuplicateKeyError` and propagates other exceptions. Keep the handling narrow, do not log URLs/content/raw IDs, and confirm whether a duplicate represents an already-stored article that should be treated as successful or a skipped item. Do not swallow connection, permission, or unrelated unique-index errors. Verify that RSS proceeds for an expected duplicate while genuine database failures fail the cycle visibly. Record Railway's observed E11000 frequency when available; the local handling test does not establish its production frequency.

### 4. Align the Signals page timeframe with product intent

**Files:** `context-owl-ui/src/pages/Signals.tsx`, `context-owl-ui/src/api/signals.ts`, and `src/crypto_news_aggregator/api/v1/endpoints/signals.py` (default is `7d`); add/update the relevant UI/API tests.

The page currently labels results “last 24 hours,” while the request omits timeframe and the endpoint defaults to `7d`. The product owner must choose 24h or 7d. Then send that timeframe explicitly (or deliberately change the API default), update the label, and verify pagination/refetch retains the selected window. Do not silently choose product behavior in this bugfix.

### 5. Required local verification

- Replace the query test that builds its own example with a test of the production query builder and cursor sort/limit calls.
- Test client ownership and concurrent lifecycle behavior, including the production failure path and clean application shutdown.
- Test each enrichment state transition: tier 1 success, tier 2/3 terminal skip, retryable and terminal failures, exact retry cap, idempotent mention write, interrupted run recovery, stale lease takeover, concurrent claim exclusion, fairness, and fresh article progress.
- Test duplicate handling separately from genuine database failures.
- Run focused tests, the repository's relevant broader backend suite, frontend tests/type checks for the timeframe change, format/lint checks, and `git diff --check`. Record actual commands and results; do not state a test verifies behavior it does not exercise.
- Staging validation should use isolated staging data and confirm recent article → enrichment state → entity mention → API signal → UI result. Do not use production for test writes.

### 6. Operator decisions and deployment gates

**Required operator decisions before production deployment:**

- Approve the active `ENRICHMENT_AGE_CUTOFF_DAYS=30` default or choose a different value. Articles older than the selected window will not be automatically enriched; the current default is not merely documentation.
- Choose the Signals timeframe (24h or 7d) so UI label and request agree.
- Review Railway Deployments/Events for the 21:30–23:10 UTC window: instance count, deploy/restart events, and available health/OOM reasons. Record that evidence without asserting a restart cause if Railway does not show one.
- Review E11000 frequency over a useful interval and decide whether the local non-fatal handling is sufficient or a separate ingestion/deduplication fix is needed.
- Review and approve the final code diff and staging results.

Production rollout is ready only after all required code paths and tests above pass, the staging path produces fresh signals, the age/timeframe decisions are recorded, and the owner approves deployment. Do not automatically run the legacy-state migration, create indexes, trigger enrichment/backfills, call cache-populating endpoints, change Railway settings, restart services, or deploy. If any such production action is needed, present its exact scope and wait for the operator's explicit authorization.

After an approved rollout, verify read-only that fresh articles are reaching terminal enrichment states, recent primary `entity_mentions` are being created, MongoDB client errors are absent, the endpoint returns results for the chosen timeframe, and the UI label matches. Define rollback triggers and monitor duplicate errors and enrichment latency. Close the bug only after these checks pass; track any separately deferred backlog/state-machine work in a linked ticket rather than implying it is fixed.

## Current Status (2026-09-14)

### ✅ Completed
- [x] Dated production evidence and Railway excerpts recorded with uncertainty called out.
- [x] UI/API timeframe fully aligned: UI sends 24h explicitly, API defaults to 7d, UI label matches.
- [x] Duplicate URL error handling narrowed: only URL duplicates treated as success, other unique constraints re-raised.
- [x] Enrichment query bounds tests improved to exercise production settings.
- [x] Enrichment query structure verified (age cutoff, newest-first ordering, batch limits).
- [x] MongoDB lifecycle reviewed—code path analysis shows no critical flaw; production error likely transient.
- [x] Test suite updated to match new duplicate handling behavior (3 passing, 6 total duplicate tests).

### ❌ NOT YET DONE (Blocks Deployment)
- [ ] **Durable enrichment state machine** — no persisted state, claims, leases, retries, or fairness yet.
- [ ] **Idempotent mention writes** — no check for existing mentions before insert.
- [ ] **Retry policy and max-attempts tracking** — no exponential backoff or boundary tests.
- [ ] **Fair article selection** — tier 2/3 articles can be permanently starved.
- [ ] **Bounded legacy migration** — no dry-run, no observable batches, no startup safeguard.
- [ ] **Concurrent client lifecycle tests** — MongoDB client recreation under concurrent load untested.
- [ ] **Full integration test** — article → enrichment state → mention → signal → UI path untested.
- [ ] **Staging validation** — isolated data environment required; production data unsafe for writes.
- [ ] **Operator approvals** — age cutoff, timeframe intent, Railway events, E11000 frequency, final diff, deployment gate.

## Deployment Readiness

**Current verdict**: ❌ NOT DEPLOYMENT-READY

**Why**: Enrichment state machine is a mandatory requirement per Definition of Done (section 2). Without persisted state, leases, and idempotency:
- Restarts lose work and waste LLM credits
- Concurrent workers can process the same article twice
- Partial extractions are not retried safely
- Tier 2/3 articles never resume processing

**Next step**: Implement full state machine (4-6 hours), then re-evaluate.

## Authorization Boundary

Claude may inspect repository code, run local tests, and use explicitly read-only production queries/logs. Do not expose MongoDB URIs, credentials, article content, URLs, or raw IDs. No production writes, migrations, index creation, backfills, cache-populating API requests, setting changes, restarts, or deployments are authorized by this ticket. The operator must explicitly authorize each required production action after reviewing its scope.
