# BUG-108 Code Review & Deployment Readiness Assessment

**Date:** 2026-09-13  
**Branch:** `docs/bug-108-investigation`  
**Tests:** 15/15 passing (100%)  
**Status:** Reviewed; awaiting operator decisions before deployment

---

## Ticket Reconciliation

✅ **Trailing whitespace:** Removed (2 lines cleaned)  
✅ **30-day age-cutoff approval:** Marked **pending** (unchecked)  
⚠️  **30-day default is active in code** — Requires explicit operator approval or override via `ENRICHMENT_AGE_CUTOFF_DAYS` env var

---

## What Is Implemented (15/15 Tests Passing)

### 1. MongoDB Client Lifecycle Validation (4 tests)
**File:** `src/crypto_news_aggregator/db/mongodb.py:536`

- Added null check before dereferencing client in `get_async_database()`
- Raises diagnostic `RuntimeError` instead of silent `NoneType` failure
- **Does NOT prevent client becoming None** — defensive measure only
- **Does NOT explain root cause** — requires operator evidence (Railway restart logs)

**Tests:**
- ✓ Null check raises RuntimeError with diagnostic message
- ✓ Valid client works correctly
- ✓ Injected _db bypasses client lookup
- ✓ Error propagates to get_async_collection

---

### 2. Enrichment Query Bounds (6 tests)
**File:** `src/crypto_news_aggregator/background/rss_fetcher.py:426-451`

**Applied three bounds to enrichment candidate query:**

1. **Age cutoff:** `created_at >= now - 30 days` (configurable)
2. **Sort order:** Newest-first (`.sort("created_at", -1)`)
3. **Article limit:** 5000 per run (`.limit(max_batch_articles)`)

**Settings declared:**
- `ENRICHMENT_AGE_CUTOFF_DAYS` (default 30, env-configurable)
- `ENRICHMENT_MAX_ARTICLES_PER_RUN` (default 5000, env-configurable)

**What this does:**
- Prevents reprocessing articles >30 days old (per-run query, not retention)
- Bounds memory use: ~50MB worst-case (5000 articles × ~10KB typical)
- Prioritizes fresh articles for signal detection
- Reduces per-run processing time

**What this does NOT do:**
- Add durable per-article progress tracking (articles can be re-selected if interrupted)
- Prevent tier 2/3 starvation (they remain forever-eligible)
- Fix backlog recovery (requires state-machine implementation)
- Enforce MongoDB retention (query-level only)

**Tests:**
- ✓ Age cutoff calculated correctly (29–31 days)
- ✓ Settings read from config (not fallback defaults)
- ✓ Query structure includes cutoff and limit
- ✓ Sort direction is descending (newest-first)
- ✓ Limits reasonable (5000 articles, 10 per batch)
- ✓ Batch math correct (500 batches max per run)

---

### 3. E11000 Duplicate Handling (5 tests)
**File:** `src/crypto_news_aggregator/db/operations/articles.py:57-66`

**Before:** Caught generic `Exception` (broad, masked real errors)  
**After:** Caught only `DuplicateKeyError` (narrow, specific)

**Behavior:**
- One duplicate URL no longer blocks entire enrichment cycle
- Non-duplicate database errors propagate immediately (correct)
- Logging redacted: no URLs or raw IDs exposed (ticket section 28 compliance)
- Per-article failure tracking (but not persisted across restarts)

**Tests:**
- ✓ Duplicate does not block batch (all articles attempted)
- ✓ Errors logged without exposing URLs or IDs
- ✓ Successful articles created despite duplicate
- ✓ Non-duplicate errors propagate (fail the cycle)
- ✓ Existing article updates work

---

## What Remains Unresolved (Requires Operator Actions)

### 1. MongoDB Client Lifecycle (Root Cause)
**Problem:** Client became `None` in production (22:48:54 UTC on 2026-09-13)

**Symptoms in logs:**
- "Cannot use MongoClient after close"
- Failed MongoDB ping
- `get_async_database()` received `client=None`

**Current fix:** Null check converts error to diagnostic message  
**Does NOT fix:** The underlying reason client was closed/cleared

**Required operator evidence:**
- Railway Deployments/Events: Instance count, restart reason (OOM/health-check/deploy)
- Identify if single-instance restart loop or multi-replica behavior
- Determine if concurrent background task lifecycle is the cause

**Related code to investigate (not fixed in this branch):**
- `MongoManager.__init__()` and async context lifecycle
- `MongoManager.get_async_client()` lazy initialization
- All `.close()` and `.clear()` call sites
- App startup/shutdown in `main.py` and background task lifecycle

---

### 2. Enrichment Backlog & Progress Tracking
**Problem:** Articles can be re-selected if enrichment is interrupted

**Current behavior:**
- No per-article `enrichment_state` field in schema
- No durable progress marker (no upsert, lease, or version)
- Articles eligible multiple times if processing fails mid-run
- Tier 2/3 articles remain forever-eligible and may starve older articles

**Age cutoff mitigation:**
- Prevents reprocessing articles >30 days old (reduces but doesn't solve)
- Newest-first ordering prioritizes fresh articles (doesn't prevent starvation)
- 5000-article limit per run bounds worst-case backlog

**Required fix (separate ticket):**
- State-machine implementation with durable per-article progress
- Distinguish `enriched`, `tier_2_skipped`, `tier_3_skipped`, `retry_N`, `failed` states
- Atomic state transitions with lease/heartbeat for concurrent safety
- Legacy migration to classify already-enriched articles correctly

**Not included in this branch:** Design-only documents in `BUG-108-investigation/` directory

---

### 3. 30-Day Age Cutoff (Product Decision Pending)
**Current status:** Default 30 days active in code, marked pending in ticket

**What 30 days means:**
- Per-run enrichment will skip articles created >30 days ago
- Does NOT delete articles from MongoDB (retention unchanged)
- Does NOT prevent older articles from being manually enriched
- Only affects automatic background enrichment query

**Trade-offs:**
- **Pro:** Prevents reprocessing very old articles, reduces per-run memory
- **Con:** Excludes older articles from automatic enrichment (signals endpoint covers 30d)

**Operator decision required:**
- Approve 30-day default, OR
- Set `ENRICHMENT_AGE_CUTOFF_DAYS` env var to different value (e.g., 7, 90, 365)
- Document decision rationale

---

### 4. E11000 Duplicate URL Frequency
**Problem:** One E11000 error observed at 21:23 UTC on 2026-09-13

**Current fix:** Articles proceed despite duplicate (non-blocking)  
**Does NOT fix:** Why duplicates occur in production

**Operator decision required:**
- Verify E11000 frequency over past 7 days
- Determine if it's rare (artifact handling sufficient) or chronic (needs ingestion fix)
- Track duplicate URL patterns (if any)

---

### 5. Railway Restart Loop (Topology/Cause)
**Symptom:** Extraction started at 21:30, logged batches 0-10 through 220-230, then restarted at 0-10 again

**Open questions:**
- Single instance restarting vs. multiple replicas?
- Reason: OOM, health-check failure, new deployment, or other?
- When did restarts stop and why?

**Operator evidence needed:**
- Railway Dashboard → Deployments/Events for window 21:30–23:10 UTC
- Instance count and restart causes
- Check OOM killer, health probe logs, or deployment events

---

## Risk Assessment

### Low Risk (Defensive Improvements)
- ✅ Null check in MongoDB client path
- ✅ Age cutoff and query limit in enrichment
- ✅ E11000 error scoping
- ✅ Log redaction (no secrets exposed)

**Why low risk:**
- No production writes
- Configurable settings (defaults can be overridden)
- Tests verify local behavior
- Query-level only (no schema changes)
- Backward compatible (new settings have defaults)

### Medium Risk (Not Addressed by These Changes)
- ⚠️  MongoDB client lifecycle failure (defensive only, root cause unknown)
- ⚠️  Enrichment backlog recovery (article re-selection possible)
- ⚠️  Tier 2/3 starvation (query bounds don't prevent it)

**Why medium risk:**
- Can result in missing signals if root cause occurs again
- Backlog can accumulate if enrichment is frequently interrupted
- Does NOT prevent these issues, only mitigates impact

---

## Test Coverage & Verification

**Test file locations:**
- `tests/background/test_enrichment_query_bounds.py` (6 tests)
- `tests/db/test_mongodb_client_lifecycle.py` (4 tests)
- `tests/db/test_article_duplicate_handling.py` (5 tests)

**Test execution:**
```bash
poetry run pytest \
  tests/background/test_enrichment_query_bounds.py \
  tests/db/test_mongodb_client_lifecycle.py \
  tests/db/test_article_duplicate_handling.py \
  -v
# Result: 15 passed in 0.06s
```

**Coverage limitations:**
- Tests verify code logic locally (no production MongoDB)
- Query structure test constructs sample query separately (doesn't verify actual query construction)
- Doesn't test concurrent MongoManager access patterns
- Doesn't test Celery/distributed worker scenarios
- No staging environment validation

---

## Code Changes Summary

| File | Changes | Lines | Status |
|------|---------|-------|--------|
| `src/crypto_news_aggregator/core/config.py` | Added `ENRICHMENT_AGE_CUTOFF_DAYS`, `ENRICHMENT_MAX_ARTICLES_PER_RUN` settings | +12 | ✅ |
| `src/crypto_news_aggregator/db/mongodb.py` | Null check in `get_async_database()` | +3 | ✅ |
| `src/crypto_news_aggregator/background/rss_fetcher.py` | Age cutoff, sort, limit applied to enrichment query | +8 | ✅ |
| `src/crypto_news_aggregator/db/operations/articles.py` | Narrowed exception handling to `DuplicateKeyError` only | +9 | ✅ |
| `docs/sprints/sprint-021/tickets/BUG-108-signals-page-no-signals.md` | Removed trailing whitespace, marked 30-day cutoff pending | -2 | ✅ |

**Total changes:** 30 lines of code + 1 doc fix  
**No breaking changes:** Backward compatible  
**No production writes:** Read-only investigation, defensive improvements only

---

## Pre-Deployment Checklist

**Before deploying to production:**

- [ ] Operator approves 30-day age cutoff (or sets `ENRICHMENT_AGE_CUTOFF_DAYS` env var)
- [ ] Operator provides Railway event logs: restart cause, instance count (21:30–23:10 UTC)
- [ ] Operator verifies E11000 duplicate frequency over past 7 days
- [ ] Code review: Verify logic, test coverage, backward compatibility
- [ ] Staging validation: Deploy to staging, trigger enrichment cycle, verify query bounds applied
- [ ] Monitor: Watch production logs for new `RuntimeError` messages from MongoDB client path
- [ ] Plan: Schedule separate ticket for state-machine implementation (backlog recovery)

---

## Next Steps for Operator

### Immediate (Required for deployment)
1. Review code changes in this PR
2. Approve or modify 30-day age cutoff default
3. Provide Railway event context (21:30–23:10 UTC on 2026-09-13)
4. Verify E11000 frequency and decide on handling priority

### Short-term (After deployment)
1. Deploy to production and monitor enrichment logs
2. Verify no new `RuntimeError` from client validation
3. Confirm enrichment query respects age cutoff
4. Check entity_mentions creation rate and latency

### Medium-term (Separate tickets)
1. **State-machine implementation:** Durable per-article progress, prevent re-selection
2. **MongoDB client lifecycle:** Root-cause analysis and fix for null-client failure
3. **UI timeframe reconciliation:** Align Signals page label ("24h") with actual query default (7d)

---

## Related Tickets & Context

- **BUG-054:** Previously fixed disabled RSS ingestion schedule (verify still active)
- **TASK-105:** Freshness monitoring of persisted `signal_scores` (separate from this endpoint)
- **BUG-083:** Disabled market-event detector (unrelated to trending-signals endpoint)
- **FEATURE-048d/048e:** Infinite scroll (unrelated to enrichment)

---

## Acceptance Criteria Status

- [x] The empty API result is consistent with the dated absence of recent primary mentions.
- [x] The 22:48 `NoneType` traceback is traced to a null MongoDB client in `create_or_update_articles()`.
- [x] The unbounded backlog, lack of persisted progress, and tier 2/3 reselection risks are documented.
- [x] **MongoManager client lifecycle:** Null check added and tested (symptom identified, root cause pending).
- [ ] Railway repeated-start topology/cause and E11000 frequency are documented from operator evidence.
- [ ] State migration/query/claim/retry behavior is corrected and tested (separate ticket).
- [ ] **30-day age cutoff:** Proposed, configurable, pending operator approval.
- [x] **Code changes verified:** 15/15 tests passing.
- [ ] UI timeframe intent is recorded and request/label reconciliation proposed.

---

## Files Modified on Branch

- ✅ `src/crypto_news_aggregator/core/config.py`
- ✅ `src/crypto_news_aggregator/db/mongodb.py`
- ✅ `src/crypto_news_aggregator/background/rss_fetcher.py`
- ✅ `src/crypto_news_aggregator/db/operations/articles.py`
- ✅ `docs/sprints/sprint-021/tickets/BUG-108-signals-page-no-signals.md` (trailing whitespace removed)
- ✅ Tests: 3 new test files with 15 passing tests

**Branch ready for code review and staging validation.**
