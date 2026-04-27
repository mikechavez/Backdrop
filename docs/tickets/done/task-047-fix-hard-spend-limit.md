---
ticket_id: TASK-047
title: Fix Hard Spend Limit & Enable Full Cost Measurement
priority: CRITICAL
severity: BLOCKS_SPRINT
status: IN_PROGRESS
date_created: 2026-04-09
branch: fix/task-047-hard-limit-cost-visibility
effort_estimate: ~0.5h (config) + 24-48h (measurement period)
---

# TASK-047: Fix Hard Spend Limit & Enable Full Cost Measurement

## Problem Statement

Sprint 13 goal is to "identify the primary cost driver with measured data" via a 48-hour burn-in. However:

1. **Hard spend limit was $0.33** — blocks all narrative enrichment and briefing operations after ~0.4-0.5/day
2. **Briefing tasks never executed** — zero `briefing_generate`, `briefing_critique`, `briefing_refine` operations recorded
3. **Incomplete cost picture** — only measuring cheap Haiku calls (narrative_generate + entity_extraction = $0.48/day)
4. **Missing the real cost driver** — Sonnet-based briefing operations never ran, so their cost impact is invisible
5. **TASK-041B (findings doc) blocked** — cannot write cost attribution report without full 48-hour cycle data

**Current measured costs (Haiku only):**
- `narrative_generate`: 87 calls, $0.262412 (avg $0.003/call)
- `entity_extraction`: 256 calls, $0.221987 (avg $0.000867/call)
- **Total: $0.48/day**

**Unmeasured costs (Sonnet-based, blocked by hard limit):**
- `briefing_generate` — unknown, never executed
- `briefing_critique` — unknown, never executed
- `briefing_refine` — unknown, never executed

---

## Task

### Part 1: Fix Hard Spend Limit (COMPLETED ✅)

**Update Railway FastAPI service environment variables:**

| Variable | Old | New | Reason |
|----------|-----|-----|--------|
| `LLM_DAILY_HARD_LIMIT` | $0.33 | $15.00 | Allow full briefing cycle without blocking; measurement period only |
| `LLM_DAILY_SOFT_LIMIT` | $0.25 | $1.00 | Raise warning threshold to allow real-world usage without false positives |

**Status:** ✅ COMPLETED
- Hard limit: $15.00 ✅
- Soft limit: $1.00 ✅
- FastAPI service redeployed ✅

---

### Part 2: Reset Cost Baseline (READY)

Once hard limit is deployed and container is live, reset MongoDB cost tracking:

```javascript
use crypto_news
db.llm_traces.deleteMany({})
```

**Why:** Clear pre-fix noise so 48-hour burn-in measures only the new cycle with Sonnet operations included.

---

### Part 3: Run Full 48-Hour Measurement Cycle (IN PROGRESS)

**Wait for:**
- ✅ 8 AM EST morning briefing (13:00 UTC) — generates brief + critique + refinement
- ✅ 8 PM EST evening briefing (01:00 UTC next day) — generates brief + critique + refinement
- ✅ Hourly narrative consolidation
- ✅ Every-10-min cache warming
- ✅ Continuous entity extraction from RSS feeds

**Expected operations to appear in traces:**
- `briefing_generate` (Sonnet)
- `briefing_critique` (Sonnet)
- `briefing_refine` (Sonnet)
- `narrative_generate` (Haiku)
- `entity_extraction` (Haiku)

---

### Part 4: Query Cost Breakdown & Write Findings (PENDING)

After 48 hours, run this query:

```javascript
db.llm_traces.aggregate([
  {
    $group: {
      _id: "$operation",
      total_cost: { $sum: "$cost" },
      call_count: { $sum: 1 },
      avg_cost_per_call: { $avg: "$cost" }
    }
  },
  { $sort: { total_cost: -1 } }
])
```

**Document in TASK-041B:**
- Which operation burns the most ($)?
- Which operation has highest call volume?
- Which operation has highest cost-per-call?
- Recommendation for optimization (kill refine loop? downgrade Sonnet? cache narrative generation?)

---

## Verification

After hard limit is live and 48h measurement completes:

### Check 1: Briefing Operations Are Executing

```javascript
db.llm_traces.find({ operation: /briefing/ })
```

**Expected:** Multiple documents with operation names like `briefing_generate`, `briefing_critique`, `briefing_refine`

### Check 2: Cost Breakdown Shows All Operations

```javascript
db.llm_traces.aggregate([
  { $group: { _id: "$operation", count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
])
```

**Expected output includes:**
- ✅ `briefing_critique`
- ✅ `briefing_generate`
- ✅ `briefing_refine`
- ✅ `entity_extraction`
- ✅ `narrative_generate`

### Check 3: Hourly Cost Trend Shows Briefing Spikes

```javascript
db.llm_traces.aggregate([
  {
    $match: {
      timestamp: {
        $gte: new Date(new Date().getTime() - 48 * 60 * 60 * 1000)
      }
    }
  },
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d %H:00",
          date: "$timestamp"
        }
      },
      total_cost: { $sum: "$cost" },
      call_count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

**Expected:** Cost spikes around 8 AM and 8 PM EST when briefings execute.

### Check 4: Sonnet vs Haiku Cost Split

```javascript
db.llm_traces.aggregate([
  {
    $group: {
      _id: "$model",
      total_cost: { $sum: "$cost" },
      call_count: { $sum: 1 }
    }
  },
  { $sort: { total_cost: -1 } }
])
```

**Expected:** Sonnet calls dominate cost, Haiku calls dominate volume.

---

## Acceptance Criteria

- [x] Hard limit updated to $15.00 in Railway
- [x] Soft limit updated to $1.00 in Railway
- [x] FastAPI service redeployed with new config
- [ ] Cost baseline cleared (delete llm_traces after verification it's live)
- [ ] 48-hour measurement period completes
- [ ] `briefing_generate`, `briefing_critique`, `briefing_refine` operations appear in traces
- [ ] Cost breakdown query shows all 5+ operation types
- [ ] Hourly cost trend shows 8 AM and 8 PM spikes
- [ ] TASK-041B findings doc written with top cost driver identified
- [ ] Optimization recommendation delivered (e.g., "narrative_generate is 60% of cost, try caching" or "refine loop is 40%, consider disabling")

---

## Impact

**Unblocks:**
- TASK-041B: Findings doc can now be written with complete data
- Sprint 13 completion: Will deliver data-driven cost optimization recommendations instead of guesses

**Risk mitigation:**
- Hard limit at $15 means worst-case is $15/day, not $50+/day
- Soft limit at $1 provides early warning before hitting hard cap
- Clear measurement window enables rapid iteration: fix → measure → verify

**Business value:**
- First time you'll have a data-driven answer to "$2.50-5/day burn" question
- Can optimize with confidence knowing which operation is the cost sink

---

## Related Tickets

- TASK-044: Lift hard spend limit to $15 for burn-in (partial fix, now complete)
- TASK-041B: Analyze burn-in + write findings doc (blocked until this completes)
- BUG-061: Budget tracking discrepancy (will be resolved by this measurement)
- Session 11: Comprehensive database investigation (revealed the measurement gap)

---

## Session Log

### Session 14 (2026-04-09) — Cost Visibility Diagnosis & Hard Limit Fix

**Problem discovered:**
- Hard limit at $0.33 blocks briefing operations
- Only measuring background Haiku calls ($0.48/day)
- Missing Sonnet-based briefing cost impact (5-10x more expensive)
- Cannot identify cost driver without complete measurement

**Action taken:**
- Updated Railway config: hard limit → $15.00, soft limit → $1.00
- Verified deployment via FastAPI logs showing new limits
- Created mongosh query suite for cost analysis
- Documented measurement workflow for 48h burn-in

**Current state:**
- Config deployed ✅
- Waiting for briefing cycles to execute and populate traces
- Ready to measure at end of 48h window

**Next step:**
- Wait 24-48 hours for full briefing cycle
- Run cost breakdown queries
- Write TASK-041B findings with actual data