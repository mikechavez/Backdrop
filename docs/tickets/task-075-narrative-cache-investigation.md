---
ticket_id: TASK-075
title: Narrative Cache Investigation - Root Cause Analysis & Fix Proposal
priority: critical
severity: critical
status: OPEN
date_created: 2026-04-27
branch: feature/narrative-cache-investigation
effort_estimate: 4-6 hours
---

# TASK-075: Narrative Cache Investigation - Root Cause Analysis & Fix Proposal

## Problem Statement

The `narrative_generate` operation has **0% cache hit rate** despite being the **second-largest cost driver** in Backdrop ($6.64/month over 2,543 calls). This indicates either:

1. **Cache is broken for narrative_generate** — the caching logic isn't working despite being configured
2. **Cache is blocked by architecture** — narrative_generate's input structure prevents effective caching
3. **Cache is disabled intentionally** — but not documented why

This costs ~$0.22/day (highest per-operation cost). Comparison: `entity_extraction` achieves 99.6% cache hit rate on similar volume.

**Business impact:** If caching could be fixed, narrative_generate cost could drop 5-10x (~$0.04/day instead of $0.22/day), potentially eliminating the need for a Gemini Flash swap entirely.

---

## Task

### Phase 1: Root Cause Analysis

**Objective:** Determine why narrative_generate has 0% cache hit rate

**Investigation steps:**

1. **Verify cache is enabled for narrative_generate:**
   - Check gateway.py lines 427–431 (CACHEABLE_OPERATIONS list)
   - Confirm "narrative_generate" is listed
   - If not listed, that's the bug — add to list and verify

2. **Understand narrative_generate callers:**
   - Find all locations that call narrative_generate
   - File: `src/crypto_news_aggregator/services/narrative_themes.py` lines 980, 1317
   - Functions: `generate_narrative_from_theme()`, `generate_narrative_from_cluster()`
   - Trace how they build the `messages` parameter
   
3. **Inspect input hashing:**
   - Gateway.py lines 440–443 builds input hash from messages using SHA-1
   - Verify the exact structure of `messages` being passed
   - Example: Is each call passing identical messages? Or are they slightly different (e.g., timestamps, IDs)?
   
4. **Check MongoDB llm_cache collection:**
   - Query recent calls for narrative_generate:
   ```bash
   db.llm_cache.find({operation: "narrative_generate"}).limit(5)
   # Should show cached_response, cached_at, cached_count fields
   ```
   - If collection is empty or has very few records, caching isn't working
   - If collection has many records but cached_count = 1 everywhere, cache isn't being hit
   
5. **Analyze call patterns:**
   - Check MongoDB llm_traces for narrative_generate calls
   - Look for: do identical inputs appear multiple times?
   - Or does every call have slightly different input?
   - Run aggregation:
   ```javascript
   db.llm_traces.aggregate([
     {$match: {operation: "narrative_generate"}},
     {$group: {_id: "$input_hash", count: {$sum: 1}}},
     {$sort: {count: -1}},
     {$limit: 10}
   ])
   # If most groups have count=1, inputs are unique
   # If some groups have count>5, those could have been cached
   ```

6. **Identify the root cause:**
   - **Hypothesis A:** narrative_generate inputs are always unique (different articles, timestamps)
     - → Cache won't help unless we normalize input (strip timestamps, etc.)
   - **Hypothesis B:** Cache is built but not hit due to SHA-1 mismatch
     - → Check if messages are serialized identically each time
   - **Hypothesis C:** narrative_generate was explicitly excluded (e.g., SKIP_CACHE_OPERATIONS)
     - → Check gateway.py lines 433–437

### Phase 2: Solution Design

**Objective:** Propose architecture to enable caching for narrative_generate

Based on root cause, produce one of:

#### If root cause is "unique inputs" (Hypothesis A):

Design a **normalized input caching** strategy:

1. **Identify what makes inputs unique:**
   - List fields in the `messages` parameter for narrative_generate
   - Categorize: static (prompt template) vs dynamic (article content)
   
2. **Propose normalization rules:**
   - Example: "Strip timestamps from article list, keep only {title, entities, sentiment}"
   - This reduces cache key collision while keeping semantically identical inputs cacheable
   
3. **Calculate expected cache hit improvement:**
   - Example: "If we normalize to article titles + entities, ~40% of calls have identical input"
   - → Estimated savings: 40% × $6.64 = $2.66/month
   
4. **Document tradeoff:**
   - Normalized caching may miss some hits (if small input variations matter)
   - But gains significantly more hits than current 0%

#### If root cause is "cache is excluded" (Hypothesis C):

Design **re-enable strategy:**

1. **Determine why it was excluded:**
   - Check commit history or comments for narrative_generate exclusion
   - Was it experimental? Performance issue? Quality concern?
   
2. **Propose re-enabling with monitoring:**
   - Add to CACHEABLE_OPERATIONS
   - Monitor: do cached responses match quality of fresh responses?
   - Set up A/B test: 10% cached vs 90% fresh, compare output quality

#### If root cause is "hashing mismatch" (Hypothesis B):

Design **deterministic serialization:**

1. **Verify JSON serialization:**
   - `messages` parameter is serialized with `json.dumps(messages, sort_keys=True)`
   - Check if this is truly deterministic across calls
   - Python dict order should be stable (3.7+), but verify

2. **Propose fix:**
   - Add explicit field ordering to narrative_generate callers
   - Or add pre-serialization normalization step

---

## Verification

### Investigation Verification (Phase 1)

- [ ] Confirmed narrative_generate is in CACHEABLE_OPERATIONS list (or not, and documented why)
- [ ] Located all callers of narrative_generate (narrative_themes.py lines 980, 1317)
- [ ] Queried llm_cache collection: confirmed presence/absence of cached entries
- [ ] Ran aggregation on llm_traces: identified cache-miss root cause
- [ ] Root cause documented: is it unique inputs, excluded operation, or hashing issue?

### Solution Design Verification (Phase 2)

- [ ] Root cause tied to specific code location
- [ ] Proposed solution includes:
  - **What changes:** specific files, functions, code blocks
  - **Why it works:** how it addresses the root cause
  - **Cost/benefit:** estimated cache hit % improvement + cost savings
  - **Tradeoffs:** what quality/performance implications?
- [ ] Solution documented in decision record (docs/decisions/NARRATIVE_CACHE_FIX.md)

---

## Acceptance Criteria

- [ ] Root cause identified and documented (0% cache hit rate caused by: ___)
- [ ] Root cause tied to specific code location(s)
- [ ] MongoDB queries run and results analyzed:
  - [ ] llm_cache collection state documented
  - [ ] llm_traces input patterns analyzed
  - [ ] Call distribution aggregated
- [ ] Solution design document produced with:
  - [ ] Proposed architecture (normalized inputs, re-enable, or serialization fix)
  - [ ] Code changes required (file paths, line numbers, before/after)
  - [ ] Expected cache hit improvement (estimated %)
  - [ ] Cost savings projection (if cache fixed)
  - [ ] Tradeoffs and risks
- [ ] Decision record written: docs/decisions/NARRATIVE_CACHE_FIX.md
- [ ] Recommendation: proceed to implementation or defer (decision needed)

---

## Impact

**On Sprint 16:**
- Determines whether narrative_generate needs model swap evaluation
- If cache is fixable, Gemini Flash swap may be unnecessary (5-10x cost reduction from cache alone)
- If cache is unfixable, confirms Flash swap is justified cost optimization

**On cost projection:**
- If cache achieved 50% hit rate: narrative_generate cost → $3.32/month (vs $6.64 today)
- Impact on total Backdrop spend: $11.03 → ~$8 MTD (27% reduction)
- Affects Sprint 16 decision: is $0.22/day cost high enough to warrant Flash evaluation?

**On TASK-071 threshold recalibration:**
- If cache is fixed, baseline cost changes
- Need to re-run cost aggregation before recalibrating thresholds

---

## Related Tickets

- BUG-090 (Model Override) — must be done first (unblocks valid model evaluation)
- FEATURE-053 (Flash Evaluations) — depends on this if narrative_generate gets evaluated
- TASK-071 (Threshold Recalibration) — depends on cache findings for new baseline
- Sprint 16 Model Selection Rubric — needs narrative_generate tier classification based on cache outcome

---

## Implementation Notes

### File Locations to Inspect

1. **Callers of narrative_generate:**
   - `src/crypto_news_aggregator/services/narrative_themes.py:980` — `generate_narrative_from_theme()`
   - `src/crypto_news_aggregator/services/narrative_themes.py:1317` — `generate_narrative_from_cluster()`
   - Both call `gateway.call()` with operation="cluster_narrative_gen" or "actor_tension_extract"
   - Check what's in the `messages` parameter

2. **Cache configuration:**
   - `src/crypto_news_aggregator/llm/gateway.py:427–431` — CACHEABLE_OPERATIONS list
   - `src/crypto_news_aggregator/llm/gateway.py:440–443` — input hash generation
   - `src/crypto_news_aggregator/llm/gateway.py:82–115` — _get_from_cache() and _save_to_cache()

3. **Cache data:**
   - MongoDB collection: `llm_cache` (documents with operation, input_hash, cached_response, cached_count)
   - MongoDB collection: `llm_traces` (documents with operation, timestamp, model, input_tokens, output_tokens, cost)

4. **Cost dashboard:**
   - Check backdropxyz.vercel.app/cost-monitor for narrative_generate cost breakdown
   - Should show: 2,543 calls, 0% cache hit rate, $6.64 cost

### Analysis Queries

**Check llm_cache for narrative operations:**
```javascript
db.llm_cache.find({
  operation: {$in: ["narrative_generate", "cluster_narrative_gen", "actor_tension_extract"]}
}).count()
// If 0 or very low: cache isn't being populated
```

**Check llm_traces for duplicate inputs:**
```javascript
db.llm_traces.aggregate([
  {$match: {operation: "cluster_narrative_gen"}},
  {$group: {
    _id: "$input_hash",  // Group by input hash
    count: {$sum: 1},
    first_call: {$min: "$timestamp"}
  }},
  {$sort: {count: -1}},
  {$limit: 20}
])
// If most documents have count=1: every call has unique input
// If some have count>5: those inputs were called multiple times (cache opportunity)
```

**Check cost by operation:**
```javascript
db.llm_traces.aggregate([
  {$match: {operation: "cluster_narrative_gen"}},
  {$group: {
    _id: "$operation",
    total_calls: {$sum: 1},
    total_cost: {$sum: "$cost"},
    avg_cost: {$avg: "$cost"}
  }}
])
// Should show: 2,543 calls, ~$6.64 cost, ~$0.0026 per call
```

---

## Decision Gate

After Phase 1 root cause analysis, decision needed:

**Option A:** Root cause is fixable (normalized caching, re-enable, deterministic serialization)
- → Proceed to Phase 2 solution design
- → Estimate implementation effort
- → Decide: implement fix now (extends Sprint 16) or defer to later sprint?

**Option B:** Root cause is unfixable (architectural limitation)
- → Accept 0% cache hit rate for narrative_generate
- → Proceed with Gemini Flash evaluation (cost swap may be necessary)
- → Mark as technical debt (future optimization)

**Option C:** Root cause is "working as intended" (narrative_generate excluded by design)
- → Document why exclusion was intentional
- → Confirm Flash evaluation is necessary given this constraint
- → Move forward with Spring 16 as planned

---

## Completion Summary

*(To be filled in after task completion)*

- **Root cause identified:** [Unique inputs / Cache excluded / Hashing issue]
- **Solution recommended:** [Normalized caching / Re-enable / Serialization fix]
- **Estimated cache hit improvement:** [X%]
- **Cost savings projection:** [$Y/month if implemented]
- **Decision:** [Implement now / Defer / Accept as-is]
- **Impact on Sprint 16:** [Proceed with Flash evals / May eliminate need for Flash evals / No change]