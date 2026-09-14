# BUG-108 Operator Action Checklist

**Ticket:** BUG-108: Investigate empty Signals page despite recent article ingestion

**Prepared:** Investigation complete, awaiting operator authorization

**Estimated time:** 45 minutes (investigation) + 10 minutes (deployment) + 30 minutes (monitoring)

---

## Phase 1: Confirm Root Cause (45 minutes, Read-Only)

### Step 1.1: Confirm Deployment Topology (5 minutes)

**In Railway dashboard:**
- [ ] Check **Deployments** tab → Note current environment (prod, staging, dev)
- [ ] Check **Services** → How many replicas for the API service? (Expected: 1)
- [ ] Check **Events** → Review restart events 21:00-23:00 UTC on 2026-09-13
- [ ] Note: Single instance starting multiple times = restart loop; multiple instances = replicas

**Expected result:** Confirms single instance with restart pattern, not multiple replicas.

### Step 1.2: Run MongoDB Investigation Queries (30 minutes, Read-Only)

**Prerequisite:** Have production MongoDB URI in environment

**Execute these 6 queries** (copy from `mongodb_investigation_queries.js`):

#### Query 1: Article Freshness ✅ (Should pass — we know articles are being ingested)
```bash
mongosh "$MONGODB_URI" --quiet
# Paste Query 1 from mongodb_investigation_queries.js
```
**Expected:** 44+ articles in 24h, 346+ in 7d (confirms ingestion working)

#### Query 2: Entity Mention Counts ❌ (Critical test — should show zero/very low)
```bash
# Paste Query 2 from mongodb_investigation_queries.js
```
**Expected:** 
- is_primary=true, last 24h: **0 mentions** ← ROOT CAUSE
- is_primary=true, last 7d: **0-5 mentions** 
- Last mention timestamp: Aug 24, 2026 (very old)

If this returns 0 for is_primary=true in 24h/7d: ✅ **Root cause confirmed**

#### Query 3: Enrichment Backlog by Age ⚠️ (Should confirm 13,496+ backlog)
```bash
# Paste Query 3 from mongodb_investigation_queries.js
```
**Expected:**
- total_unenriched: **13,496+** 
- last_1d: **100-300** (newest articles waiting)
- last_7d: **500+**
- last_30d: **4,000+**
- older_30d: **8,000+** (stale articles never enriched)

If total_unenriched > 10,000: ✅ **Backlog confirmed**

#### Query 4: Enrichment Field Completion (2 minutes, sanity check)
```bash
# Paste Query 4 from mongodb_investigation_queries.js
```
**Expected:** Large number of articles missing relevance_score, sentiment_score, entities

#### Query 5: Article Linkage Validation (2 minutes)
```bash
# Paste Query 5 from mongodb_investigation_queries.js
```
**Expected:** Most primary mentions have matched articles (not orphaned)

#### Query 6: Trending Signals Endpoint Simulation ❌ (Critical test)
```bash
# Paste Query 6 from mongodb_investigation_queries.js
```
**Expected:**
- 24h window: **0 entities** ← Signals page result
- 7d window: **0 entities** 
- 30d window: **1-5 entities** ← Old data from Aug 24

If 24h/7d return 0 but 30d returns >0: ✅ **Recency boundary confirmed**

### Step 1.3: Review Extraction Logs (10 minutes)

**In Railway logs, search for:**
- [ ] `"Processing entity extraction batch"` at 21:45:58
- [ ] Note: Did it reach batch 10-20? 20-30? Or stop at 0-10?
- [ ] Search for `"Entity extraction complete"` — was this message logged?
- [ ] Search for `"E11000"` — did duplicate key error occur?
- [ ] Search for `"NoneType"` at 22:48 UTC — get full traceback
- [ ] Search for `"Entity mentions batch: created="` — how many mentions were inserted?

**Expected:** 
- Batch 0-10 logged ✅
- No "batch 10-20" or beyond ❌ (process halted)
- "Entity extraction complete" not logged ❌ (incomplete)
- E11000 or NoneType error logged ✅ (blocking error identified)

---

## Phase 2: Code Review (10 minutes, No Production Changes)

### Step 2.1: Review Proposed Fix

**File to review:** `src/crypto_news_aggregator/background/rss_fetcher.py` (lines 399-449)

**Check:**
- [ ] Function: `process_new_articles_from_mongodb()`
- [ ] Constants added at top:
  - `MAX_BACKLOG_PER_CYCLE = 500` ✅
  - `MAX_BACKLOG_AGE_DAYS = 30` ✅
- [ ] Enrichment query replaced:
  - Has age boundary: `"created_at": {"$gte": min_created_at}` ✅
  - Has limit: `.limit(MAX_BACKLOG_PER_CYCLE)` ✅
  - Has sort: `.sort("created_at", -1)` ✅ (newest first)
- [ ] Backlog logging added: Warning message if backlog > limit ✅
- [ ] No removal of error handling or mention creation logic ✅

### Step 2.2: Verify Risk Assessment

- [ ] Low risk? (Only query input changes, no business logic changes) ✅
- [ ] Reversible? (Can revert to previous query if needed) ✅
- [ ] No breaking changes? (Existing mention creation logic unchanged) ✅
- [ ] Age cutoff (30d) aligns with product retention policy? ✅

---

## Phase 3: Deployment Authorization (5 minutes)

### Step 3.1: Confirm Root Cause

**Checklist before proceeding:**
- [ ] MongoDB Query 2 confirmed: 0 primary mentions in 24h/7d
- [ ] MongoDB Query 3 confirmed: 13,496+ total unenriched articles
- [ ] MongoDB Query 6 confirmed: Trending signals 0 for 24h/7d
- [ ] Railway logs confirmed: Batch extraction halted, E11000 or NoneType error
- [ ] Root cause accepted: Unbounded backlog + restart loop + error conditions

**If all above confirmed:** ✅ **Proceed to deployment**

### Step 3.2: Authorization

**Review decision matrix:**

| Condition | Status | Decision |
|-----------|--------|----------|
| Root cause confirmed (unbounded backlog) | ✅ Yes | → Proceed |
| Fix is minimal (<20 lines) | ✅ Yes | → Proceed |
| Risk assessment is low | ✅ Yes | → Proceed |
| Code review approved | [ ] Yes | → Proceed |
| No production data modification | ✅ Yes | → Proceed |
| Can be reverted if needed | ✅ Yes | → Proceed |

**If all checks pass:** ✅ **Authorize deployment**

---

## Phase 4: Deployment (10 minutes)

### Step 4.1: Merge Fix to Main

**Standard process:**
- [ ] Engineer: Create PR from `fix/bug-108-bounded-enrichment`
- [ ] You: Review code changes (see Phase 2 above)
- [ ] You: Approve PR
- [ ] Engineer: Squash merge to main (standard workflow)

### Step 4.2: Deploy to Production

**Standard Railway process:**
- [ ] In Railway dashboard: Trigger deployment from main branch
- [ ] Monitor deployment progress (should take 2-5 minutes)
- [ ] Wait for new deployment to reach "Running" status
- [ ] Note deploy timestamp (will use for log correlation)

**If deployment fails:**
- [ ] Check Railway logs for build or startup errors
- [ ] If issue found: Engineer investigates and fixes
- [ ] If no clear issue: Rollback to previous deploy
- [ ] Re-assess before retry

### Step 4.3: Initial Health Check (2 minutes after deploy)

**In Railway logs:**
- [ ] Search for `"Running initial RSS fetch on startup..."`
- [ ] Search for `"Processing X articles with cost-optimized extraction"`
- [ ] Look for errors or exceptions in first 5 minutes

**Expected:** New deployment starts, runs enrichment with bounded query, completes without errors.

---

## Phase 5: Monitoring & Validation (30 minutes post-deployment)

### Step 5.1: Immediate Checks (5 minutes, right after deploy)

**Monitor logs for 5 minutes:**
- [ ] Check: `"Processing X articles with cost-optimized extraction"` appears
- [ ] Note: X should be between 1 and 500 (bounded)
- [ ] Check: No `"E11000"` errors (if it appears again, note it)
- [ ] Check: No `"NoneType"` errors (if new errors, investigate)
- [ ] Check: `"Entity extraction complete: articles=X, llm=Y, regex=Z"`

**Expected:** Enrichment runs to completion without E11000 or new NoneType errors.

### Step 5.2: Mention Creation Validation (10 minutes)

**Run MongoDB query to check mention creation:**
```bash
mongosh "$MONGODB_URI" --quiet
db.entity_mentions.countDocuments({
  "created_at": { "$gte": new Date(Date.now() - 5*60*1000) }  // Last 5 minutes
})
```
- [ ] Count should be > 0 (mentions being created)
- [ ] Note the count (baseline for next cycle)
- [ ] Re-run in 5 minutes: Count should increase

**Expected:** 50+ mentions created in first 5-10 minutes (vs. 0 before fix).

### Step 5.3: Signals Page Verification (5 minutes)

**Test production Signals page:**
- [ ] Browser: Load `https://context-owl.com/signals` (or staging equivalent)
- [ ] Check: Page no longer shows "No signals detected yet" ✅
- [ ] Check: Should show 5-15 entities (Bitcoin, Ethereum, etc.) ✅
- [ ] Check: Each entity shows recent mention count ✅

**Expected:** Signals page shows trending entities within 2-5 minutes of deployment.

### Step 5.4: Backlog Reduction Tracking (30 minutes total, ongoing)

**Monitor backlog per cycle:**

Run this query every 10 minutes:
```bash
mongosh "$MONGODB_URI" --quiet
db.articles.countDocuments({
  "created_at": { "$gte": new Date(Date.now() - 30*24*60*60*1000) },
  "$or": [
    { "relevance_score": { "$exists": false } },
    { "relevance_tier": { "$exists": false } }
  ]
})
```

**Expected progression:**
- T+0min: 13,496 articles
- T+30min: 12,996 articles (500 processed in first cycle)
- T+60min: 12,496 articles (another 500 processed)
- T+120min: 11,496 articles (steady 500/cycle progress)

**If not decreasing:** Something is wrong, investigate logs.

### Step 5.5: Tier Distribution Check (5 minutes)

**Monitor tier classification:**
```bash
mongosh "$MONGODB_URI" --quiet
db.articles.aggregate([
  { $match: { "relevance_tier": { $exists: true } } },
  { $group: {
    _id: "$relevance_tier",
    count: { $sum: 1 }
  } },
  { $sort: { _id: 1 } }
]).toArray()
```

**Expected:**
- Tier 1: 5-15% (high signal articles → yield mentions)
- Tier 2: 70-85% (default crypto news)
- Tier 3: 5-15% (low signal filtered out)

**If all articles tier 1 or all tier 3:** Classifier may be misconfigured.

---

## Phase 6: Post-Deployment Monitoring (48 hours)

### Daily Checklist (Morning + Evening)

**Day 1 (tomorrow, 2026-09-14):**
- [ ] Signals page still shows results
- [ ] No error spikes in logs
- [ ] Backlog continues decreasing (should reach <3,000 by end of day)
- [ ] Memory usage stable (no OOM incidents)
- [ ] Cost stable (no LLM retry storms from E11000 errors)

**Day 2 (2026-09-15):**
- [ ] Backlog near zero (should reach <500)
- [ ] Enrichment cycle time stable (<5 min per cycle)
- [ ] Mention creation rate stable (hundreds per cycle)
- [ ] No new errors or regressions

### Metrics Dashboard (Suggested)

Set up monitoring for:
- **Signals API response time:** Should be <500ms (was 45+ seconds before)
- **Entity mention creation rate:** Should be 500+ per cycle (was 0)
- **Enrichment backlog:** Should decrease to <500 (was 13,496)
- **Enrichment cycle time:** Should be <5 min (was stalled)
- **LLM API error rate:** Should be baseline (no increase from E11000)

---

## Rollback Plan (If Needed)

**If something goes wrong during monitoring (Phase 5):**

1. **Check logs first** — Understand the error before rolling back
2. **If clear regression** (Signals page broken, error spike):
   - [ ] In Railway: Trigger rollback to previous deploy
   - [ ] Wait for rollback to complete
   - [ ] Verify Signals page reverts to previous state
   - [ ] Report findings to engineer for investigation

**Rollback is safe because:**
- ✅ Fix is query-only (no data mutation)
- ✅ Previous deploy still functional
- ✅ No data loss or corruption risk

---

## Sign-Off Checklist

**Before marking BUG-108 as RESOLVED:**

- [ ] Root cause confirmed (unbounded backlog + restart loop)
- [ ] Fix deployed to production
- [ ] Signals page shows results (not "No signals detected")
- [ ] Entity mention creation rate >0 (was 0)
- [ ] Backlog decreasing per cycle
- [ ] Error rates stable (no new E11000/NoneType spike)
- [ ] 48-hour monitoring window passed with no regressions
- [ ] Documentation updated (lessons learned, monitoring guidance)

**Once all checks pass:** ✅ **BUG-108 RESOLVED**

---

## Questions to Track

| Question | Answer | Status |
|----------|--------|--------|
| Single instance or multiple replicas? | [ ] Single / [ ] Multiple | [ ] Pending |
| Did batch 0-10 complete or halt? | [ ] Complete / [ ] Halt | [ ] Pending |
| E11000 error confirmed? | [ ] Yes / [ ] No | [ ] Pending |
| NoneType error confirmed? | [ ] Yes / [ ] No | [ ] Pending |
| Are all articles tier 2-3 (no tier 1)? | [ ] Yes / [ ] No | [ ] Pending |
| Should we backfill articles >30d? | [ ] Yes / [ ] No / [ ] Later | [ ] Pending |

---

## Success Criteria (Final)

**BUG-108 is RESOLVED when:**

1. ✅ Signals page displays trending entities (not "No signals detected")
2. ✅ Entity mentions created in last 24h (was 0)
3. ✅ Enrichment backlog decreasing (<500 remaining within 48 hours)
4. ✅ No new error spikes or regressions
5. ✅ Production metrics stable (latency, cost, error rate)

**Estimated timeline:**
- Today: Confirm root cause (45 min) + authorize fix (5 min)
- Tomorrow: Deploy + monitor (1 hour active, then passive monitoring)
- Day 3: Final validation + close ticket

---

**Ready to proceed?** Please confirm:
1. [ ] Root cause investigation results reviewed
2. [ ] MongoDB queries run and results confirmed
3. [ ] Railway logs reviewed
4. [ ] Code fix reviewed and approved
5. [ ] Risk assessment accepted
6. [ ] Deployment authorized

Once all confirmed: **Engineer proceeds with PR + deployment. You monitor and validate.**
