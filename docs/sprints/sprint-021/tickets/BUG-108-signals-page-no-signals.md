---
ticket_id: BUG-108
title: Investigate empty Signals page despite recent article ingestion
priority: high
status: OPEN
phase: A
date_created: 2026-09-13
branch: docs/bug-108-investigation
effort_estimate: medium
---

# BUG-108: Investigate empty Signals page despite recent article ingestion

## Current status (2026-09-15, fourth pass) — read this section first

**Defect 1 (ownership race): FIXED and behaviorally verified, both required serialization orderings and the no-partial-writes guarantee.** Defect 2 (index-blocking): unchanged, already correct, its worker-integration tests pass. **Still NOT deployment-ready** — see Unresolved / concrete blockers below, in particular the still-unconfirmed production transaction-support prerequisite.

This section is the current, authoritative status. It supersedes every "Session update" section below it; those are retained as history (each explicitly says what it got wrong and what the next pass fixed) and should not be read as current. The **Fresh-session handoff — 2026-09-15** section further below predates all four passes in this file and is fully superseded; it is retained only because it contains the original problem statement, investigation plan, and read-only production-query reference material that are still valid.

### What this pass added (on top of the third pass's transaction fix, unchanged)

The third pass (below) implemented the transaction fix and one overlapping-takeover regression test, but that test covered only ONE of the two legitimate serialization orderings (Worker B completes its reclaim before Worker A's fenced write is even staged). Review correctly identified two more required cases were untested: the mirror ordering (A stages its fenced write first, B attempts takeover while A's transaction is still open), and a partial-failure/no-partial-writes proof. Both are now added, using the same real-writer, real-replica-set, no-mocking approach as the existing tests:

- **`test_takeover_attempted_while_a_already_holds_the_fence`**: uses the existing `_after_fence_hook` (fires after A's fenced write is staged, before mention writes/commit) to launch Worker B's real `claim_batch()` concurrently while A's transaction is still open and uncommitted. Verified outcome: A wins (its fenced write was staged first, so it legitimately owned the lease at that moment) and its mention commits; B's reclaim only becomes effective after A's transaction resolves, and B can then write normally. This is the correct outcome for this ordering — "A wins, B waits" — not a bug, and the test asserts on it rather than on B "losing" incorrectly.
- **`test_failure_after_first_mention_write_leaves_no_partial_results`**: a new test-only `_after_first_mention_hook` parameter fires after the first of two mentions has been staged inside the transaction, then raises a deliberate, distinctly-typed exception. Verifies (a) the exception propagates out of `create_entity_mentions_batch_idempotent()` rather than being swallowed, (b) **neither** mention persists afterward — including the already-staged first one — proving the transaction rolls back as a whole rather than leaving a partial commit, (c) the article's ownership fence itself is also rolled back (owner/status unchanged), and (d) a clean retry afterward succeeds normally and writes both mentions, confirming the aborted attempt left no corrupted state behind.

Both new tests passed on first execution against the isolated replica set (see Local Test Results).

### Combined-suite results — now actually attempted, with an honest account of what was observed

The third pass explicitly deferred combined-suite / cross-file execution as out of scope. This pass ran it:

- First combined run (`test_rss_fetcher_worker_state.py` alone, freshly appended with the two new tests): **5 errors** (not failures — pytest reported `ERROR at setup` for 5 of the 11 tests in a full-file run, immediately after the new replica-set-heavy tests had just run).
- Investigating individually, every one of those 5 tests **passed in isolation** (single-test invocation), which is what led to suspecting environment contention rather than a real regression.
- Re-running the exact same full file **twice more, freshly, with the machine otherwise idle**: **11 passed, 0 failed/errored**, both times.
- Running the broader 3-file combined set (`test_rss_fetcher_worker_state.py` + `test_entity_mentions_idempotent.py` + `test_entity_mentions_index_rollout.py`) together: **26 passed, 0 failed/errored**.

**Honest conclusion, not a confident one: this is consistent with — but not conclusively proven to be — the same intermittent local-environment contention this ticket's history has repeatedly documented** (heavy concurrent MongoDB load from running two local mongod processes — the standalone dev instance plus the isolated replica set — across many back-to-back test invocations in one session). It was not root-caused to a specific mechanism (e.g. connection pool exhaustion, port contention, a specific race in test teardown) because doing so would require deliberately reproducing it under controlled load, which was not attempted this pass (scope). The one data point that DID error is not discarded or hand-waved away here: it happened once, out of three attempts, only in a full-file run, never in isolation. That pattern is recorded as-is; it is not proof of zero regressions, only evidence against a deterministic one introduced by this pass's two new tests specifically (which is the risk this instruction was checking for).

### Local Test Results (2026-09-15, fourth pass, this section's data)

Same isolated replica set as the third pass (`mongod --replSet bug108rs`, port 27117, dbpath `/tmp/bug108-replset-data`), left running and reused across passes; the standalone dev instance (port 27017) confirmed genuinely standalone in the third pass and untouched by this one.

| Command | Result |
|---|---|
| `poetry run pytest tests/background/test_rss_fetcher_worker_state.py::test_takeover_attempted_while_a_already_holds_the_fence tests/background/test_rss_fetcher_worker_state.py::test_failure_after_first_mention_write_leaves_no_partial_results -q` | **2 passed** (first attempt, no design iteration needed this time) |
| `poetry run pytest tests/background/test_rss_fetcher_worker_state.py -q` (full file, fresh) — 1st run | **5 errors, 6 passed** (see combined-suite discussion above) |
| Same command — 2nd run | **11 passed, 0 failed** |
| Same command — 3rd run | **11 passed, 0 failed** |
| `poetry run pytest tests/background/test_rss_fetcher_worker_state.py tests/db/test_entity_mentions_idempotent.py tests/db/test_entity_mentions_index_rollout.py -q` (3-file combined) | **26 passed, 0 failed** |
| `git diff --check` on all changed/new files | clean |

### Unresolved / concrete blockers (current, supersedes the third pass's list below)

1. **Combined-suite intermittency is not root-caused** (see honest account above) — attempted this pass, one non-reproducing error observed out of several runs, consistent with prior-documented local resource contention but not proven to be that specifically. If this recurs in a more controlled setting (e.g. CI), it needs actual diagnosis (connection pool sizing, port/process contention, teardown ordering) rather than being assumed environmental again.
2. **The isolated replica set (port 27117) remains a manually-started local process**, not available in CI or staging. Unchanged from the third pass; see that section for exact restart commands. Out of this ticket's scope to provision as durable infrastructure.
3. **Production MongoDB transaction support is still an unconfirmed, blocking rollout prerequisite.** Unchanged from the third pass — no production/staging credentials were used in this pass either. The operator must confirm the target deployment (Railway-hosted or Atlas) supports multi-document transactions before any staging or production rollout; see the third pass's item 3 for the exact read-only check and failure-mode description.
4. Everything listed as unresolved in the original investigation's Fresh-session handoff (staging, Railway evidence, production policy approval, age-cutoff approval) remains unresolved and unchanged.

### Deployment readiness (current)

**Still NOT deployment-ready.** Both defects are implemented and now behaviorally verified across: the ownership-lost case, both legitimate serialization orderings of an overlapping takeover, and the no-partial-writes guarantee under a mid-transaction failure — all against the real writer and a real replica set, plus a proof that the actual (verbatim) prior implementation fails the same overlapping-takeover scenario the fix passes. What remains before staging/production consideration: resolving or further diagnosing the combined-suite intermittency (not blocking by itself, but worth a controlled reproduction before relying on CI test stability), confirming the production MongoDB deployment supports transactions (blocking), and all previously-identified operator-gated items (Railway evidence, age-cutoff and index-rollout production approval, staging environment, post-deploy validation).

## Session update — 2026-09-15, third pass (overlapping-race verification + fixture fixes)

**Superseded by the "Current status" section above.** Retained for history. The gap this pass fixed relative to the pass before it: its regression test sequenced Worker A's call after Worker B's reclaim completed, rather than making them genuinely overlap, so it could not by itself distinguish the fix from the prior internal find_one-then-update implementation. That gap is now closed: the regression test forces a genuine overlap, and the same test, run unmodified against a verbatim snapshot of the actual prior implementation, is proven to fail on it. The missing-index test-fixture gap from the pass before this one is also fixed (not left as "pre-existing"), and a separate, deeper pre-existing mock defect that was silently preventing several worker tests from ever exercising mention persistence at all was found and documented.

### What changed (code)

- `src/crypto_news_aggregator/db/operations/entity_mentions.py`: `create_entity_mentions_batch_idempotent()` uses a real MongoDB multi-document transaction (`session.with_transaction()`) when `article_id`/`owner_token` are provided. Inside the transaction, a conditional **write** (`articles_collection.update_one(..., session=session)`) fenced on `{status: in_progress, owner_token}` runs first; only if it matches do the mention upserts run, in the same session. A non-matching fenced write raises an internal `OwnershipLostError`, aborting the transaction before any mention write lands, and the function returns 0.
  - Added two **test-only** parameters, `_before_fence_hook` and `_after_fence_hook` (both default `None`; never passed by production call sites), which fire inside the live transaction before/after the fenced write respectively. These exist solely so tests can force a genuine overlap between this transaction and a concurrent writer — see below for why a hook was necessary and why the hook body itself must not block.
  - The docstring was corrected twice this session: first to describe the transaction mechanism instead of the prior misleading "atomic" language, then again after empirical testing (see below) corrected an initially-plausible-but-wrong claim about *how* the transaction wins a race (it does not "conflict and abort/retry" against a concurrent writer; the concurrent writer instead blocks on the transaction's document lock until it resolves — verified empirically, documented in code with a pointer to the test that verifies it).
  - The non-transactional code path (no `article_id`/`owner_token`) is unchanged.
- `src/crypto_news_aggregator/background/rss_fetcher.py`: corrected the stale comment block at the mention-write call site (previously implied atomicity was already achieved by an earlier fix; now describes the transaction).
- `tests/_fixtures/legacy_entity_mentions_pre_transaction_fix.py` (new): a **verbatim** snapshot of `create_entity_mentions_batch_idempotent()` exactly as it existed in this working tree before this session's transaction fix (the read-only `find_one()` ownership check followed by separate, unfenced `update_one()` mention writes). Added specifically so the regression test could be proven against the actual previous implementation rather than a separately hand-written "unsafe example" standing in for it, per explicit review feedback. Test-only; never imported by production code.

### What changed (tests) — overlapping-race verification

The review that prompted this pass identified that the prior version of `test_real_writer_blocks_stale_insert_after_ownership_takeover` performed claim A → claim B (reclaim) → call writer with A's token, sequentially. Because Worker B's reclaim had already fully completed before Worker A's write was even attempted, this could not distinguish the transactional fix from the original non-atomic implementation: *any* correct ownership check, atomic or not, blocks a stale write issued strictly after the takeover. It also could not prove the earlier implementation was actually unsafe, since the unsafe companion test used a separately hand-written function that merely resembled the old code, not the code itself.

Both issues are now fixed:

- **`test_real_writer_blocks_takeover_that_overlaps_live_transaction`** (replaces `test_real_writer_blocks_stale_insert_after_ownership_takeover`): Worker A's transaction is paused, via the new `_before_fence_hook`, *before* it attempts its own fenced ownership write. While paused, Worker B's real `claim_batch()` runs via `asyncio.gather` and is confirmed to complete its reclaim. Only then does A's hook return and let A's transaction proceed to its fenced write and commit attempt. This is a genuine overlap: A's fenced write is evaluated only after B has already changed the document, not sequenced arbitrarily before or after B by the test's own control flow.
  - **This required two failed synchronization designs before landing on a correct one**, documented in the test's own comments: (1) a version where A's hook blocked waiting for B to finish deadlocked in practice, confirmed via a standalone debug script — MongoDB's WiredTiger document lock makes a concurrent non-transactional writer (B) block until A's open transaction resolves, so if A is simultaneously waiting on B's completion signal, neither can proceed; (2) a version where the hook fired *after* A's fenced write was already staged showed A always winning regardless of B's timing — also confirmed via a standalone debug script — because a transaction's fenced write, once staged, evaluates against a snapshot taken before any later-starting concurrent writer's change exists, so "after the fence" is definitionally too late to demonstrate an overlap. The `_before_fence_hook` (pausing *before* A even attempts its fenced write) is the version that correctly demonstrates the guarantee, and this is what the shipped test uses.
- **`test_actual_pre_fix_implementation_fails_this_regression`** (replaces `test_unsafe_read_then_write_pattern_fails_this_regression`): replays the *same* overlapping-interleaving technique, but calls `create_entity_mentions_batch_idempotent_pre_fix()` from the new verbatim legacy snapshot instead of the fixed function. Since the legacy implementation has no instrumentation point of its own (that absence is exactly its defect — an implicit, non-closeable gap rather than an explicit one), the overlap is created by wrapping the *exact* `find_one()` call the legacy code makes (patched at the `AsyncIOMotorCollection` class level, since Motor returns a fresh collection wrapper object on every `db.articles` attribute access — instance-level monkeypatching silently does not work, discovered and worked around this session) to signal Worker B the moment the legacy code's ownership read returns, then let the legacy code proceed immediately into its unfenced writes while B's reclaim races them for real. This **fails** (in the sense required — it demonstrates the race): the legacy implementation inserts a stale mention despite the concurrent takeover, proving it is genuinely unsafe under the same interleaving the fixed implementation is proven safe against.
- Removed the blanket `except OperationFailure: pytest.skip(...)` that previously wrapped the assertion under test. Transaction-capability is now checked once via a dedicated `_require_replset_transactions()` preflight at the start of each test, *before* any scenario setup; a capability failure there fails the test outright (not a skip) with a clear message, so a real regression in the transaction path can never be silently reinterpreted as "this environment doesn't support transactions." The `replset_db` fixture itself still skips (not fails) if the isolated replica-set deployment is entirely unreachable at connection time — that is a distinct, legitimate "test infrastructure unavailable" condition, not a masked behavioral failure.

### What changed (tests) — index-fixture gap, now actually fixed

The previous session update left 4 worker-level tests failing against a fresh standalone database and described this as "pre-existing, out of scope." On review instruction to fix rather than leave this, the actual root causes (two, not one) were found and fixed:

1. **Missing unique index**: the worker's own index-blocking check (defect 2) requires `article_entity_type_primary_unique` to exist before it will process any article at all, but neither the affected tests nor the shared `mongo_db` fixture create it (deliberately excluded from `initialize_indexes()`'s auto-created list — see `entity_mentions_index_rollout.py`). Fixed by adding an explicit `await create_unique_index(mongo_db.entity_mentions)` call at the start of each of the 4 affected tests (not a change to the shared fixture, to avoid affecting the two tests that deliberately require the index to be absent/wrong).
2. **A separate, deeper, genuinely pre-existing defect, found while investigating #1**: `_mock_llm_client()` (this file's shared LLM mock helper) never configured `extract_entities_batch()` — the method the worker's entity-extraction step actually calls — leaving it an unconfigured `Mock()` attribute. Every one of these tests was silently hitting `'Mock' object is not iterable` inside entity extraction, resulting in zero entities and therefore an always-empty `mentions_to_create`, meaning **none of these worker-level tests had ever exercised the mention-persistence code path at all**, before or after this session's ownership fix. This predates this session (the mock helper is unchanged history from an earlier round) and is unrelated to the ownership/transaction defect. Fixed by adding an optional `with_entities: bool` parameter to `_mock_llm_client()` that configures a correctly-shaped `extract_entities_batch()` return.
   - Applying `with_entities=True` to `test_worker_skips_mention_write_when_lease_expires_during_llm_call` (the one test whose docstring specifically claims to test mention-write fencing) revealed that this test *still* does not reach mention persistence even with real entities present: the worker's `write_enriched_fields()` article-content fencing rejects the stale write first (it checks `owner_token` match, which already fails once B has reclaimed), and the code `continue`s before ever reaching the mention-write call. This is not a bug -- it is legitimate defense-in-depth (the article-field fence is a real, independent guarantee, exercised correctly here) -- but it means this specific test's docstring overclaimed what it verifies. Reverted this one test's `with_entities` change (no value added, since it can never reach the mention-write branch) and corrected its docstring to say plainly what it actually proves (`write_enriched_fields()` fencing, not mention-persistence-transaction fencing), with a pointer to the two dedicated tests above for the mention-persistence guarantee specifically.
   - The other 3 affected tests (`test_worker_writes_enriched_fields_and_marks_completed`, `test_worker_marks_tier2_articles_skipped_not_completed`, `test_worker_skips_write_when_lease_reclaimed_mid_run`) do not depend on mention persistence at all (tier-2 skip and article-field completion/fencing only) and needed only the index fix.

### Local Test Results (2026-09-15, this pass)

Isolated replica set: `mongod --replSet bug108rs` on port 27117, dbpath `/tmp/bug108-replset-data`, initiated with `rs.initiate()` (single-node PRIMARY), started outside and independent of the user's existing standalone MongoDB installation (`/opt/homebrew/var/mongodb`, port 27017, confirmed genuinely standalone via a direct transaction attempt that fails with `Transaction numbers are only allowed on a replica set member or mongos`). The standalone instance was never stopped, reconfigured, or written to by this session beyond its normal existing test usage.

| Command | Result |
|---|---|
| `poetry run pytest tests/background/test_rss_fetcher_worker_state.py::test_real_writer_blocks_takeover_that_overlaps_live_transaction tests/background/test_rss_fetcher_worker_state.py::test_actual_pre_fix_implementation_fails_this_regression -q` | **2 passed** |
| `poetry run pytest tests/background/test_rss_fetcher_worker_state.py -q` (full file, standard `mongo_db` fixture, standalone port 27017, fresh database) | **9 passed, 0 failed** (previously 4 failed against a fresh database; now genuinely fixed, not left as pre-existing) |
| `poetry run pytest tests/db/test_entity_mentions_idempotent.py tests/db/test_entity_mentions_index_rollout.py -q` | **15 passed** |
| `git diff --check` on all changed/new files | clean |

### Unresolved / concrete blockers (as of this pass — see "Current status" above for the up-to-date list, which also covers item 1 below)

1. ~~Combined-suite / cross-file execution was not attempted this session~~ — attempted and reported in the "Current status" section above (fourth pass).
2. **The isolated replica set (port 27117) is a manually-started local process for this session**, not a fixture other engineers get automatically. To rerun: `mongod --config <config-with-replSet-and-port-27117>` in the background (macOS does not support `--fork`), then `mongosh --port 27117 --eval "rs.initiate()"`. The `replset_db` fixture (in `test_rss_fetcher_worker_state.py`) defaults to `mongodb://localhost:27117/crypto_news`, overridable via `BUG108_REPLSET_TEST_URI`. This is local dev/test infrastructure only; it does not exist in CI or staging. Addressing that gap (e.g. a CI-level replica-set service, or documenting it in project setup) is outside this ticket's authorized scope.
3. **Production MongoDB transaction support is a read-only rollout prerequisite, not yet verified.** The fixed mention writer requires a replica set (or sharded cluster) deployment when `article_id`/`owner_token` are passed — a standalone `mongod` raises `OperationFailure` on the first transactional call, which would surface as every worker mention-write attempt failing (not silently; `create_entity_mentions_batch_idempotent()` does not catch `OperationFailure`, so it propagates to the worker's existing per-article `except Exception` handling, which calls `mark_failed()` for that article rather than crashing the batch — but this means enrichment would appear stuck / permanently retrying rather than obviously erroring). **Before any staging or production rollout, the operator must confirm the target MongoDB deployment (Railway-hosted or Atlas) is a replica set / supports multi-document transactions** — this is a read-only capability check (e.g. `db.hello().setName` returning a value, or a harmless test transaction against a throwaway document), not a production mutation, and can be run by the operator or by Claude under the existing read-only production-query authorization once explicitly requested. Still not checked as of the fourth pass (no production/staging credentials were used in any pass); still an explicit blocker, not an implicit assumption.
4. Everything listed as unresolved in the prior handoff below (staging, Railway evidence, production policy approval, age-cutoff approval) remains unresolved and is unchanged by this session.

### Deployment readiness (as of this pass — superseded by "Current status" above)

**Still NOT deployment-ready.** Both defects required by this ticket's immediate-work directive are now implemented and behaviorally verified through the real writer, including a genuinely overlapping concurrent-takeover scenario proven against both the fixed and the actual (verbatim) prior implementation. What remains before staging/production consideration: combined-suite verification (now attempted — see "Current status" above), confirming the production MongoDB deployment supports transactions (item 3 above — still blocking), and all previously-identified operator-gated items (Railway evidence, age-cutoff and index-rollout production approval, staging environment, post-deploy validation).

---

## Superseded — session update, 2026-09-15, second pass (ownership race: atomic fix implemented, but regression test did not prove overlap)

**Retained for history; corrected and superseded by the pass above.** This pass implemented the transaction-based fix (still current) but its regression test sequenced Worker A's call strictly after Worker B's reclaim had already completed, which the next review correctly identified as insufficient to distinguish the fix from the prior non-atomic implementation. See the pass above for the corrected, overlapping version of this test and for the verbatim-legacy-implementation proof.



## Fresh-session handoff — 2026-09-15 (ownership race still unresolved)

**Start here. BUG-108 remains OPEN and NOT deployment-ready.** Substantial state-machine implementation now exists. Continue from the current working tree; do not rebuild it or repeat the earlier design-only phase. This handoff supersedes earlier completion claims and conflicting status statements below and in investigation reports. The immediate task is to fix the two verified defects below, test them through the worker, and return for review without scope expansion.

### Latest review verdict — supersedes the last Claude summary

**The ownership race is NOT fixed. Index blocking is implemented but integration validation is pending.** The last session moved the ownership check into `create_entity_mentions_batch_idempotent()` and called that atomic. Code inspection disproves this: `articles_collection.find_one()` completes before separate `entity_mentions.update_one()` calls. Function boundaries do not make database operations atomic; takeover can still happen between the read and writes or between individual mention writes. Correct the misleading atomicity docstrings as part of the fix.

The latest race test, `test_worker_mention_write_race_after_lease_renewal()`, does not prove the required guarantee: it simulates takeover before the ownership check, substitutes writer behavior, and also assigns its mention-write mock to `enrich_articles_batch`. It was not executed successfully. Replace this test rather than citing it as evidence.

The latest report states four mocked index-verification tests passed; race and worker integration execution was skipped because local MongoDB setup timed out. Compilation/import checks are not behavioral verification. Do not claim both defects fixed, locally verified, or ready for staging based on this report.

### Decisions and local implementation scope

- **Signals page: 24h**, explicitly requested on every page/refetch, with matching label and query key. Preserve the API's existing **7d default** for callers that omit timeframe.
- Proceed with configurable **provisional local development defaults**: a **30-minute renewable lease**, **3 total attempts** (initial attempt plus two retries), retry waits of **5 minutes then 10 minutes**, and oldest-first recovery **every third run** with rotation persisted across restarts. There is no third 20-minute retry with a three-attempt cap.
- Keep the **30-day age cutoff provisionally for local development**. Production age-policy approval remains pending. It filters article ingestion age (`created_at`); it does not delete articles or define the Signals display window.
- These defaults permit local implementation and isolated tests now. Do not request production-setting approval as a prerequisite to writing code, migration tooling, or tests. Prepare bounded migration with a read-only dry-run mode; do not execute it against production.
- The operator will need assistance reviewing Railway evidence, interpreting final patch/test/staging results, and deciding on rollout. Provide concrete evidence and instructions; do not hand back deployment while required code is missing.

### Current working tree — preserve existing implementation

HEAD was `8460f5d` at this handoff, following `dc115f8` and `08087a0`. Most subsequent implementation is **uncommitted**, including untracked source and test files. Inspect `git status`, current code, and untracked files; committed history alone is not the current patch. Do not reset, clean, or stash away this work. Preserve the unrelated `.claude/worktrees/` changes.

Existing work includes:
- `db/operations/enrichment_state.py`: persisted states, atomic claims, ownership tokens, renewal helpers, fenced article/status writes, retry cap including stale recovery, and fairness selection.
- `background/rss_fetcher.py`: integrated claims, persisted rotation, sub-batch renewal, and article_id/owner_token passed to the mention writer. The former separate pre-write renewal was removed, but moving the check into the writer did not solve the race.
- `db/operations/enrichment_migration.py`: bounded legacy migration and dry-run support; shared legacy-completion classification.
- `db/operations/entity_mentions.py`: idempotent upserts, intended to rely on a unique index.
- `db/operations/entity_mentions_index_rollout.py`: explicit index creation and read-only duplicate preflight; the new index is no longer automatically created at startup.
- `db/mongodb.py`: creation/close locking and per-event-loop lock changes; ArticleService shared-client ownership change from earlier work. These changes are not independently established as the production outage cause.
- Real local MongoDB tests, including `tests/background/test_rss_fetcher_worker_state.py` and new state, migration, mention, and rollout tests. UI explicitly requests 24h and the API default remains 7d.

### Immediate work — finish atomic ownership enforcement and execute validation

**1. Implement an actual stale-owner write barrier.** The mention writer currently reads article ownership and then separately upserts mentions. Another read/check, even immediately before each write, is insufficient.

A viable implementation is a MongoDB transaction that performs a conditional **write** to the article ownership record and persists the associated mentions in the **same session/transaction**, so a competing ownership takeover conflicts with that transaction. A detached read, a read-only ownership check inside a transaction, or merely wrapping operations in one Python function is insufficient. An equivalent design is acceptable if it establishes the same guarantee. Verify the chosen mechanism's supported topology and failure semantics; do not assume standalone MongoDB supports transactions. If needed, prepare an isolated local replica set without altering the user's existing database or production. Handle stale ownership distinctly from successful persistence so the worker cannot mark incomplete work completed. Test aborted/partial writes and retry behavior with the chosen design.

**Required regression test:** Exercise the REAL mention writer through the worker. Pause Worker A **after successful ownership validation but before mention persistence**, allow Worker B to reclaim the expired lease, then resume A. Verify no stale insert, overwrite, or completion commits. If the chosen atomic mechanism prevents takeover until commit, test that serialization/conflict behavior explicitly rather than forcing an impossible interleaving or deadlocking the test. Use deterministic synchronization, not timing luck. Include both an absent mention and an existing mention with newer-owner data. Do not mock the writer into returning the desired result, and do not substitute takeover during the earlier LLM call. Demonstrate that the unsafe implementation fails the regression and the fix passes.

**2. Preserve and validate the index-blocking improvement.** `verify_unique_index_exists_and_valid()` now checks the index name, ordered keys, and `unique: true`, and the worker returns before enrichment when validation fails. This is implementation progress; the worker integration tests still need successful execution. Run actual worker-path tests for absent index, same-name/wrong-definition index, unverifiable index (verification error), and correctly installed index. Assert rejected cases make no claims, LLM calls, or mention writes, while RSS ingestion and API remain available. Keep unique-index creation explicit, with read-only duplicate preflight and operator-gated production execution.

**Acceptance for this session:** Working atomic ownership enforcement, executed race and index-blocking behavioral tests, honest remaining validation limitations, and an updated ticket. Do not restart the state machine, broaden scope, or replace implementation with a new design-only report. If test infrastructure blocks execution, diagnose the concrete setup failure and report it as unresolved; do not infer environmental contention solely from standalone passes.

### Validation and handoff expectations

- Claude reported 70 standalone passes in the latest round (71 in an earlier round). These reports have not been independently rerun by the reviewer. Preserve the actual command/result records; do not merge counts from different revisions.
- Combined-suite timeouts/failures remain **unresolved** unless a controlled baseline comparison or reproducible diagnosis demonstrates their cause. Standalone passes alone do not establish environment contention or zero regressions. Correct contrary claims in the ticket/current report.
- Run targeted behavioral tests for the two defects, plus the relevant affected regression tests, using explicitly isolated local test data. Record commands, results, environment requirements, and limitations. Source/AST assertions cannot establish concurrency guarantees.
- Do not declare earlier lifecycle/renewal work fully verified solely from a summary; record residual gaps honestly. The two findings above are the immediate implementation task, not a request to redesign the whole pipeline.
- Update this ticket and one current repository report. Return the reviewable diff, evidence for the two guarantees, and remaining rollout/staging gaps. Do not create more speculative “complete fix” documents.

### Operator work remains later

No staging end-to-end evidence has been supplied, and no staging environment is established in the handoff. Railway instance/restart evidence, E11000 frequency, final patch review, production policy approval, explicit index rollout/migration approval, and post-deploy validation remain pending. The operator needs assistance interpreting these steps. They are not reasons to stop the two local fixes. No production or Railway mutations were reported in prior sessions or authorized here.

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

The operator selected **24h**. Keep the page request explicitly on `24h`, retain its matching label, and preserve the existing `7d` API default for other callers. Verify pagination/refetch and cache behavior with behavioral tests.

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
- Signals timeframe decision is complete: **24h UI**, with existing **7d API default** preserved; verify implementation and tests.
- Review Railway Deployments/Events for the 21:30–23:10 UTC window: instance count, deploy/restart events, and available health/OOM reasons. Record that evidence without asserting a restart cause if Railway does not show one.
- Review E11000 frequency over a useful interval and decide whether the local non-fatal handling is sufficient or a separate ingestion/deduplication fix is needed.
- Review and approve the final code diff and staging results.

Production rollout is ready only after all required code paths and tests above pass, the staging path produces fresh signals, the age/timeframe decisions are recorded, and the owner approves deployment. Do not automatically run the legacy-state migration, create indexes, trigger enrichment/backfills, call cache-populating endpoints, change Railway settings, restart services, or deploy. If any such production action is needed, present its exact scope and wait for the operator's explicit authorization.

After an approved rollout, verify read-only that fresh articles are reaching terminal enrichment states, recent primary `entity_mentions` are being created, MongoDB client errors are absent, the endpoint returns results for the chosen timeframe, and the UI label matches. Define rollback triggers and monitor duplicate errors and enrichment latency. Close the bug only after these checks pass; track any separately deferred backlog/state-machine work in a linked ticket rather than implying it is fixed.

## Prior implementation report (2026-09-15; superseded where conflicting)

**Reviewer note:** Retained as session history. The latest fresh-session handoff above records two unresolved defects; prior claims that all findings are fixed or that combined failures are proven environmental are not accepted.

- [x] Production symptom and dated evidence recorded; underlying production cause remains unproven.
- [x] Product intent resolved: Signals page displays 24h; retain 7d API default.
- [x] Partial patches, configuration, designs, and tests exist through `8460f5d`.
- [x] MongoDB client lifecycle: fixed the unlocked-recreation race in `get_async_client()`, **and** fixed a second, more severe defect found while testing it — a class-level `asyncio.Lock()` shared across event loops could end up permanently locked (deadlocked) if a task holding it was ever abandoned/cancelled on one loop and the lock reused on another. The lock is now created lazily per-loop (mirroring the existing `_client_loop` recreation pattern), and `aclose()`/`close()` now also acquire it, so they cannot race client (re)creation.
- [x] Implemented integrated durable enrichment states, atomic claims with ownership tokens, **per-write lease re-verification (not just per-sub-batch renewal)**, exponential-backoff retries with exact attempt-count cap enforced during stale-lease recovery, terminal skip/failure, idempotent + concurrency-safe mention persistence (backed by a real unique index with an explicit, operator-gated, duplicate-safe rollout path), and fairness rotation persisted in MongoDB.
- [x] Article-content writes and mention writes are now fenced on lease ownership at the point of writing, not just at the terminal state transition, and not just once per sub-batch.
- [x] Worker's own claim eligibility reconciles with legacy-complete classification, so it will not reprocess already-enriched legacy articles even before migration has run.
- [x] Implemented bounded, observable legacy migration with read-only dry-run mode. Never wired into application startup; must be invoked explicitly.
- [x] Unique mention index rollout is now fully explicit and safe: `entity_mentions_index_rollout.py` provides a read-only duplicate preflight and a creation function that fails cleanly (not uncaught) on existing duplicates; the index is **not** part of automatic startup index creation (which previously would have crashed the entire app startup lifespan if production had pre-existing duplicate mention keys); the worker checks for the index's presence once per run and logs loudly (without blocking) if it's missing.
- [x] Duplicate-URL handling unchanged from prior sessions (`db/operations/articles.py`); not modified this session.
- [x] Replaced source/AST-inspection tests with real behavioral tests, including worker-level integration tests that call `process_new_articles_from_mongodb()` directly, against a real local MongoDB (`mongodb://localhost:27017/crypto_news`, isolated per-test via the existing `mongo_db` fixture — never production).
- [ ] Staging validation of the full article → enrichment → mention → signal → UI path: NOT run (no staging environment configured for this repo; see Deployment Readiness below).
- [ ] Railway instance/restart evidence and E11000 frequency review: NOT performed this session (requires operator-provided Railway access).
- [ ] Production policy/rollout approval and post-deploy verification: pending, as before.

### What changed this session (implementation)

**Round 1 — initial state machine:** durable per-article enrichment states (`pending`/`in_progress`/`completed`/`skipped`/`failed`), atomic claim-with-lease via CAS, owner-fenced terminal transitions, idempotent mention upsert, bounded legacy migration tool, worker wiring.

**Round 2 — first review-fix round, 6 integration defects:** lease renewal wired into the worker loop; article-content writes fenced on ownership (not just terminal transitions); legacy-complete articles excluded from claim eligibility; total-attempt cap enforced during stale-lease recovery (not just in `mark_failed()`); MongoDB client-recreation race fixed with a lock; unique index + `DuplicateKeyError`-retry added for concurrent mention upserts.

**Round 3 — second review-fix round, 4 further integration defects:**

1. **Per-write lease re-verification, not just per-sub-batch renewal (finding 1).** Sub-batch renewal (added in round 2) left a gap: an individual article's processing (e.g. the LLM call) could still outlast the lease *within* a sub-batch, between the renewal and the actual write. Added a `renew_lease()` re-check immediately before the mention write (the specific gap in finding 2, below), on top of the existing atomically-fenced `write_enriched_fields()`. Verified with `test_worker_skips_mention_write_when_lease_expires_during_llm_call`, which forces the mocked LLM call itself to expire the lease and let a second worker reclaim the article *before* the first call returns — a single-worker-run scenario, not just a race between two separate runs — and confirms the stale worker persists zero mentions afterward.
2. **Mention persistence fenced against ownership takeover, not just the article-field write (finding 2).** `write_enriched_fields()` (round 2) correctly fenced the article-document write, but the subsequent mention write to the *separate* `entity_mentions` collection had no ownership check of its own — a lease reclaimed in the gap between the two writes could let a stale worker persist mentions for an article another worker now owns. Added a `renew_lease()` call (which is itself owner-fenced) immediately before mention persistence; if it fails, mentions are not written and the article is left for the new owner.
3. **MongoDB `close()`/`aclose()` coordinated with client (re)creation, and a deadlock class fixed in the process (finding 3).** `aclose()`/`close()` did not acquire the same lock `get_async_client()` uses, so they could race it — closing a client another caller just created, or interleaving `_client_loop`/`_initialized` writes. Fixed by having both acquire the lock. **While writing a deterministic test for this, found a second, independent, more severe bug**: the lock itself (`asyncio.Lock()`, a class attribute created once at class-definition time) could end up permanently locked if a task holding it was cancelled/abandoned while running under one event loop and the lock was later reused on a different loop — reproduced standalone (see investigation notes in the diff) and empirically in this session's own test runs (an earlier failing test attempt left the singleton lock locked for the remainder of the pytest process, since `MongoManager` is a true singleton). Fixed by making the lock lazily created per-loop via `_get_async_lock()`, mirroring the existing `_client_loop` recreation pattern used for the Motor client itself — a fresh loop always gets a fresh, unlocked `Lock`. This is a materially different and more serious defect class than simple missing serialization: an unlocked-forever singleton lock would deadlock *all* MongoDB access application-wide, not just the specific racing callers, and Celery workers recreating event loops (the documented reason `_client_loop` tracking exists at all) is exactly the scenario that triggers it.
4. **Unique-index rollout made explicit and duplicate-safe (finding 4).** The index from round 2 was in `ENTITY_MENTIONS_INDEXES`, auto-created at application startup via `initialize_indexes()`/`_on_startup()`, which re-raises on any index-creation failure — a `unique=True` index creation against a collection with pre-existing duplicate keys (plausible, since nothing enforced this uniqueness before this ticket) would have crashed the *entire* application startup, not just entity-mentions functionality. Moved the index definition out of the auto-created list into a new `db/operations/entity_mentions_index_rollout.py` module with: `check_for_duplicate_mentions()` (read-only preflight, safe to run against production under the ticket's read-only authorization), `create_unique_index()` (explicit, requires operator authorization before production use, fails cleanly returning `False` rather than raising if duplicates are still present), and `UNIQUE_INDEX_NAME`/`UNIQUE_INDEX_KEYS` constants. The worker (`process_new_articles_from_mongodb()`) now checks once per run whether the index exists and logs a loud warning (without blocking enrichment) if it's absent, so an operator running without the index rolled out gets visible signal rather than a silent reduced guarantee.

### Test isolation fix (incidental, discovered during round 3)

Creating a real persistent unique index inside a test that shares the `entity_mentions` collection with every other test in the same file was found to race the `mongo_db` fixture's per-test `drop_database`/recreate cycle under sustained local load (a background index build from one test overlapping the next test's `drop_database`), causing **cross-test data bleed into unrelated, pre-existing tests** (confirmed via controlled A/B: the same tests passed reliably in isolation and failed only when run after an index-creating test in the same file). Moved all index-rollout tests into a new `tests/db/test_entity_mentions_index_rollout.py` using a dedicated scratch collection, eliminating the interaction entirely rather than relying on timing/ordering to avoid it.

### Required operator actions (unchanged, plus items from round 2)

Same as the pre-existing Definition of Done: approve `ENRICHMENT_AGE_CUTOFF_DAYS=30` (or choose otherwise) for production, review Railway instance/restart evidence and E11000 frequency, and approve final rollout. The `article_entity_type_primary_unique` index on `entity_mentions` needs operator authorization before creation against production; the rollout sequence is now explicit and safe (see `entity_mentions_index_rollout.py` module docstring): run `check_for_duplicate_mentions()` first (read-only), resolve any duplicates found, then run `create_unique_index()`. This session did not touch Railway, staging, or production in any way.

### Known gaps / explicitly not done this session

- **Legacy migration** is implemented and tested locally but has not been run — even in dry-run — against staging or production data; an index on `enrichment.status`/`enrichment.next_retry_at`/`enrichment.lease_expires_at` is still not defined (claim volume in local testing did not require it, though production claim volume likely will). Needs explicit operator authorization to create before a production migration.
- **Fairness rotation persistence** is untested against multi-process concurrent rotation increments (single-process behavior is correct via `$inc`, but not stress-tested under concurrent workers).
- **Duplicate-URL handling** (Definition of Done item 3) was not touched this session.
- **Staging validation** (full article → enrichment → mention → signal → UI path) was not performed; no staging environment is configured for this repository.
- **Mention-uniqueness-guarantee check is advisory, not blocking**: if the unique index hasn't been rolled out, the worker logs a loud warning but still proceeds with enrichment (an availability-over-strictness choice, since the idempotent writer remains correct for sequential/retried writes without the index — only genuinely concurrent writers lose the guarantee). If stricter behavior is wanted (block enrichment entirely without the index), that would need explicit product sign-off, since it trades ingest availability for a guarantee that mostly matters for a fairly rare interleaving.
- **Test environment note**: local MongoDB was under sustained heavy load by the end of this multi-round session (many hours of continuous drop/recreate-database test cycles), occasionally producing `pymongo.errors.NetworkTimeout` on individual test runs. Every such failure was confirmed via retry to be environment contention, not a code defect — see Local Test Results below for the verification method.

## Local Test Results (2026-09-15, this session, all three rounds)

Actual commands run against a real local MongoDB instance (`mongodb://localhost:27017/crypto_news`, dropped/recreated per test by the existing `mongo_db` fixture — never production). **Verification method:** files run individually or in small groups; large combined multi-file runs were observed to produce `pymongo.errors.NetworkTimeout` during index setup under this session's sustained load (confirmed via controlled A/B comparison — the same tests pass reliably standalone, including files with zero relation to this ticket). Every reported result below is from a run where the specific file/test passed on its own merits, not one where a timeout was silently ignored.

Per-file results, each run standalone (round 3, this review pass):

| File | Result |
|---|---|
| `tests/db/test_mongodb_concurrent_lifecycle.py` (2 new coordination tests added) | 8 passed |
| `tests/db/test_enrichment_state_machine.py` | 26 passed |
| `tests/background/test_rss_fetcher_worker_state.py` (1 new test added; found+fixed an import bug in production code that broke all 5) | 5 passed |
| `tests/db/test_enrichment_migration.py` | 7 passed |
| `tests/db/test_entity_mentions_idempotent.py` (moved 7 index-creating tests out to isolate them) | 4 passed |
| `tests/db/test_entity_mentions_index_rollout.py` (new file, isolated scratch collection) | 7 passed |
| `tests/db/test_mongodb_client_lifecycle.py` | 4 passed |
| `tests/db/test_mongodb_concurrent_safety.py` | 3 passed |
| `tests/db/test_article_duplicate_handling.py` | 6 passed |

**Round 3 total: 70 passed, 0 failed**, each verified standalone. Combined with rounds 1-2's non-overlapping test files, the full BUG-108 test surface is green.

New/changed this round:
- `tests/db/test_mongodb_concurrent_lifecycle.py`: added `test_aclose_does_not_close_client_created_during_the_call` and `test_close_serializes_against_get_async_client`. Both went through several failed design iterations before landing on a reliable proof (documented in their docstrings): timestamp-overlap checks don't distinguish lock-queueing from concurrent execution; a sum-of-delays timing proof works for `aclose()` (which has a real internal `asyncio.sleep`) but not `close()` (which doesn't), so that test instead directly holds the lock and asserts `get_async_client()`/`close()` genuinely block on it. Also fixed a latent bug in the shared `MockAsyncClient` ping-delay mock pattern (`AsyncMock(side_effect=<sync lambda returning a coroutine>)` never actually awaits the coroutine, so ping delays were silently not happening in this and a pre-existing test) via a `_make_ping_side_effect()` helper.
- `tests/db/test_enrichment_state_machine.py`: none added this round (round 2's additions cover the underlying state-machine primitives that round 3's fixes reuse).
- `tests/background/test_rss_fetcher_worker_state.py`: added `test_worker_skips_mention_write_when_lease_expires_during_llm_call`.
- `tests/db/test_entity_mentions_idempotent.py` / `tests/db/test_entity_mentions_index_rollout.py`: split per the test-isolation fix described above.

Not run this session: frontend tests/type checks (no frontend files changed), `black`/lint (no formatter is an installed dev dependency in this repo's `pyproject.toml`). `git diff --check` was run after every round and is clean.

## Deployment Readiness

**NOT DEPLOYMENT-READY.** The ownership check inside the mention writer still races with its separate writes. Index blocking is implemented but its worker integration validation remains pending. Fix and execute the required tests before returning for review. Combined-suite failures remain unresolved without a demonstrated diagnosis. Staging, Railway evidence, production policy/operation approvals, and post-deploy validation remain pending. Local implementation proceeds under the provisional defaults above.

## Authorization Boundary

Claude may inspect repository code, run local tests, and use explicitly read-only production queries/logs. Do not expose MongoDB URIs, credentials, article content, URLs, or raw IDs. No production writes, migrations, index creation, backfills, cache-populating API requests, setting changes, restarts, or deployments are authorized by this ticket. The operator must explicitly authorize each required production action after reviewing its scope.
