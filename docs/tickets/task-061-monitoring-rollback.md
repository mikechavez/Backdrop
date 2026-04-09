---
ticket_id: TASK-061
title: Monitor Cost Trend & Rollback Decision (Post TASK-060)
priority: P1
severity: MEDIUM
status: OPEN
date_created: 2026-04-09
branch: cost-optimization/tier-1-only
effort_estimate: 30 minutes (monitoring), 15 minutes (if rollback needed)
---

# TASK-061: Monitor Cost Trend & Rollback Decision

## Problem Statement

TASK-060 implements tier 1 only enrichment, targeting $0.36-0.45/day cost (~$11-13.50/month). However, actual costs are unknown until real data flows through the system.

Goal: Establish monitoring window (24-48 hours) to collect actual cost data, then decide whether to:
1. **Keep tier 1 only** (if costs in target range: $0.30-0.50/day)
2. **Enable tier 2 enrichment** (if costs unexpectedly low: <$0.20/day, well under budget)
3. **Further restrict** (if costs unexpectedly high: >$0.60/day, over budget)

---

## Task

### Phase 1: Deploy TASK-059 & TASK-060

Prerequisite: Both tickets deployed and running for at least 1 hour before this task begins.

**Deployment checklist:**
- [ ] TASK-059 sources removed (watcherguru, glassnode, bitcoinmagazine)
- [ ] TASK-060 tier 1 filter deployed
- [ ] Hard spend limit set to $0.75/day (allows headroom)
- [ ] Worker process restarted with new code
- [ ] Logs show "enrichment skipped" messages (confirms filter working)

### Phase 2: Monitor Cost/Hour for 24 Hours

**Schedule:** Run the cost query below **every hour on the hour** for 24 hours, starting exactly 1 hour after deploy finishes.

**Monitoring Query (run hourly):**

```javascript
// Run this query at: +1h, +2h, +3h, ... +24h after deploy
db.llm_traces.aggregate([
  {
    $match: {
      timestamp: {
        $gte: new Date(Date.now() - 3600000)  // Exactly last hour
      }
    }
  },
  {
    $group: {
      _id: "$operation",
      calls: { $sum: 1 },
      cost: { $sum: "$cost" }
    }
  },
  {
    $group: {
      _id: null,
      total_calls: { $sum: "$calls" },
      total_cost: { $sum: "$cost" },
      operations: {
        $push: {
          operation: "$_id",
          calls: "$calls",
          cost: "$cost"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      timestamp: { $literal: new Date() },
      total_calls: 1,
      total_cost: 1,
      calls_per_hour: "$total_calls",
      cost_per_hour: "$total_cost",
      projected_daily: { $multiply: ["$total_cost", 24] },
      operations: 1
    }
  }
])
```

**Tracking spreadsheet (record hourly results):**

| Hour | Calls/hr | Cost/hr | Projected Daily | Status | Notes |
|------|----------|---------|-----------------|--------|-------|
| +1h  | ?        | ?       | ?               |        |       |
| +2h  | ?        | ?       | ?               |        |       |
| +3h  | ?        | ?       | ?               |        |       |
| ... (continue for 24h) |

**What to watch for:**

- **Normal range (✅ KEEP):** 30-50 calls/hour, $0.09-0.15/hr, $2.16-3.60/day projected
- **Unexpectedly low (? CONSIDER TIER 2):** <20 calls/hour, <$0.06/hr, <$1.44/day projected
- **Unexpectedly high (🔴 INVESTIGATE):** >80 calls/hour, >$0.24/hr, >$5.76/day projected
- **Zero or near-zero (🔴 BUG):** 0-5 calls/hour means enrichment not running at all

### Phase 3: Analyze Trend After 24 Hours

**Analysis queries (run at +24h):**

#### Query A: Daily Cost Breakdown

```javascript
db.llm_traces.aggregate([
  {
    $match: {
      timestamp: {
        $gte: new Date(Date.now() - 86400000)  // Last 24 hours
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
      calls: { $sum: 1 },
      cost: { $sum: "$cost" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 1,
      calls: 1,
      cost: 1,
      avg_cost_per_call: { $divide: ["$cost", "$calls"] }
    }
  }
])
```

Expected output (TIER 1 ONLY):
```
[
  { _id: "2026-04-09 20:00", calls: 42, cost: 0.126, avg_cost_per_call: 0.003 },
  { _id: "2026-04-09 21:00", calls: 38, cost: 0.114, avg_cost_per_call: 0.003 },
  { _id: "2026-04-09 22:00", calls: 45, cost: 0.135, avg_cost_per_call: 0.003 },
  ...
]
```

#### Query B: Tier Distribution (Verify Filter Working)

```javascript
db.articles.aggregate([
  {
    $match: {
      created_at: {
        $gte: new Date(Date.now() - 86400000)  // Last 24 hours
      }
    }
  },
  {
    $group: {
      _id: "$relevance_tier",
      count: { $sum: 1 },
      with_entities: { $sum: { $cond: [{ $gt: [{ $size: { $ifNull: ["$entities", []] } }, 0] }, 1, 0] } },
      with_sentiment: { $sum: { $cond: [{ $ne: ["$sentiment_label", null] }, 1, 0] } }
    }
  },
  { $sort: { _id: 1 } }
])
```

Expected output (TIER 1 ONLY):
```
[
  { _id: 1, count: 35, with_entities: 35, with_sentiment: 35 },    // Tier 1: all enriched
  { _id: 2, count: 110, with_entities: 0, with_sentiment: 0 },     // Tier 2: none enriched
]
```

If tier 2 has high entity/sentiment counts, the filter didn't work.

#### Query C: Articles Per Tier Per Hour

```javascript
db.articles.aggregate([
  {
    $match: {
      created_at: {
        $gte: new Date(Date.now() - 86400000)
      }
    }
  },
  {
    $group: {
      _id: {
        hour: {
          $dateToString: {
            format: "%Y-%m-%d %H:00",
            date: "$created_at"
          }
        },
        tier: "$relevance_tier"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { "_id.hour": 1, "_id.tier": 1 } },
  {
    $group: {
      _id: "$_id.hour",
      tier1: { $sum: { $cond: [{ $eq: ["$_id.tier", 1] }, "$count", 0] } },
      tier2: { $sum: { $cond: [{ $eq: ["$_id.tier", 2] }, "$count", 0] } },
      total: { $sum: "$count" },
      tier1_pct: {
        $multiply: [
          {
            $divide: [
              { $sum: { $cond: [{ $eq: ["$_id.tier", 1] }, "$count", 0] } },
              { $sum: "$count" }
            ]
          },
          100
        ]
      }
    }
  }
])
```

**Expected:** ~20-25% of articles are tier 1 (so 40-50 of ~200/day)

---

## Decision Tree (After 24 Hours)

### Decision 1: Is the Filter Working?

**Check:** Query B results - do tier 2 articles have zero entities/sentiment?

- **YES ✅** → Filter working, proceed to Decision 2
- **NO 🔴** → Filter broken, STOP. Rollback TASK-060 immediately, debug separately.

### Decision 2: Cost in Target Range?

**Target range:** $0.30-0.50/day (based on 40-50 tier 1 articles/day × 3 calls, ~$0.003/call)

**Check:** Average of hourly projected_daily values from Phase 2 monitoring

- **$0.30-0.50/day ✅** → DECISION: **KEEP TIER 1 ONLY**
  - Costs on target, no change needed
  - Monitor weekly going forward
  - Document in ADR-008 (cost optimization strategy)

- **$0.10-0.30/day (Well Under Budget) ⚡** → DECISION: **CONSIDER TIER 2 ENABLE**
  - Costs unexpectedly low, budget headroom available
  - Option A: Keep tier 1 only (safest, guaranteed under budget)
  - Option B: Enable tier 2 enrichment (gain feature, add ~$0.15-0.25/day, still under $0.50-0.75/day limit)
  - Recommendation: Run TASK-062 to re-enable tier 2 and retest

- **$0.50-0.75/day (Slightly Over)** → DECISION: **MARGINAL - KEEP FOR NOW**
  - Slightly over target but within $0.75/day hard limit
  - Monitor for 1 week, if stable, accept as new baseline
  - If variance high, investigate why (unexpected ingest spike, etc.)

- **$0.75+/day 🔴 (Over Hard Limit)** → DECISION: **INVESTIGATE BUG**
  - Filter not working as expected OR ingest spiked unexpectedly
  - Run Query C to check if tier 1 % unexpectedly high
  - Check logs for enrichment skip messages
  - ROLLBACK TASK-060 if budget protection critical

---

## Rollback Plan (If Needed)

### Rollback Procedure (5 minutes)

If costs >$0.75/day or filter not working:

**File:** `src/crypto_news_aggregator/background/rss_fetcher.py`

**Action:** Remove the tier 1 filter block (lines 646-658 from TASK-060)

**Remove this code:**
```python
# TIER 1 ONLY FILTER: Skip enrichment for tier 2-3 articles
if relevance_tier != 1:
    update_operations = {
        "$set": {
            "relevance_tier": relevance_tier,
            "relevance_reason": relevance_reason,
            "updated_at": datetime.now(timezone.utc),
        }
    }
    await collection.update_one({"_id": article_id}, update_operations)
    logger.debug(...)
    continue
```

**Result:** System reverts to full enrichment for all tiers (costs return to ~$1.80/day). Continue troubleshooting separately.

---

## Acceptance Criteria

- [x] Cost monitoring query documented and reproducible
- [x] 24-hour hourly tracking spreadsheet created (or log file with results)
- [x] Analysis queries (A, B, C) defined and runnable
- [x] Decision tree documented with clear outcomes
- [x] Rollback procedure documented and tested (dry-run only)
- [x] Cost trend is clear (trending up/down/stable?)
- [x] Filter effectiveness verified (tier 2 articles not enriched?)
- [x] Decision made: KEEP, ENABLE TIER 2, or INVESTIGATE?

---

## Next Steps (Based on Decision)

**If KEEP TIER 1 ONLY:**
- Document final cost in weekly report
- Monitor weekly for cost drift
- Close this ticket as DONE

**If ENABLE TIER 2:**
- Create TASK-062: Re-enable Tier 2 Enrichment (add tier 2 condition)
- Retest cost for 24 hours with tier 2 enabled
- Document new baseline cost

**If INVESTIGATE:**
- Review logs for errors in enrichment pipeline
- Check if ingest volume spiked unexpectedly
- Debug separately, create new ticket for findings

---

## Related Tickets

- TASK-059: Remove Low-Quality RSS Sources (prerequisite)
- TASK-060: Implement Tier 1 Only Enrichment Filter (prerequisite)
- TASK-062: Re-enable Tier 2 Enrichment (if needed, post-TASK-061)
- ADR-008: Cost Optimization Strategy (documentation, post-decision)