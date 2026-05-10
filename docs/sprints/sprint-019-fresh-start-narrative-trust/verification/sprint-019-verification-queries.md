---
verification_id: SPRINT-019-VERIFICATION
title: Sprint 019 Fresh-Start Narrative Trust - Verification Queries
date_created: 2026-05-10
scope: Read-only validation queries for Sprint 019 deployment
status: REFERENCE
---

# Sprint 019 Verification Queries

## ⚠️ SAFETY HEADER

**All queries in this document are read-only. Do not execute mutation commands.**

### Critical Rules

- ✓ **Allowed:** Running read-only Mongo queries to inspect data
- ✓ **Allowed:** Running grep/git/build commands for code inspection
- ✗ **Forbidden:** Running `narrative_refresh` tasks in production unless explicitly approved by project lead
- ✗ **Forbidden:** Running `generate_briefing` jobs in production unless explicitly approved by project lead
- ✗ **Forbidden:** Using `updateMany`, `deleteMany`, `bulkWrite`, or other mutations
- ✗ **Forbidden:** Setting `last_summary_generated_at` as a shortcut to mark narratives trusted
- ✗ **Forbidden:** Mutating `narratives`, `daily_briefings`, `articles`, or `llm_traces` collections
- ✗ **Forbidden:** Modifying production data via scripts or ad hoc commands

**Remediation commands (if required) require explicit project lead approval and are not included in this document.**

---

## Configuration

All example queries use this cutoff date:

```
FRESH_START_CUTOFF = 2026-05-10T00:00:00Z
```

This date represents the Sprint 019 fresh-start boundary. Narratives and briefings created or refreshed on or after this date are considered "trusted" for briefing synthesis. Narratives older than this date without an explicit `_fresh_start_validated_at` flag are considered "untrusted" and should not contribute their generated summary to briefing content.

---

## Section 1: Invalid Published Briefing Detection

### Query 1.1: Briefings with Confidence Score < 0.5

**Purpose:** Find published briefings that fell back to low-confidence parsing due to JSON parsing failure.

**Read-only query:**

```javascript
db.daily_briefings.find({
  "published": true,
  "metadata.confidence_score": { "$lt": 0.5 }
})
.sort({ "generated_at": -1 })
.limit(10)
```

**Expected result:**
- **Good:** Zero results (no low-confidence briefings published)
- **Investigate:** Any results. These indicate the fallback parser captured non-JSON LLM output as narrative content.
- **Action:** If found, check `content.narrative` for meta-request text or incomplete JSON fragments.

**Cost:** Minimal (index on `published` and `metadata.confidence_score`)

---

### Query 1.2: Briefings with Empty key_insights

**Purpose:** Find published briefings with no key insights extracted.

**Read-only query:**

```javascript
db.daily_briefings.find({
  "published": true,
  "content.key_insights": { "$size": 0 }
})
.sort({ "generated_at": -1 })
.limit(10)
```

**Expected result:**
- **Good:** Zero results (all published briefings have at least one key insight)
- **Investigate:** Any results. These indicate incomplete briefing generation.
- **Action:** Check if this coincides with low confidence_score (Query 1.1).

**Cost:** Moderate ($size operator)

---

### Query 1.3: Briefings with Empty Narrative

**Purpose:** Find published briefings where the narrative content is missing or empty.

**Read-only query:**

```javascript
db.daily_briefings.find({
  "published": true,
  $or: [
    { "content.narrative": { "$exists": false } },
    { "content.narrative": "" },
    { "content.narrative": { "$regex": "^\\s*$" } }  // only whitespace
  ]
})
.sort({ "generated_at": -1 })
.limit(10)
```

**Expected result:**
- **Good:** Zero results (all published briefings have narrative content)
- **Investigate:** Any results. These are unpublishable briefings that passed validation.
- **Action:** Check `metadata.refinement_iterations` and `metadata.model` to understand generation state.

**Cost:** Moderate (regex scan)

---

### Query 1.4: Briefings Flagged Invalid But Published

**Purpose:** Find briefings marked with `metadata.invalid_output=true` but still published.

**Read-only query:**

```javascript
db.daily_briefings.find({
  "published": true,
  "metadata.invalid_output": true
})
.sort({ "generated_at": -1 })
.limit(10)
```

**Expected result:**
- **Good:** Zero results (invalid briefings are never published)
- **Investigate:** Any results indicate a validation logic bypass.
- **Action:** Check deployment logs to verify BUG-099 containment fix is active.

**Cost:** Minimal (index on `published` and `metadata.invalid_output`)

---

### Query 1.5: Sample Invalid Briefing Content Inspection

**Purpose:** If Query 1.1, 1.2, or 1.3 returns results, inspect the actual narrative for meta-request phrases.

**Read-only query (example):**

```javascript
db.daily_briefings.find({
  "published": true,
  "metadata.confidence_score": { "$lt": 0.5 }
}, {
  "_id": 1,
  "generated_at": 1,
  "metadata.confidence_score": 1,
  "content.narrative": 1
})
.limit(3)
```

**Note:** Once retrieved, inspect the first 500 characters of `content.narrative` for meta-request phrases.

**Expected result:**
- **Good:** Narrative is coherent briefing content.
- **Investigate:** Narrative contains phrases like:
  - "provide narrative titles"
  - "provide summaries"
  - "entity names"
  - "AVAILABLE DATA"
  - Any meta-request text that looks like a prompt fragment
- **Action:** If found, this confirms the fallback parser issue from TASK-095 Section A.6. BUG-099 containment should prevent recurrence.

**Cost:** Minimal

---

## Section 2: Trusted Briefing Narrative Eligibility

### Query 2.1: Count Trusted Narratives for Briefing Synthesis

**Purpose:** Count narratives eligible to contribute their generated summary to briefing synthesis.

**Trusted narrative rule:**
A narrative is trusted if it meets ANY of these conditions:
- `first_seen >= 2026-05-10T00:00:00Z` (created after fresh-start cutoff)
- `last_summary_generated_at >= 2026-05-10T00:00:00Z` (summary refreshed after cutoff)
- `_fresh_start_validated_at >= 2026-05-10T00:00:00Z` (explicitly validated in this sprint)

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.countDocuments({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated"] },  // active states only
  $or: [
    { "first_seen": { "$gte": CUTOFF } },
    { "last_summary_generated_at": { "$gte": CUTOFF } },
    { "_fresh_start_validated_at": { "$gte": CUTOFF } }
  ]
})
```

**Expected result:**
- **Good:** Nonzero count (at least some narratives are trusted)
- **Investigate:** Count is 0. This means no narratives are trusted and briefings may lack substance.
- **Action:** If 0, check if FRESH_START_CUTOFF is set correctly or if narratives table is stale.

**Cost:** Minimal (index on lifecycle_state and date fields)

---

### Query 2.2: List Trusted Narrative Titles for Reference

**Purpose:** Spot-check which narratives are trusted and available for briefing synthesis.

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.find({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated"] },
  $or: [
    { "first_seen": { "$gte": CUTOFF } },
    { "last_summary_generated_at": { "$gte": CUTOFF } },
    { "_fresh_start_validated_at": { "$gte": CUTOFF } }
  ]
}, {
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "first_seen": 1,
  "last_summary_generated_at": 1,
  "_fresh_start_validated_at": 1,
  "article_count": 1
})
.sort({ "lifecycle_state": -1, "last_updated": -1 })
.limit(20)
```

**Expected result:**
- **Good:** List includes major entities (Bitcoin, Ethereum, DeFi, NFTs, etc.) with dates >= 2026-05-10
- **Investigate:** List is empty or missing major trending narratives
- **Action:** Verify that recent narrative creation/refresh is working (check logs, check FRESH_START_CUTOFF date)

**Cost:** Minimal

---

## Section 3: Recent Activity Narrative Count

### Query 3.1: Active Narratives with Recent Article Activity

**Purpose:** Count narratives that have received article updates recently, regardless of summary freshness.

**Purpose note:** The narratives page should show recent article clusters even if their summary is stale/untrusted. This query validates that recent activity is still tracked.

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.countDocuments({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling", "echo"] },
  "last_updated": { "$gte": CUTOFF }
})
```

**Expected result:**
- **Good:** Nonzero count (recent narratives exist with article activity)
- **Investigate:** Count is 0. This means no narratives have been updated since cutoff.
- **Action:** Check if article ingestion is running and narrative merges are working.

**Cost:** Minimal

---

### Query 3.2: List Recent Narratives with Activity Dates

**Purpose:** Spot-check recent narratives to confirm article clustering is active.

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.find({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling", "echo"] },
  "last_updated": { "$gte": CUTOFF }
}, {
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "last_updated": 1,
  "last_summary_generated_at": 1,
  "article_count": 1
})
.sort({ "last_updated": -1 })
.limit(20)
```

**Expected result:**
- **Good:** List includes recent narratives with last_updated dates >= 2026-05-10
- **Investigate:** Narratives with last_updated >= 2026-05-10 but last_summary_generated_at missing or much older
- **Action:** These are candidates for article-cluster display mode (Query 4.1)

**Cost:** Minimal

---

## Section 4: Article-Cluster Display Candidate Count

### Query 4.1: Untrusted but Recent Narratives

**Purpose:** Count narratives that have recent article activity but untrusted/stale summaries.

**These narratives should use `display_mode="article_cluster"` instead of showing generated summary.**

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.countDocuments({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling", "echo"] },
  "last_updated": { "$gte": CUTOFF },
  $nor: [
    { "first_seen": { "$gte": CUTOFF } },
    { "last_summary_generated_at": { "$gte": CUTOFF } },
    { "_fresh_start_validated_at": { "$gte": CUTOFF } }
  ]
})
```

**Expected result:**
- **Good:** Nonzero count (some narratives with recent activity but stale summaries exist)
- **Can be zero:** If all recent narratives are also trusted (all have summary >= CUTOFF)
- **Investigate:** Count is unusually high (> 50% of recent narratives). This suggests narrative refresh is not keeping up.
- **Action:** Check `needs_summary_update` count (Query 6.1) and narrative_refresh task logs.

**Cost:** Minimal

---

### Query 4.2: List Untrusted but Recent Narratives

**Purpose:** Identify specific narratives that need article-cluster display fallback.

**Read-only query:**

```javascript
const CUTOFF = new Date("2026-05-10T00:00:00Z");

db.narratives.find({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling", "echo"] },
  "last_updated": { "$gte": CUTOFF },
  $nor: [
    { "first_seen": { "$gte": CUTOFF } },
    { "last_summary_generated_at": { "$gte": CUTOFF } },
    { "_fresh_start_validated_at": { "$gte": CUTOFF } }
  ]
}, {
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "first_seen": 1,
  "last_summary_generated_at": 1,
  "last_updated": 1,
  "article_count": 1,
  "needs_summary_update": 1
})
.sort({ "last_updated": -1 })
.limit(30)
```

**Expected result:**
- **Good:** List shows narratives with recent activity (last_updated >= 2026-05-10) but stale summaries (last_summary_generated_at << 2026-05-10)
- **Example row:**
  ```
  title: "Bitcoin Spot ETF Outflows"
  last_updated: 2026-05-10T14:23:00Z
  last_summary_generated_at: 2026-04-05T09:15:00Z
  article_count: 8
  ```
- **Investigate:** Narratives in this list with `needs_summary_update=false`. These should be flagged for eventual refresh.
- **Action:** These are candidates for article-cluster display on narratives page.

**Cost:** Minimal

---

## Section 5: Legacy Stale Inventory Count

### Query 5.1: Active Narratives Missing last_summary_generated_at

**Purpose:** Count legacy narratives that lack a timestamp for when their summary was generated.

**These narratives cannot be evaluated for staleness and should be treated as untrusted for briefing synthesis.**

**Read-only query:**

```javascript
db.narratives.countDocuments({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling"] },
  "last_summary_generated_at": { "$exists": false }
})
```

**Expected result:**
- **Good:** Count is 0 (all narratives have summary timestamps)
- **Can be nonzero:** Legacy narratives from before timestamp field was added
- **Investigate:** Count > 100. This suggests legacy narratives are still numerous.
- **Action:** If nonzero, these are candidates for the Stage 3 narrative backfill (documented in TASK-095 Addendum). Do not include these in briefing synthesis.

**Cost:** Minimal

---

### Query 5.2: List Legacy Narratives Missing Timestamp

**Purpose:** Identify specific legacy narratives and their current state.

**Read-only query:**

```javascript
db.narratives.find({
  "lifecycle_state": { "$in": ["hot", "emerging", "rising", "reactivated", "cooling"] },
  "last_summary_generated_at": { "$exists": false }
}, {
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "first_seen": 1,
  "last_updated": 1,
  "article_count": 1,
  "needs_summary_update": 1
})
.sort({ "lifecycle_state": -1, "last_updated": -1 })
.limit(30)
```

**Expected result:**
- **Good:** Count is 0
- **Can be nonzero:** Shows legacy narratives with their current activity and refresh flag state
- **Example row:**
  ```
  title: "Ethereum Staking"
  lifecycle_state: "hot"
  first_seen: 2026-02-15T00:00:00Z
  last_updated: 2026-05-09T12:30:00Z
  article_count: 42
  needs_summary_update: false
  last_summary_generated_at: <missing>
  ```
- **Action:** Narratives in this list should NOT be used for briefing synthesis. They should use article-cluster display.

**Cost:** Minimal

---

## Section 6: Narrative Refresh Backlog Count

### Query 6.1: Narratives Flagged for Summary Refresh

**Purpose:** Count narratives queued for the narrative_refresh task.

**Read-only query:**

```javascript
db.narratives.countDocuments({
  "needs_summary_update": true
})
```

**Expected result:**
- **Good:** Count is small (< 20), indicating refresh task is keeping up with staleness
- **Investigate:** Count > 50, indicating backlog is building
- **Action:** Check narrative_refresh task logs and LLM cost (Query 7.1). If cost is high, staleness checks may be triggering too aggressively.

**Cost:** Minimal (index on needs_summary_update)

---

### Query 6.2: List Flagged Narratives with Details

**Purpose:** Identify which narratives are queued for refresh and their state.

**Read-only query:**

```javascript
db.narratives.find({
  "needs_summary_update": true
})
.project({
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "last_updated": 1,
  "last_summary_generated_at": 1,
  "article_count": 1
})
.sort({ "last_updated": -1 })
.limit(30)
```

**Expected result:**
- **Good:** List shows narratives with recent activity and clear reasons for refresh flag (e.g., new articles, lifecycle change)
- **Example row:**
  ```
  title: "SEC Regulatory Announcements"
  lifecycle_state: "emerging"
  article_count: 15
  (article count increased, triggering refresh flag)
  ```
- **Investigate:** Narratives with no obvious reason for flag (no recent articles, no lifecycle change). These may be flagged by the age-gap check.
- **Action:** Monitor that refresh task is processing these. Check Query 7.1 for narrative_generate operation costs.

**Cost:** Minimal

---

## Section 7: LLM Cost in Last 24 Hours by Operation

### Query 7.1: Total Cost by Operation (Last 24 Hours)

**Purpose:** Track LLM spending and identify cost spikes by operation.

**Read-only query:**

```javascript
const YESTERDAY = new Date(new Date().getTime() - 24 * 60 * 60 * 1000);

db.llm_traces.aggregate([
  {
    "$match": {
      "timestamp": { "$gte": YESTERDAY }
    }
  },
  {
    "$group": {
      "_id": "$operation",
      "count": { "$sum": 1 },
      "total_cost": { "$sum": "$cost" },
      "avg_cost": { "$avg": "$cost" },
      "max_cost": { "$max": "$cost" }
    }
  },
  {
    "$sort": { "total_cost": -1 }
  }
])
```

**Expected result:**
- **Good:** Costs are low and distributed. Example:
  ```
  { operation: "briefing_generate", count: 2, total_cost: $0.23, avg_cost: $0.115 }
  { operation: "narrative_generate", count: 0, total_cost: $0, avg_cost: 0 }
  { operation: "entity_extract", count: 8, total_cost: $0.04, avg_cost: $0.005 }
  Total: ~$0.27 for the day
  ```
- **Investigate:** Any operation with total_cost > $1.00 or sudden spike
- **Action:** If `narrative_generate` cost is high, check Query 6.1 refresh backlog size and narrative_refresh task logs.

**Cost:** Moderate (aggregation pipeline on llm_traces)

---

### Query 7.2: Cost Over Time (Last 7 Days, Hourly Breakdown)

**Purpose:** Detect cost trends and identify when spikes occurred.

**Read-only query:**

```javascript
const WEEK_AGO = new Date(new Date().getTime() - 7 * 24 * 60 * 60 * 1000);

db.llm_traces.aggregate([
  {
    "$match": {
      "timestamp": { "$gte": WEEK_AGO }
    }
  },
  {
    "$group": {
      "_id": {
        "date": {
          "$dateToString": {
            "format": "%Y-%m-%d %H:00",
            "date": "$timestamp"
          }
        },
        "operation": "$operation"
      },
      "hourly_cost": { "$sum": "$cost" },
      "count": { "$sum": 1 }
    }
  },
  {
    "$sort": { "_id.date": -1, "hourly_cost": -1 }
  }
])
```

**Expected result:**
- **Good:** Costs are consistent hour-to-hour, with predictable spikes around briefing generation times (8 AM, 8 PM EST)
- **Example result:**
  ```
  { date: "2026-05-10 08:00", operation: "briefing_generate", hourly_cost: $0.15, count: 2 }
  { date: "2026-05-10 08:00", operation: "narrative_generate", hourly_cost: $0.00, count: 0 }
  { date: "2026-05-10 07:00", operation: "entity_extract", hourly_cost: $0.02, count: 4 }
  ```
- **Investigate:** Unexpected spikes (e.g., $1.00+ in a single hour, or narrative_generate outside of scheduled 7:30 AM/PM times)
- **Action:** If spike detected, check deployment logs and task execution logs.

**Cost:** Moderate

---

### Query 7.3: Narrative Generate Operation Cost Detail (Last 24 Hours)

**Purpose:** Drill down into narrative generation costs to confirm refresh task is within budget.

**Read-only query:**

```javascript
const YESTERDAY = new Date(new Date().getTime() - 24 * 60 * 60 * 1000);

db.llm_traces.find({
  "operation": "narrative_generate",
  "timestamp": { "$gte": YESTERDAY }
})
.project({
  "_id": 1,
  "timestamp": 1,
  "cost": 1,
  "input_tokens": 1,
  "output_tokens": 1,
  "model": 1
})
.sort({ "timestamp": -1 })
.limit(50)
```

**Expected result:**
- **Good:** Zero or very few results (no narrative refresh happened, or minimal refresh)
- **Can be nonzero:** Narrative refresh task ran as scheduled (7:30 AM or 7:30 PM EST)
- **Example result:**
  ```
  { timestamp: 2026-05-10T07:30:00Z, operation: "narrative_generate", cost: $0.032, model: "claude-haiku", input_tokens: 3400, output_tokens: 680 }
  ```
- **Investigate:** More than 20 traces in 24 hours (indicates more than 2 runs, or multiple narratives per run)
- **Action:** Cross-check with Query 6.1 refresh backlog size. If both are high, monitor for budget exhaustion.

**Cost:** Minimal

---

## Section 8: Public-Copy Forbidden Word Scan

### Query 8.1: Narratives with Public Display Fields

**Purpose:** Verify that public-facing narrative display does not expose internal system state.

**Note:** If the backend computes `display_title`, `display_summary`, or `display_mode` at API time rather than storing them in MongoDB, skip this query and move to Section 8.2 (API manual check).

**Read-only query (if display fields are stored):**

```javascript
db.narratives.find({
  $or: [
    { "display_title": { "$regex": "stale|missing|untrusted|needs refresh|summary status", "$options": "i" } },
    { "display_summary": { "$regex": "stale|missing|untrusted|needs refresh|summary status", "$options": "i" } }
  ]
})
.project({
  "_id": 1,
  "title": 1,
  "display_title": 1,
  "display_summary": { "$substr": ["$display_summary", 0, 200] }
})
.limit(10)
```

**Expected result:**
- **Good:** Zero results (no internal state words in public copy)
- **Investigate:** Any results. These indicate public-facing fields contain internal terminology.
- **Action:** Verify API response (Query 8.2) does not expose these terms. If stored, may require data remediation.

**Cost:** Moderate (regex scan)

---

### Query 8.2: API Manual Check (Required if Display Fields Not Stored)

**Purpose:** Verify public API does not expose internal system state.

**This is a manual verification step, not a Mongo query.**

**What to check:**

1. Hit the public narratives endpoint:
   ```
   GET /api/v1/narratives
   ```

2. For each narrative in the response, inspect:
   - `display_title` (if present)
   - `display_summary` (if present)
   - `display_mode` (if present)
   - `recent_articles` (if present, used for article-cluster fallback)

3. Verify that public copy does NOT contain:
   - "stale"
   - "missing"
   - "untrusted"
   - "needs refresh"
   - "summary status"
   - "invalid_output"
   - "confidence_score"
   - Any internal system terms

4. Expected public copy examples (GOOD):
   ```json
   {
     "title": "Bitcoin Spot ETF Outflows",
     "display_title": "Bitcoin Spot ETF Outflows",
     "display_mode": "summary",
     "display_summary": "Recent articles discuss outflows from new spot ETFs following regulatory clarity on custody requirements..."
   }
   ```

   OR for untrusted narratives (GOOD fallback):
   ```json
   {
     "title": "Ethereum Staking",
     "display_title": "Ethereum Staking",
     "display_mode": "article_cluster",
     "display_summary": null,
     "recent_articles": [
       { "title": "Ethereum Staking Yields Hit 3-Year High", "source": "CoinDesk" },
       { "title": "Validators Prepare for Shanghai Upgrade", "source": "The Block" }
     ],
     "recent_article_count": 8
   }
   ```

5. Expected behavior (GOOD):
   - Trusted narratives show `display_mode="summary"` with clean, coherent summaries
   - Untrusted narratives show `display_mode="article_cluster"` with deterministic fallback derived from articles
   - No internal system state exposed

6. Unexpected behavior (INVESTIGATE):
   - Public copy contains any forbidden words
   - Untrusted narratives still show generated `display_summary` instead of falling back to article cluster
   - `display_mode` is missing or always "summary"

**Cost:** Manual, no database cost

---

## Section 9: Post-Deploy Checks

### Checklist: Immediate Post-Deployment Validation

Run these checks within 1 hour of deploying Sprint 019 code to production:

- [ ] **Invalid Briefing Check**
  - Query 1.1: No briefings with confidence_score < 0.5
  - Query 1.2: No briefings with empty key_insights
  - Query 1.3: No briefings with empty narrative
  - Query 1.4: No briefings with metadata.invalid_output=true but published=true
  - ✅ Expected: All queries return 0 results

- [ ] **Trusted Narrative Availability**
  - Query 2.1: Trusted narrative count is nonzero
  - Query 2.2: List includes major entities (Bitcoin, Ethereum, major altcoins)
  - ✅ Expected: At least 5-10 trusted narratives available

- [ ] **Recent Activity Preserved**
  - Query 3.1: Recent activity count is nonzero
  - Query 3.2: Narratives page data is available
  - ✅ Expected: Recent narratives list exists and is current (last_updated >= 2026-05-10)

- [ ] **Article-Cluster Fallback Candidates Exist**
  - Query 4.1: Untrusted but recent narrative count is nonzero or zero (either is acceptable)
  - Query 4.2: If nonzero, list shows narratives with recent activity but stale summaries
  - ✅ Expected: System can gracefully fall back to article clusters for untrusted narratives

- [ ] **Public API Includes Display Fields**
  - Query 8.2: Hit /api/v1/narratives endpoint and inspect response
  - ✅ Expected: Responses include `display_mode`, `display_title`, and recent article fallback data
  - ✅ Expected: Trusted narratives show `display_mode="summary"` with generated title/summary
  - ✅ Expected: Untrusted narratives show `display_mode="article_cluster"` with recent articles and no generated summary

- [ ] **Public Copy Does Not Expose Internal State**
  - Query 8.2: Verify no forbidden words in display fields
  - ✅ Expected: Public copy is clean and user-facing

- [ ] **No Unexpected Narrative Refresh Occurred**
  - Query 6.1: Refresh backlog count is reasonable (< 30)
  - Query 6.2: If flagged narratives exist, they have clear reasons (new articles, lifecycle change)
  - ✅ Expected: No surprise refresh job ran during deployment

- [ ] **LLM Cost Did Not Spike**
  - Query 7.1: Last 24 hours cost is in normal range (~$0.20-0.50)
  - Query 7.2: No unexpected hourly spikes
  - Query 7.3: narrative_generate costs are low (< 5 calls, < $0.20 total)
  - ✅ Expected: Costs are consistent with baseline

- [ ] **Legacy Narratives Inventory (For Information)**
  - Query 5.1: Count legacy narratives missing last_summary_generated_at
  - ✅ Expected: Any nonzero count is documented for future Sprint 019 Addendum discussion (Stage 3 narrative repair is deferred)

---

## Section 10: Rollback Checks

### If Code Is Reverted (Rollback Scenario)

**Purpose:** Verify that reverting Sprint 019 code does not cause data corruption and restores old behavior.

**Execute these checks after rolling back to pre-Sprint-019 code:**

- [ ] **Old Briefing Generation Behavior Is Restored**
  - Query 1.1, 1.2, 1.3: Run invalid briefing queries
  - ✅ Expected: Results may exist (old code did not validate)
  - ✅ Expected: No new invalid briefings are generated after rollback

- [ ] **No Data Mutation Occurred**
  - Narrative documents: No fields were deleted, no timestamps were overwritten
  - Briefing documents: No published briefings were unpublished
  - LLM trace documents: No traces were deleted or modified
  - ✅ Expected: All data remains as-is (queries are read-only, no writes happened)

- [ ] **Refresh Task Is Not Stuck**
  - Query 6.1: Refresh backlog count is reasonable
  - ✅ Expected: Backlog size is unchanged from pre-rollback

- [ ] **API Behavior**
  - If display fields were added, they are now absent or null in API responses
  - ✅ Expected: API responses revert to pre-Sprint-019 format

### If BUG-099 Data Already Exists (Invalid Briefing Pre-Rollback)

**Purpose:** Verify that rolling back does not cause old invalid briefings to be re-surfaced or new ones to be published.

**Check:**

- [ ] **No Rollback-Related Re-Publishing**
  - Query 1.1, 1.2, 1.3: Run invalid briefing queries after rollback
  - ✅ Expected: Invalid briefings may exist in database from pre-rollback (published=true), but no NEW invalid briefings generated after rollback
  - ✅ Expected: Rollback does not mutate or unpublish existing briefings

- [ ] **Public API Does Not Surface Invalid Briefings**
  - Manual check: Hit /api/v1/briefings/latest endpoint
  - ✅ Expected: Latest briefing returned to users is valid (coherent narrative, not meta-request text)
  - ✅ Expected: If latest is invalid, endpoint either returns second-latest, or API filtering removes it (behavior depends on implementation)

---

## Section 11: Local Verification Commands

### Git Inspection Commands

**Verify TASK-096 verification document exists:**

```bash
# For TASK-096 alone, show files changed
git diff --name-only

# Expected output: Only the verification markdown file
# docs/sprints/sprint-019-fresh-start-narrative-trust/verification/sprint-019-verification-queries.md
```

**Verify full Sprint 019 branch (context):**

```bash
# When reviewing the full Sprint 019 feature branch, expected changes include:
git diff --name-only main..feature-branch

# Expected areas:
# src/                   (BUG-099 briefing validation, FEATURE-060 trusted narrative eligibility, BUG-100 refinement context)
# context-owl-ui/        (FEATURE-062 display_mode support, FEATURE-061 narrative API fields)
# docs/                  (TASK-096 verification queries, sprint docs)
```

```bash
# Show stat of changes
git diff --stat main..HEAD

# Expected: Show new files (display_mode fields, trusted narrative filters, article-cluster logic)
```

```bash
# Verify no secrets were committed
git diff main..HEAD | grep -E "API_KEY|TOKEN|SECRET|password|mongodb://"

# Expected: No output (no secrets in diff)
```

---

### Code Inspection Commands

**Verify Display Fields Are Present:**

```bash
# Search for display_mode field in code
grep -r "display_mode" src/ --include="*.py"

# Expected: Occurrences in:
# - api/v1/endpoints/narratives.py or similar (narrative API serialization)
# - services/narrative_service.py (display mode computation)
# 
# Note: display_mode is a narrative API concern, not briefing_agent behavior.
# Briefing agent should use trusted narrative filters, not display_mode fields.
```

```bash
# Search for trusted narrative filter
grep -r "last_summary_generated_at\|_fresh_start_validated_at\|FRESH_START" src/ --include="*.py"

# Expected: Occurrences in briefing_agent.py or narrative_service.py (trusted narrative eligibility logic)
```

```bash
# Search for article-cluster fallback logic
grep -r "article_cluster\|recent_articles\|deterministic" src/ --include="*.py"

# Expected: Occurrences in narrative routes/endpoints (fallback display generation)
```

```bash
# Verify no forbidden words in public API responses
grep -r "display_summary\|display_title" src/ --include="*.py" | grep -v "test" | head -20

# Expected: API routes that populate display fields with clean content (no internal terminology)
```

---

### Build Verification (Optional, Frontend-Related)

**If frontend changes were made for display_mode support:**

```bash
# Build frontend (if applicable)
cd context-owl-ui && npm run build

# Expected: Build succeeds with no TypeScript errors
# Expected: No new warnings related to undefined props (display_mode, display_summary, recent_articles)
```

---

### Test Verification (Information Only)

**Do NOT run tests from this verification task.** Tests are run as part of the normal CI/CD pipeline.

For reference, Sprint 019 tests should be in:
- `tests/services/test_briefing_agent.py` (briefing validation, display_mode logic)
- `tests/api/test_narratives*.py` (narrative eligibility, article-cluster fallback)
- `tests/db/test_narrative_refresh.py` (refresh task behavior unchanged)

To run them (if needed outside of CI):
```bash
pytest tests/services/test_briefing_agent.py -v
pytest tests/api/test_narratives*.py -v
```

---

## Section 12: Expected Results Summary

### Good Health Indicators (Post-Deploy)

| Check | Query | Good Result |
|-------|-------|------------|
| Invalid briefings | 1.1, 1.2, 1.3, 1.4 | All return 0 |
| Trusted narratives | 2.1, 2.2 | Count > 0, major entities present |
| Recent activity | 3.1, 3.2 | Count > 0, activity dated >= 2026-05-10 |
| Article-cluster candidates | 4.1, 4.2 | Count >= 0, not concerning if 0 |
| Legacy stale inventory | 5.1, 5.2 | Any count acceptable (deferred stage) |
| Refresh backlog | 6.1, 6.2 | Count < 30 |
| LLM cost | 7.1, 7.2, 7.3 | No spikes, narrative_generate < $0.20 |
| Public copy | 8.1, 8.2 | No forbidden words |

### Investigate-Required Indicators

| Check | Query | Result | Action |
|-------|-------|--------|--------|
| Low-confidence briefing | 1.1 | Any result | Check content for meta-request text, verify BUG-099 is deployed |
| Empty briefing fields | 1.2, 1.3 | Any result | Investigate generation logs |
| No trusted narratives | 2.1 | Count = 0 | Verify FRESH_START_CUTOFF date, check narrative creation |
| No recent activity | 3.1 | Count = 0 | Verify article ingestion and narrative merge jobs |
| High refresh backlog | 6.1 | Count > 50 | Check staleness logic, verify budget not exhausted |
| Narrative_generate cost spike | 7.3 | > $0.50 | Check scheduled task logs, verify no manual refresh triggered |
| Forbidden words in public copy | 8.2 | Any found | Verify API response formatting, may need data fix |

---

## Section 13: Important Notes

### On FRESH_START_CUTOFF Date

The cutoff date `2026-05-10T00:00:00Z` marks the beginning of Sprint 019's fresh-start narrative trust model. All narratives created or refreshed on or after this date are considered "trusted" for briefing synthesis. This date is fixed for the lifecycle of the sprint and should not be changed without explicit product decision.

If you need to verify a different date range, substitute the ISO 8601 timestamp in the queries above.

### On Query Performance

All queries are designed to be read-only and safe to run in production. However:
- Regex queries (Query 1.3, 8.1) may be slow on large datasets; limit results
- Aggregation queries (Query 7.1, 7.2) may use significant memory; consider time-bounding
- Date range queries assume indexes on timestamp, last_updated, first_seen, and last_summary_generated_at

If queries are slow, check index coverage:
```javascript
db.narratives.getIndexes()
db.daily_briefings.getIndexes()
db.llm_traces.getIndexes()
```

### On Data Retention

- `llm_traces` are typically rotated after 90 days (check retention policy)
- `daily_briefings` are kept indefinitely
- `narratives` are kept indefinitely (never deleted, only dormancy-marked)

Queries in Section 7 that reference "last 24 hours" will work reliably unless llm_traces rotation is < 24 hours (very unlikely).

### On Manual Remediation

If any query results indicate a problem, do NOT attempt to fix it with a Mongo mutation or ad hoc script.

Approved remediation requires:
1. Project lead approval
2. A dedicated ticket (e.g., BUG-XXX or CHORE-XXX)
3. Code implementation (not ad hoc scripts)
4. Tests verifying the fix
5. Staged deployment to staging first

Examples of remediation (NOT PROVIDED HERE):
- Flagging stale narratives for refresh
- Overwriting `last_summary_generated_at` on legacy narratives
- Marking old briefings as invalid
- Deleting corrupted documents

None of these are included in this verification document by design.

---

## Conclusion

This verification guide provides read-only queries and checks to confirm Sprint 019's fresh-start narrative trust model is working correctly post-deployment. All queries are designed to be safe to run in production without risk of data mutation or cost explosion.

If any query results diverge from expected outcomes, review the investigation (linked as action items above) and consult project team before running any mutation or remediation.

**Last updated:** 2026-05-10

---

*End of Sprint 019 Verification Queries Document*
