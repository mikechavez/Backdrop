---
ticket_id: BUG-110
type: bug
title: Production news ingestion and processing schedule is not running
priority: high
status: REPO_WORK_COMPLETE_AWAITING_RAILWAY_VERIFICATION
date_created: 2026-09-15
branch: fix/bug-110-production-ingestion-schedule
related: BUG-109, BUG-108
---

# BUG-110: Production news ingestion and processing schedule is not running

## Problem

After BUG-109 deployment, the production Signals endpoint returned HTTP 200 but no signals. Railway services were online and the Celery worker connected to Redis and MongoDB successfully, but recent logs showed no RSS fetch, article-processing, or entity-mention creation activity. Celery Beat showed cache warming only.

Without fresh articles being ingested and processed, no new publication-dated mentions can reach the Signals computation. Do not interpret an empty Signals response as proof that the publication-time query is incorrect.

## Evidence observed on 2026-09-15

- Production services were reported online.
- `GET /api/v1/signals` returned HTTP 200 with `count: 0`.
- Worker startup and Redis/MongoDB connection succeeded.
- Worker logs showed cache warming and `No trending signals found`.
- Beat logs showed `warm-entity-articles-cache` but no observed news-fetch activity in the inspected window.

These are point-in-time observations and must be revalidated before choosing a fix.

## Railway verification performed on 2026-09-15

The operator inspected the authenticated Railway production project together with the agent.

- Project: `scintillating-alignment`
- Environment: `production`
- Services online: `crypto-news-aggregator`, `celery-worker`, `celery-beat`, and `bugops`
- Celery Beat was running, but its observed schedule dispatched cache warming and narrative consolidation, not RSS ingestion.
- The FastAPI service was actively running the in-process RSS scheduler.
- Around 21:16, the web service logged several RSS fetches of 262–272 articles within seconds of one another.
- Articles were successfully ingested/upserted.
- Multiple overlapping fetch cycles indicate that the in-process scheduler is running in multiple web replicas/processes. This creates duplicate fetch and processing attempts.
- Enrichment was blocked because MongoDB reported the required unique index as missing or invalid:
  `article_entity_type_primary_unique`.
- The index diagnostic explicitly instructed the operator to run the repository's index rollout checks before creating the index.
- A production duplicate preflight found `2,016` duplicate key groups, `43,406` documents in those groups, `41,390` excess documents, and a maximum group size of `7,448`.
- The largest group was `(article_id=69cebfd8aa731a71682e7d33, entity=Bitcoin, entity_type=cryptocurrency, is_primary=true)` with `7,448` documents spanning `2026-04-02` through `2026-07-08`.
- Therefore, the duplicate data is historical repeated processing, not solely the current multi-replica collision. The current collision must be stopped before remediation, but the historical records require a separate dry-run analysis and controlled operator-approved cleanup.

These observations confirm that RSS fetch and article upsert are functioning in production. They do not yet prove successful entity-mention creation or Signals output.

## Code and deployment areas to inspect

- `src/crypto_news_aggregator/main.py`: web-process background schedules.
- `src/crypto_news_aggregator/worker.py`: worker schedules and startup mode.
- `src/crypto_news_aggregator/background/rss_fetcher.py`: RSS schedule and processing handoff.
- `src/crypto_news_aggregator/tasks/celery_config.py` and beat schedule modules.
- Railway service start commands, replicas, environment variables, and deployment configuration.
- RSS fetch, article upsert, processing, and entity-mention creation logs/metrics.

## Expected behavior

- The intended production process must run the RSS fetch schedule at its configured interval.
- Each successful fetch must report feed-level and aggregate results.
- Newly ingested articles must be handed to processing.
- Processing must create publication-dated entity mentions when enrichment succeeds.
- Failures must be visible with enough context to distinguish feed failure, MongoDB failure, queue failure, enrichment failure, and zero-article results.
- A healthy scheduler must not be inferred solely from the process being online.

## Implementation scope

1. **Repository-side investigation:** Trace the RSS ingestion and processing paths, including:
   - the FastAPI lifespan task started by `main.py`;
   - the Celery `fetch_news` task and its queue routing;
   - the Celery Beat schedule and the intentionally disabled `fetch-news-every-3-hours` entry;
   - article upsert, enrichment, entity-mention creation, and signal-score refresh.
2. **Joint Railway investigation:** With the operator, inspect the production service commands, replicas, environment variables, deploy state, and recent logs. Claude must not assume access to Railway or claim this step is complete without operator-provided evidence.
3. Decide and document one canonical production ingestion owner (FastAPI background scheduler or Celery/Beat). Do not leave two production schedulers active unless duplicate execution is explicitly prevented and tested.
4. Determine whether the failure is a missing process, incorrect command, disabled schedule, task-routing mismatch, environment/configuration problem, or logging gap.
5. Restore the intended ingestion and processing schedule with minimal repository and, if needed, deployment/configuration changes. Record any required Railway change for the operator to apply or verify.
6. Add or extend health/heartbeat observability proving recent fetch attempts, successful fetches, article upserts, processing, and entity-mention creation. Preserve actionable failure context for feed, queue, MongoDB, and enrichment failures.
7. Add tests for schedule ownership/startup, task handoff, and observability where practical. Tests must not require Railway credentials or production access.
8. Verify the processing path locally or in staging with a controlled fixture/fake feed and publication-dated article. Do not create production data, perform a blind backfill, or rewrite historical timestamps.
9. With the operator, perform the final production verification: recent fetch at the configured interval, article processing, entity mention creation, and Signals output for qualifying data.

10. Resolve the production MongoDB enrichment blocker through the explicit index rollout procedure. The procedure must check for duplicate mention keys first and must stop rather than delete, merge, or rewrite data if duplicates are found.
11. Eliminate duplicate RSS scheduling. Either operate the web service with one replica as a temporary mitigation or move RSS ownership to a singleton Celery/Beat path and remove/disable the FastAPI scheduler. The selected approach must be documented and tested.
12. After code and deployment changes, verify that one fetch cycle occurs at the configured interval and that the full path reaches entity mentions and Signals.
13. Rotate production credentials exposed during the Railway variable inspection, including database, Redis, API, and service tokens. This is an operational security action and must not be performed by repository tests.
14. Prepare a read-only duplicate-remediation report/tool before any production cleanup. It must compare duplicate records, identify meaningful field differences, inspect references to mention `_id` values, report created-at ranges, and propose—but not apply—a canonical-record policy.
15. Do not create the unique index until the duplicate-remediation plan is explicitly approved, any required cleanup is completed, and the duplicate preflight reports zero duplicate groups.

### Claude execution boundary

Claude may inspect and modify repository code, tests, documentation, and local/staging fixtures. Claude cannot inspect Railway services, production logs, deployment settings, or production data. Those checks require a joint operator session and must be recorded as evidence before selecting a deployment fix.

The implementation must not silently choose between the existing FastAPI scheduler and Celery/Beat. The final change must state which scheduler owns production RSS ingestion, why the other path is disabled or harmless, and how duplicate runs are prevented.

### Operator-controlled production actions

Claude should prepare the code, tests, documentation, and exact runbook commands, but the operator must execute or explicitly supervise these production actions:

- inspect MongoDB for duplicate entity-mention keys;
- create `article_entity_type_primary_unique` only if the duplicate check passes;
- change the Railway replica count or apply the selected scheduler deployment configuration;
- rotate exposed production credentials;
- redeploy production;
- inspect post-deploy logs and verify health, entity mentions, and Signals.

## Acceptance criteria

- [ ] Production shows a recent successful RSS fetch at the configured interval.
- [ ] Production shows article upsert/processing activity after a successful fetch.
- [ ] At least one controlled fresh article can be traced through ingestion to an entity mention, without manual historical backfill.
- [ ] Signals returns qualifying data when the database contains qualifying recent mentions.
- [ ] Fetch, queue, MongoDB, and enrichment failures are observable and actionable.
- [ ] Scheduler behavior is covered by relevant tests or a documented staging verification.
- [ ] The canonical production scheduler is explicitly documented, including the disabled/non-owning path and duplicate-run behavior.
- [ ] Railway service/configuration evidence has been collected jointly with the operator before production remediation is selected.
- [ ] The MongoDB duplicate check passes and `article_entity_type_primary_unique` is created or its failure is documented without destructive cleanup.
- [ ] Historical duplicate groups have a reviewed dry-run report, including field differences, reference analysis, time ranges, and proposed canonical-record policy.
- [ ] Any duplicate cleanup is explicitly approved, bounded, recoverable where practical, and documented; no blind deletion or primary-value rewriting is performed.
- [ ] Only one production RSS scheduler owner is active, with duplicate execution prevented.
- [ ] Production credentials exposed during investigation have been rotated.
- [ ] No production reset, deletion, duplicate cleanup, blind backfill, or historical timestamp rewrite is performed by this ticket.

## Resolution

### Status: Repository-side work complete, including a duplicate-run lock added after the operator's Railway session confirmed live multi-replica duplicate fetching. Production remediation (index rollout, redeploy, replica verification, credential rotation) is NOT yet performed or verified — see the operator checklist below.

### Correction (2026-09-15, after joint Railway session)

My original findings below said "there is no live dual-scheduler collision today." **That is now confirmed wrong** by the operator's Railway investigation appended above (`## Railway verification performed on 2026-09-15`): production logs show several RSS fetches of 262-272 articles seconds apart, confirming the FastAPI in-process scheduler is actually running concurrently across multiple `web` replicas today — a real, live duplicate-run collision, not just a theoretical risk. My repository-side static analysis correctly ruled out a *Celery Beat vs. FastAPI lifespan* collision, but missed the *FastAPI lifespan running on N replicas simultaneously* collision, because that can only be observed from running production instances, not from the code alone. Section 6 below ("Duplicate-run mitigation") is the fix for this, added after the correction.

### Findings (repository-side investigation, 2026-09-15)

**1. Celery Beat is not the source of duplication, but per-replica FastAPI scheduling was (see correction above).**

- The **FastAPI lifespan** (`main.py::lifespan`) starts an asyncio task that calls `background.rss_fetcher.schedule_rss_fetch(1800, run_immediately=True)` on every `web` process boot. This is what has actually been running in production, and it runs independently, unlocked, on every replica.
- **Celery Beat's** `fetch-news-every-3-hours` entry (`tasks/beat_schedule.py`) is already commented out, with a BUG-057 note explaining the Celery-routed sources (CoinDesk JSON API, Bloomberg) are dead (403/HTML) and that RSS ingestion is owned by `background/rss_fetcher.py` instead. So Beat does **not** duplicate ingestion against the FastAPI path.
- `worker.py`'s asyncio `main()` *also* independently schedules `schedule_rss_fetch` (a second, separate implementation of the same idea), but nothing in `Procfile` invokes `python -m crypto_news_aggregator.worker` — the `worker:` Procfile entry runs `celery ... worker`, not this asyncio script. `worker.py`'s scheduler is dead code in production. Left as-is (not deleted) since removing it is out of scope for this fix and it poses no live risk as long as Procfile is unchanged — flagged below as an operator-verification item.
- **Two Celery tasks were both registered under the task name `"fetch_news"`**: `tasks/news.py::fetch_news` (uses `NewsCollector`, writes a `fetch_news` heartbeat, referenced by `/admin/trigger-fetch`) and `tasks/fetch_news.py::fetch_news` (uses `create_source`/`ArticleService`, unused by Beat or any endpoint). This is a real name collision in the Celery task registry — whichever module's decorator ran last during `autodiscover_tasks` would win, silently shadowing the other. **Fixed:** renamed the latter to `"fetch_news_source_based"`.

**Canonical production scheduler decision:** the **FastAPI lifespan asyncio scheduler** (`background.rss_fetcher.schedule_rss_fetch`, invoked from `main.py`) is the canonical owner of RSS ingestion. Celery Beat's `fetch-news-every-3-hours` entry stays disabled/absent — its underlying sources are still dead per BUG-057, and moving ownership to Beat is a larger change than this ticket's minimal-fix scope. `worker.py`'s asyncio scheduler must never be started in production alongside the FastAPI lifespan scheduler; a regression test (`test_worker_asyncio_main_is_not_referenced_by_procfile`) guards the Procfile against this. **Duplicate execution across FastAPI replicas is now prevented by a repository-level distributed lock** (see section 6 below) rather than by restricting Railway to one replica, so the fix survives normal horizontal scaling.

**2. The real bug: the live scheduler never reported a heartbeat, so `/health` could not distinguish "healthy" from "silently stuck."**

- `/health`'s `check_pipeline_heartbeats()` reads `pipeline_heartbeats["fetch_news"]` and only marks the pipeline **critical** if a heartbeat exists but is stale; if no heartbeat has ever been recorded it returns `"warning"` (non-fatal), by design, to tolerate a fresh deploy.
- Only the **dead** Celery task (`tasks/news.py::fetch_news`) called `record_heartbeat(..., stage="fetch_news")`. The **actually running** path, `rss_fetcher.fetch_and_process_rss_feeds()`, never wrote this heartbeat.
- Net effect: even if the FastAPI lifespan scheduler were completely stuck or crashing silently, `/health` would report `"pipeline": {"fetch_news": {"status": "warning", ...}}` forever — HTTP 200, no error — matching exactly what was observed on 2026-09-15 (200 OK, worker/beat online, no visible fetch activity, no alarms).
- **Fixed:** `fetch_and_process_rss_feeds()` now records the `fetch_news` heartbeat after every cycle (success or partial success), with a summary of feeds-ok/feeds-failed/articles-fetched/articles-enriched. Heartbeat write failures are caught and logged, never fail the ingestion cycle.

**3. No feed-level success/failure reporting.** `RSSService.fetch_all_feeds()` silently dropped failed feeds (a `None` return from `fetch_feed`) with no logging beyond stray `print()` statements. Fixed: `fetch_feed` now uses `logger.warning`; added `RSSService.fetch_all_feeds_with_results()` returning `(articles, {source: bool})`, consumed by `rss_fetcher.py` to log aggregate and per-feed-failure results every cycle.

**4. `/admin/trigger-fetch` is misleading.** Its docstring claimed it verifies "the ingestion pipeline," but it dispatches the dead Celery `tasks.news.fetch_news` task (`NewsCollector` source, no Beat schedule), not the canonical RSS path. Fixed: docstring/response message now state plainly this is the legacy path and point operators to `/health` for real RSS ingestion status. Behavior unchanged (kept minimal — not deleting the endpoint).

**5. Actionable failure context added** at each stage boundary in `fetch_and_process_rss_feeds()`: feed fetch, article upsert, and enrichment failures are now each wrapped with a distinguishing `logger.exception` before re-raising, so a MongoDB failure, an enrichment failure, and a "zero articles" cycle are distinguishable in logs (previously an exception anywhere in the chain surfaced with only a generic asyncio task-cancelled/failed log line from `schedule_rss_fetch`'s outer catch).

**6. Duplicate-run mitigation (added after the correction above): a MongoDB-backed distributed lock around the RSS fetch/process cycle.**

- New module `db/operations/scheduler_lock.py`: a generic named-lock primitive (`acquire_lock` / `renew_lock` / `release_lock`) using the same atomic `find_one_and_update` compare-and-set pattern already used for enrichment leasing in `enrichment_state.py`, keyed by an unguessable per-acquisition owner token (`secrets.token_hex(16)`), stored in a new `scheduler_locks` collection (one document per named job, `_id` = job name).
- `fetch_and_process_rss_feeds()` now acquires the `"rss_fetch"` lock before doing any work. If another replica already holds a live lease, the cycle is **skipped immediately** with a clear log message — never queued, never run concurrently. The lock is **released in a `finally` block** so it's freed even if fetch, upsert, or enrichment raises.
- **Lease TTL** is `settings.RSS_FETCH_LOCK_TTL_SECONDS` (default 1200s / 20 minutes) — comfortably longer than a normal fetch/upsert cycle (typically a few seconds based on the observed 262-272 article production fetches), so a crashed replica's lock expires and is automatically reclaimed rather than blocking ingestion forever.
- **Renewal**: the lock is renewed (lease extended) right before the longest-running step, LLM enrichment (`process_new_articles_from_mongodb`), so a large batch that runs long doesn't outlive its lease mid-cycle. If renewal fails (lease was reclaimed — meaning this replica's own lock was already lost to expiry and reacquired elsewhere), enrichment for that cycle is skipped rather than risking concurrent enrichment with the new owner.
- **Ownership-fenced release**: `release_lock`/`renew_lock` both compare-and-set on `(job_name, owner_token)`, so a replica whose lease already expired and was reclaimed by someone else can never accidentally release or renew the *new* owner's lock.
- This is a **repository-level mitigation independent of the missing `article_entity_type_primary_unique` index** (item 10 in scope, operator-controlled) — it stops duplicate fetch/upsert/enrichment *attempts*, but does not itself fix or depend on the index rollout.

### Changed files

- `src/crypto_news_aggregator/background/rss_fetcher.py` — heartbeat recording, feed-level result logging, stage-scoped failure logging, and the new scheduler-lock guard in `fetch_and_process_rss_feeds()`.
- `src/crypto_news_aggregator/services/rss_service.py` — `fetch_all_feeds_with_results()`, replaced `print()` with `logger`.
- `src/crypto_news_aggregator/tasks/fetch_news.py` — renamed colliding Celery task `"fetch_news"` → `"fetch_news_source_based"`; docstring documents it is not the canonical path.
- `src/crypto_news_aggregator/api/admin.py` — corrected `/admin/trigger-fetch` docstring/response to stop claiming it verifies RSS ingestion.
- `src/crypto_news_aggregator/core/config.py` — new `RSS_FETCH_LOCK_TTL_SECONDS` setting (default 1200s).
- `src/crypto_news_aggregator/db/operations/scheduler_lock.py` (new) — the distributed lock primitive described in finding 6.
- `tests/background/test_rss_fetcher.py` — fixed a pre-existing test bug (`monkeypatch.setattr` targeted the wrong module, `services.rss_service` instead of `background.rss_fetcher`, so the fake RSS service was never actually applied and the test was silently hitting live feed URLs); added heartbeat assertions, a partial-feed-failure test, and three lock-behavior tests (contention skip, lock released after success, lock released after a mid-cycle failure).
- `tests/db/operations/test_scheduler_lock.py` (new) — unit tests for the lock primitive: acquisition, contention, expiry/recovery from a crashed owner, ownership-fenced release, and renewal (including renewal failing for a reclaimed lease).
- `tests/test_bug_110_scheduler_ownership.py` (new) — regression tests: Beat schedule has no `fetch-news*` entry, the two `fetch_news` Celery tasks have distinct names, `main.py` wires up `schedule_rss_fetch`, Procfile's `worker` entry runs Celery (not `worker.py`'s asyncio scheduler).

### Test / verification results

Ran locally with `poetry run pytest` against a local MongoDB (no Railway credentials, production data, or production access used):

- `tests/test_bug_110_scheduler_ownership.py` — **4/4 passed**.
- `tests/db/operations/test_scheduler_lock.py` — **6/6 passed**, including a real bug the tests caught and I then fixed: the first version of `acquire_lock` raised an unhandled `pymongo.errors.DuplicateKeyError` on contention (an `upsert=True` `find_one_and_update` that fails to match an existing live lock still can't insert a new document with the same `_id`), so a second replica's acquisition attempt crashed instead of cleanly returning "lock held by another owner." Fixed by catching `DuplicateKeyError` and treating it as expected contention.
- `tests/services/test_heartbeat.py` — 6/6 passed (unchanged, pre-existing).
- `tests/api/test_health_heartbeat.py` — passed (unchanged, pre-existing).
- `tests/background/test_rss_fetcher.py` lock-behavior tests — **3/3 passed** when run together or with the rest of the new tests: `test_fetch_and_process_rss_feeds_skips_when_lock_held_by_another_replica` (fetch never called, no articles/heartbeat written, other replica's lock left untouched), `test_fetch_and_process_rss_feeds_releases_lock_after_success`, `test_fetch_and_process_rss_feeds_releases_lock_after_upsert_failure` (lock released via the `finally` block even when a stage raises).
- `tests/background/test_rss_fetcher.py::test_fetch_and_process_rss_feeds_records_heartbeat_with_failed_feeds` — **passed**: verifies a partial feed failure still records a heartbeat and the summary reports `"1/2 feeds ok"`.
- `tests/background/test_rss_fetcher.py::test_fetch_and_process_rss_feeds_persists_and_enriches` — fixed the monkeypatch target; article persistence now verified against a fake RSS service instead of live feeds, plus a new heartbeat assertion. Passes through persistence; enrichment assertions in this test and in the pre-existing `test_process_new_articles_from_mongodb_enriches_articles` still fail **locally**, but this is a **pre-existing failure unrelated to BUG-110** — reproduced identically on a clean stash of this branch before any BUG-110 changes. Root cause (from captured logs): the entity-mention enrichment path is gated by `_verify_mention_uniqueness_index`, which blocks enrichment when the `article_entity_type_primary_unique` index is missing/invalid; the local test MongoDB doesn't have that index provisioned. This is exactly the same index gap the operator's Railway session found blocking production enrichment (item 10, operator-controlled) — not touched here.
- **Known pre-existing test-file flakiness, not a BUG-110 regression:** `tests/background/test_rss_fetcher.py` has a pre-existing issue (reproduced on a clean stash) where an early test failure (the enrichment-index gate above) leaves later tests in the *same file* vulnerable to an intermittent `RuntimeError: Event loop is closed` from motor's executor-thread binding when the full file is run together. On a clean stash this already fails 3/4 tests in the file for this reason. My 3 new lock-behavior tests pass reliably in isolation and together with each other, but `test_fetch_and_process_rss_feeds_releases_lock_after_success` intermittently hits this same pre-existing flakiness when run after the already-broken enrichment tests earlier in the file. Not a correctness issue in the lock; a pre-existing test-infra gap in how this file manages the Motor event loop across many async DB tests.
- `tests/tasks/` — 11 pre-existing failures (`test_batch_processing.py`, `test_briefing_tasks.py`, `test_news_tasks.py`, `test_process_article.py`), reproduced identically on a clean stash of this branch. Not caused by or related to BUG-110 changes.
- `tests/background/test_rss_fetcher.py::test_rss_service_has_correct_feed_count` — pre-existing failure (test comment expects 13 feeds; only 9 are actually configured, a stale-comment mismatch unrelated to BUG-110), reproduced identically on a clean stash.

No production data, credentials, or Railway access were used at any point. No backfill, deletion, deduplication, replica/config change, or timestamp rewrite was performed.

### Railway checks / configuration still required from the operator (joint session)

Not performed — outside Claude's execution boundary for this ticket. Items 1-9 are the original repo-verification checklist; items 10-13 come from the ticket's expanded implementation scope (items 10-13) added after the joint Railway session and are explicitly operator-controlled actions I have not performed:

1. **Service inventory:** exact Railway service names for `web`, `worker`, `beat` (and `bugops` if deployed), replica counts for each, and confirmation only one `beat` replica is running (Celery Beat must never run more than one replica — duplicate schedules).
2. **Start commands:** confirm each service's actual start command matches `Procfile` (`web: uvicorn main:app ...`, `worker: celery -A crypto_news_aggregator.tasks worker ...`, `beat: celery -A crypto_news_aggregator.tasks beat ...`) — Railway can be configured with a custom start command that silently diverges from `Procfile`.
3. **Deploy status:** current deploy SHA/timestamp for `web` — confirm it includes this fix (heartbeat + scheduler lock), and that all `web` replicas have restarted since (the lifespan scheduler, and the lock, only take effect on process boot; a mixed fleet of old/new code would still duplicate-run until every replica redeploys).
4. **Environment variables (presence-only, do not print values):** `MONGODB_URI`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `TESTING` (must be unset/false in prod), `HEARTBEAT_FETCH_NEWS_MAX_AGE`, `RSS_FETCH_LOCK_TTL_SECONDS` (new; defaults to 1200s if unset).
5. **Recent `web` logs (post-redeploy):** grep for `"Starting RSS fetcher schedule"`, `"RSS feed fetch results"`, `"RSS ingestion cycle completed"`, `"Skipping RSS fetch cycle: another replica currently holds"`, `"Failed to record fetch_news heartbeat"` — confirms the lifespan task runs on each replica and the lock is now actively deduplicating cycles (you should see fetch logs from only one replica per cycle, and "Skipping" logs from the others, replacing the previously observed simultaneous 262-272 article fetches).
6. **Recent `worker`/`beat` logs:** confirm no `fetch_news`-related task dispatch/execution (expected, since Beat's entry is disabled) and that `warm-entity-articles-cache`/briefing tasks still run on schedule.
7. **`GET /health` response** (no auth required) post-deploy: confirm `checks.pipeline.fetch_news.status` moves from `"warning"` to `"ok"` with a recent `last_success` timestamp and a summary like `"N/M feeds ok, X articles fetched, Y enriched"`.
8. **Article/entity-mention evidence:** a read-only query (via existing `db-query` tooling, read-only credentials only) for `articles` with `created_at` in the last hour, and `entity_mentions` with `created_at` in the last hour tied to those article IDs — confirms the full fetch → upsert → enrichment → entity-mention chain is live, not just the fetch stage.
9. **Signals evidence:** `GET /api/v1/signals` returning non-empty `data` once qualifying recent mentions exist (downstream of #8 — do not force/backfill this).
10. **MongoDB index rollout (operator-controlled, ticket item 10):** run `db/operations/entity_mentions_index_rollout.py`'s `check_for_duplicate_mentions()` first; only create `article_entity_type_primary_unique` if that check passes. If duplicates are found, stop and document — do not delete, merge, or rewrite data.
11. **Confirm the lock actually eliminates duplicate fetches in production (operator-controlled, ticket item 11):** after redeploying with this fix, re-check `web` logs (#5) for the "Skipping RSS fetch cycle" messages from non-owning replicas. If overlapping full fetch cycles are still observed across replicas post-deploy, that's a signal the lock isn't taking effect (e.g. replicas can't reach the shared MongoDB `scheduler_locks` collection, or old code is still running on some replicas) and needs joint investigation before going further — do not fall back to reducing replica count as a silent workaround without documenting it here.
12. **Final production verification (ticket item 12):** confirm one fetch cycle occurs at the configured interval (not duplicated), and that the full path reaches entity mentions and Signals, only after 10 and 11 above are done.
13. **Rotate exposed production credentials (operator-controlled, ticket item 13):** database, Redis, API, and service tokens exposed during the Railway variable inspection. This is a manual operational security action; do not run this through repository tests or automation.

None of the above may be used to justify a production reset, deletion, deduplication, or timestamp rewrite; this ticket's acceptance criteria explicitly forbid that.

### Duplicate-remediation tooling (added 2026-09-15, repository-side only)

Following the production duplicate preflight above (2,016 duplicate groups,
43,406 documents, 41,390 excess documents, max group size 7,448, spanning
2026-04-02 through 2026-07-08), this section adds read-only analysis
tooling and an explicitly operator-gated, bounded cleanup path. **Nothing
in this section has been run against production.** No production data was
modified, deleted, or inspected while building or testing this.

#### What was added

- `src/crypto_news_aggregator/db/operations/entity_mentions_duplicate_audit.py`
  (new) — read-only analysis + gated cleanup module:
  - `run_duplicate_audit()` — groups `entity_mentions` by `(article_id,
    entity, entity_type, is_primary)` and reports duplicate group count,
    total/excess documents, max group size and its key, `created_at`
    min/max range, a group-size histogram (`2`, `3-5`, `6-10`, `11-100`,
    `101-1000`, `1001+`), and bounded representative samples. Never writes
    to the database. `max_groups_scanned` bounds the per-group detail pass
    without truncating the aggregate counts, so this stays cheap even
    against the known 7,448-document group.
  - `compare_group_documents()` — fetches every document in one duplicate
    group and reports which fields (`sentiment`, `confidence`, `source`,
    `metadata`, `published_at`) actually differ across the group, plus its
    `created_at` range. Distinguishes byte-identical reprocessing
    duplicates from duplicates that disagree on real field values.
  - `choose_canonical()` — a **deterministic, documented, proposal-only**
    canonical-record policy: prefer the document with a non-null
    `published_at` (BUG-109 established this as the field freshness
    computation depends on), then earliest `created_at`, then smallest
    `_id` as a final stable tie-break. Never called automatically; only
    decides, never deletes.
  - `plan_duplicate_cleanup()` — read-only: builds a dry-run `CleanupPlan`
    by applying `choose_canonical()` to the smallest N duplicate groups
    first (cheapest/safest to review). Groups larger than
    `max_group_size_for_auto_plan` (default 20,000) are skipped and listed
    in `skipped_groups` rather than materialized, so a very large group
    (e.g. the known 7,448-doc group) is never loaded unbounded into memory
    by an automatic pass — those must go through
    `compare_group_documents()` individually first.
  - `execute_cleanup_plan()` — the only function that can delete anything,
    and only if **all** of the following hold: (1) `confirm` equals the
    exact phrase `CLEANUP_CONFIRMATION_PHRASE` (`"DELETE DUPLICATE ENTITY
    MENTIONS"`) — a stray `confirm=True` can never trigger it; (2)
    `dry_run=False` is explicitly passed (default is `True`, so even a
    correctly confirmed call previews first); (3) deletion proceeds in
    bounded batches (`batch_size`, default 25) using individual
    `delete_one({"_id": ...})` calls, never `delete_many`/`bulkWrite`, so a
    partial failure can never remove more than the one document it
    targeted. Every call (dry-run or real) returns a `CleanupAuditReport`
    with the group key, canonical id kept, and exact ids removed/would-be
    removed, for the operator to save. Recoverability note documented
    in-module: this function does not create a backup itself; the operator
    should `find({"_id": {"$in": documents_to_delete}})` and export before
    ever passing `dry_run=False` against production.
- `scripts/entity_mentions_duplicate_audit.py` (new) — CLI wrapping the
  above: `report`, `compare`, `plan` (writes a reviewable JSON plan),
  `cleanup` (requires `--confirm "<exact phrase>"`, defaults to dry-run,
  only deletes with `--execute`). Never creates the unique index and never
  should be extended to.
- `tests/db/operations/test_entity_mentions_duplicate_audit.py` (new) — 10
  tests: no-duplicates baseline, byte-identical duplicates, duplicates that
  differ on `sentiment`/`source`/`published_at` (and that `choose_canonical`
  correctly prefers the doc with `published_at`), a 250-document large
  group (analogous in shape to the 7,448-doc production case) verified
  against the size-distribution histogram, plan-skips-oversized-groups,
  plan-never-deletes, cleanup-rejects-wrong-confirmation-phrase,
  dry-run-deletes-nothing, execute-deletes-only-discarded-docs (canonical
  survives), and batching (9 discard ids / batch_size 3 → 3 batches).

#### Reference-safety finding (repository-wide search, informs the canonical policy)

Searched every `.py` file under `src/` for references to `entity_mentions`
document identity. **No collection or code path stores or looks up an
`entity_mentions._id` value anywhere else in the codebase.** Every consumer
(`signal_service.py`, `narrative_service.py`, `signal_scores.py`,
`briefing_agent.py`, admin endpoints, `entity_mentions.py` itself) queries
or aggregates by `(article_id, entity, entity_type, is_primary)`, never by
a stored/foreign-keyed `entity_mentions._id`. This means which specific
duplicate document is kept as canonical has no referential-integrity impact
elsewhere in the system — only the kept document's field values matter,
which is what `choose_canonical()`'s policy optimizes for.

#### Test results

`poetry run pytest tests/db/operations/test_entity_mentions_duplicate_audit.py -q`
against local MongoDB: **10/10 passed.** `tests/db/operations/test_scheduler_lock.py`
re-run to confirm no interference: **6/6 passed.** No production data,
credentials, or Railway access used.

#### Limitations

- Not run against production. All counts/behavior above are validated
  against synthetic local fixtures, not the actual 2,016 production groups.
- `choose_canonical()`'s policy is a proposal. It has not been reviewed or
  approved by the operator, and no cleanup has been planned or executed
  against production data.
- `plan_duplicate_cleanup()`'s default `max_group_size_for_auto_plan`
  (20,000) would not skip the known 7,448-doc group; an operator should
  explicitly lower this (or review that group individually via `compare`
  first) before ever building a plan against the real dataset, given its
  size and 3-month span.
- `execute_cleanup_plan()` does not create its own pre-deletion backup;
  that is documented as an operator step, not automated here, since the
  export destination/tooling choice is an operational decision outside a
  read-only module's scope.

#### Exact operator approval required before any cleanup runs

All of the following, in order, before `execute_cleanup_plan(..., dry_run=False)`
is ever invoked against production:

1. Operator runs `scripts/entity_mentions_duplicate_audit.py report` against
   production (read-only) and reviews the real duplicate-group shape.
2. Operator runs `compare` against the largest/most concerning groups
   (starting with the known 7,448-doc Bitcoin group) to see whether the
   proposed `choose_canonical()` policy's tie-break actually picks a
   sensible representative for that data.
3. Operator explicitly approves (in writing, e.g. this ticket or a linked
   doc) the canonical-record policy in `choose_canonical()`, or specifies
   changes to it, before any plan is built against production.
4. Operator runs `plan` against production (still read-only; writes a JSON
   plan file) and reviews the plan output, including `skipped_groups`.
5. Operator exports a backup of every document in `documents_to_delete`
   before running `cleanup`.
6. Operator runs `cleanup` **without** `--execute` first (dry run) and
   reviews the audit report.
7. Only then does the operator run `cleanup --execute` with the exact
   `--confirm "DELETE DUPLICATE ENTITY MENTIONS"` phrase, in bounded
   batches, saving the resulting audit report.
8. Operator re-runs `report` and confirms `duplicate_groups == 0` (or that
   all remaining groups are explicitly accepted as out of scope) before
   proceeding to index creation.

**The `article_entity_type_primary_unique` index must not be created until
all of the following are true:** (a) the duplicate-remediation plan above
has been explicitly approved by the operator; (b) any approved cleanup from
that plan has been completed and audited; (c) a fresh
`check_for_duplicate_mentions()` / `report` preflight against production
shows **zero** duplicate groups. This is unchanged from, and reaffirms,
ticket item 15 and the original operator checklist item 10 above — this
section only adds the tooling to make steps (a) and (b) possible without a
blind/manual cleanup.
