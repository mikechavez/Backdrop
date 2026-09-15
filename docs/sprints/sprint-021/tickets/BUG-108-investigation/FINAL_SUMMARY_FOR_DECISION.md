# BUG-108: Final Summary for Operator Decision

**Status:** Investigation complete. Root cause identified but not fully validated. Fix design is rigorous with explicit state machine and retry policy. **Awaiting operator decision on backlog cutoff and authorization.**

---

## Root Cause (Confirmed via Code Analysis)

Two separate issues combine to create empty Signals page:

### Issue 1: Unbounded Backlog Query

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`, lines 426-443

```python
articles_list = []
async for article in collection.find(enrichment_query):
    articles_list.append(article)  # ← Loads ALL 13,496+ matching articles
```

**Impact:**
- Memory pressure (65-130 MB for 13,496 articles × 5-10 KB each)
- No progress checkpoint across restarts
- Repeated cycles re-process same articles

### Issue 2: Tier 2/3 Articles Stay Eligible for Retry

**File:** Same location, tier classification logic (lines 668-685)

Tier 2/3 articles have only `relevance_tier` set, but other fields (`relevance_score`, `sentiment_score`, `sentiment`) remain missing.

**Result:** Query still matches them next cycle → Re-selected, tier classified AGAIN, enrichment SKIPPED AGAIN → Infinite loop

**Consequence:** If all articles classified as tier 2/3, zero entity mentions created → Empty Signals page

---

## What Needs Operator Validation (Before Fix Authorization)

### Must Provide: Railway Evidence

**Cannot proceed without this; impacts root cause confidence:**

1. **Is this single instance or multiple replicas?**
   - Check Railway Deployments tab and Events for 2026-09-13 21:45-22:48 UTC
   - Are restart events from single container crashing or scale-up events?

2. **Did batch extraction complete or halt?**
   - Search logs for "Processing entity extraction batch 0-10" at 21:45:58
   - Search for "10-20", "20-30" — did batches progress?
   - Search for "Entity extraction complete" — was enrichment finished?
   - If halted, at which batch and what error?

3. **Baseline E11000 frequency:**
   - Search logs for "E11000" in last 7 days
   - How often do duplicate-key errors occur? (Daily? Hourly? Per-cycle?)
   - Baseline before fix; will re-assess after to check for regressions

**Why this matters:** 
- Confirms whether restart loop, E11000 errors, NoneType errors, or OOM is the actual blocking issue
- Validates that fix targets the right problem
- Provides baseline metrics for post-deployment monitoring

### Must Decide: Backlog Age Cutoff

**Three options, choose one:**

**Option A — Unlimited (No age cutoff)**
```
enrichment_query: All unenriched articles, regardless of age
```
- Pros: No articles left behind; eventually processes everything
- Cons: First cycle loads 13,496 articles (memory spike); takes ~13.5 hours to clear

**Option B — 30-day fresh only (Recommended)**
```
enrichment_query: Articles created in last 30 days + unenriched
```
- Pros: Bounded backlog (~30d worth); memory safe; fresh articles prioritized
- Cons: Articles older than 30d not enriched; acceptable if fresh content exists for Signals page

**Option C — Progressive (Hybrid)**
```
If fresh backlog < 100: Process last 90 days
Else: Process last 30 days only
```
- Pros: Prioritizes high-value fresh articles; eventually processes historical
- Cons: More complex; still takes time

**Recommendation:** Start with **Option B** (30-day fresh only). Historical articles can be backfilled separately if needed after fix is stable.

---

## Fix Design: State Machine + Retry Policy

### What the Fix Does

Adds explicit tracking of article processing state and retry logic:

**New field:** `enrichment_state: {status, last_attempt, attempt_count, error, completed_at}`

| State | Meaning | Re-selected? |
|-------|---------|--------------|
| `pending` | Never processed | Yes |
| `in_progress` | Currently processing | Only if stuck >60s (hung detection) |
| `completed` | Done (regardless of tier or retry count) | **Never** |
| `failed` | Transient error | Yes, after backoff (5-30 min) |

### Guarantees (Actual, Not Overstated)

**GUARANTEED:**
- ✅ No article processed by two concurrent processes (atomic claim)
- ✅ Articles marked `completed` never re-selected (even if fields missing)
- ✅ Hung `in_progress` articles (>60s stale) are detected and re-attempted
- ✅ Transient failures retry with backoff (3 attempts max, 5-30 min delays)
- ✅ Progress preserved across restarts (only articles reaching `completed` are skipped)

**NOT GUARANTEED:**
- ❌ "No article selected twice" — If crash before `completed` is written, article re-selected on restart (legitimate retry of lost work)
- ❌ "Immediate processing" — Failed articles only retry after backoff delays
- ❌ "All historical articles" — With age cutoff, old articles (>30d) are skipped

### Test Cases (Local, No Staging Required)

Six unit tests demonstrating interrupt safety and state transitions:
1. Tier 1 happy path (processes to completion)
2. Tier 2/3 marked completed (not re-selected despite missing fields)
3. Hung detection (in_progress >60s detected and eligible for re-attempt)
4. Backoff schedule (failed articles retry with 0min, 5min, 30min delays)
5. Max retries exceeded (marked completed with error after 3 failed attempts)
6. Atomic claim (two processes can't both claim the same article)

All in `STATE_MACHINE_AND_RETRY_POLICY.md`, ready to run locally.

---

## Code Changes Required

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`

**Complexity:** ~40-50 lines of code

1. Add `enrichment_state` schema and initialization
2. Atomically set `in_progress` before processing (prevent double-claim)
3. Set `completed` after tier classification (tier 1, 2/3, or max retries all marked done)
4. Set `failed` and increment attempt_count on transient errors
5. Update enrichment_query to exclude articles with `status: completed`
6. Add optional age boundary (for backlog cutoff decision)

---

## Deployment & Monitoring

### Pre-Deployment

- [ ] Operator provides Railway topology and extraction batch trace evidence
- [ ] Operator decides on backlog cutoff (Option A, B, or C)
- [ ] Code review: Verify atomic `in_progress` claim and state transition logic
- [ ] Run 6 unit tests locally (demonstrate interrupt safety)
- [ ] No staging deployment needed (state machine logic can be tested in unit tests)

### Post-Deployment (48 hours)

**Monitor these queries after each enrichment cycle:**

```javascript
// Should increase by ~500 per cycle (progress)
db.articles.countDocuments({
  "enrichment_state.status": "completed",
  "enrichment_state.completed_at": {"$gt": <1 hour ago>}
})

// Should decrease by ~500 per cycle (backlog shrinking)
db.articles.countDocuments({
  "enrichment_state.status": {"$in": ["pending", "failed", "in_progress"]},
  "created_at": {"$gte": <30 days ago>}  // If using Option B cutoff
})

// Should increase as mentions created
db.entity_mentions.countDocuments({
  "created_at": {"$gt": <1 hour ago>}
})
```

---

## Separate Issues (Not Fixed by This Change)

### BUG-108-A: E11000 Duplicate-Key Errors

**Current behavior:** `create_or_update_articles()` uses batch insert; any duplicate fails entire batch → Enrichment skipped for that cycle

**Investigation needed:**
- Does the function use upsert semantics or all-or-nothing batch insert?
- Should duplicates be updated instead of rejected?
- What is the frequency and impact?

**Separate ticket recommended** after this fix is stable.

### BUG-108-B: NoneType Errors in Extraction

**Current behavior:** LLM response parsing or selective processor fails → Batch extraction halts → Zero entities extracted

**Investigation needed:**
- Trace exact failure point (lines 283-285, 477, or elsewhere)
- Add defensive null checks in LLM response parsing
- Determine if these errors are transient (retry candidate) or permanent

**Separate ticket recommended** after this fix is stable.

### PRODUCT-X: Signals Timeframe Reconciliation

**Current mismatch:** UI label says "24h" but API defaults to "7d"

**Decision needed:** Should Signals display 24h, 7d, or configurable?

**Separate product decision** after Signals page starts showing results.

---

## Decision Checklist for Operator

**Before authorizing fix, confirm:**

- [ ] Reviewed code analysis: Unbounded query + tier 2/3 infinite loop identified
- [ ] Reviewed state machine design: Explicit state transitions, retry policy, interrupt safety
- [ ] Reviewed test cases: 6 unit tests cover happy path, tier 2/3, hung detection, backoff, max retries, atomic claim
- [ ] Will provide Railway evidence: Topology, extraction trace, E11000 baseline
- [ ] Will decide on backlog cutoff: Option A (unlimited), Option B (30d fresh), or Option C (progressive)
- [ ] Understands what is guaranteed: No double-processing, hung detection, backoff, but not immediate progress
- [ ] Understands what is NOT guaranteed: "No re-selection" if crash before `completed` written, all historical articles with age cutoff
- [ ] Accepts post-deployment monitoring: Will track backlog count, completion count, mention rate per cycle

**Once checklist complete:** Fix can proceed to code review, testing, and deployment.

---

## Timeline

**Today (Phase 1: Validation)**
- Operator provides Railway evidence (topology, extraction trace, baseline)
- Operator decides on backlog cutoff (A, B, or C)
- Code review passes

**Tomorrow (Phase 2: Implementation)**
- Engineer implements state machine + retry policy (~2-3 hours)
- Run 6 unit tests locally (~30 min)
- Code review + merge to main

**Day 3 (Phase 3: Deployment)**
- Deploy to production (standard Railway process)
- Monitor for 48 hours (check backlog count, completion, mentions)

**Day 5 (Phase 4: Validation)**
- Confirm Signals page shows results (or understand why not)
- Establish baseline metrics (mention rate, tier distribution, error rate)
- Mark BUG-108 resolved

---

## Risk Assessment

### Low Risk
- ✅ State machine only adds tracking; doesn't change enrichment logic
- ✅ Atomic claim uses MongoDB `find_one_and_update` (well-tested pattern)
- ✅ Can be rolled back easily (just revert code)

### Medium Risk
- ⚠️ New `enrichment_state` field requires schema migration (add to all articles)
- ⚠️ Backlog cutoff decision impacts which articles are processed
- ⚠️ E11000 and NoneType errors not fixed (separate issues; may still block progress)

### Mitigations
- ✅ Schema migration: Backfill `enrichment_state` field on first startup (articles default to `pending`)
- ✅ Backlog cutoff: Start with Option B (safe, bounded); can change later if needed
- ✅ Error path: State machine treats E11000 and NoneType as transient failures (retry with backoff)

---

## What You're Authorizing

**You are NOT authorizing:**
- ❌ Fix for E11000 duplicate-key errors (separate issue)
- ❌ Fix for NoneType errors (separate issue)
- ❌ Changes to Signals UI/API (separate product decision)
- ❌ Historical article backfill (separate feature, can run after fix is stable)

**You ARE authorizing:**
- ✅ State machine + retry policy for enrichment pipeline
- ✅ Backlog age cutoff (your choice: A, B, or C)
- ✅ Deployment of ~40-50 line fix to production
- ✅ 48-hour monitoring period to establish baselines

---

## Questions for Clarification

Before you authorize, if any of these are unclear, let me know:

1. **Is the state machine design sound?** Explicit states, atomic claims, interrupt safety all correct?
2. **Is the retry backoff reasonable?** (0min, 5min, 30min for 3 attempts)
3. **Is 60-second stale threshold reasonable for hung detection?** (Cycle time is ~30 min, so 60s is conservative)
4. **Which backlog cutoff preferred?** Option A (unlimited), Option B (30d fresh), or Option C (progressive)?
5. **Is it OK to separate E11000 and NoneType investigation?** (I can document them as BUG-108-A/B for separate tickets)
6. **Any production operational constraints** I should know about? (Deployment windows, monitoring setup, rollback procedures?)

---

**Ready to proceed once:**
1. Operator provides Railway evidence
2. Operator decides on backlog cutoff
3. Operator approves state machine design

