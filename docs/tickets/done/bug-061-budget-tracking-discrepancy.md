---
id: BUG-061
type: bug
status: backlog
priority: high
severity: high
created: 2026-04-09
updated: 2026-04-09
---

# BUG-061: Budget Tracking Discrepancy and Missing Briefing Generation

## Problem

Session 10 reported that soft spend limit at $3.00 was hit and blocking briefing generation. Database investigation reveals actual spend is only $0.445, well under the limit. Additionally, no briefing generation operations have been recorded in the past 24 hours.

## Expected Behavior

- Briefing generation should run on schedule (8 AM and 8 PM EST = 13:00 and 01:00 UTC)
- Briefing generation cost should be visible in cost tracking collections
- Soft limit blocking should only occur when daily spend exceeds $3.00

## Actual Behavior

Investigation performed 2026-04-09 using direct MongoDB queries via mongosh.

---

## Database Query Results

### Query 1: Cost Breakdown by Operation (Last 24 hours)

**Query:**
```javascript
db.llm_traces.aggregate([
  { $match: { timestamp: { $gte: new Date(Date.now() - 24*60*60*1000) } } },
  { $group: { _id: "$operation", total_cost: { $sum: "$cost" }, calls: { $sum: 1 }, total_input: { $sum: "$input_tokens" }, total_output: { $sum: "$output_tokens" } } },
  { $sort: { total_cost: -1 } }
]).toArray();

db.api_costs.aggregate([
  { $match: { timestamp: { $gte: new Date(Date.now() - 24*60*60*1000) } } },
  { $group: { _id: "$operation", total_cost: { $sum: "$cost" }, calls: { $sum: 1 } } },
  { $sort: { total_cost: -1 } }
]).toArray();
```

**Results:**

```
=== LLM_TRACES (Last 24 hours) ===
narrative_generate: 87 calls, $0.262412
entity_extraction: 215 calls, $0.188784
Total: $0.451196

=== API_COSTS (Last 24 hours) ===
narrative_generate: 87 calls, $0.262412
entity_extraction: 46001 calls, $0.182703
Total: $0.445115
```

---

### Query 2: Collection Sizes

**Query:**
```javascript
const traceCount = db.llm_traces.countDocuments({});
const costCount = db.api_costs.countDocuments({});
console.log(`llm_traces: ${traceCount} documents`);
console.log(`api_costs: ${costCount} documents`);
```

**Results:**
```
llm_traces: 302 documents
api_costs: 46088 documents
```

---

### Query 3: Detailed Timeline by Hour (Last 24 hours)

**Query:**
```javascript
const timeline = db.llm_traces.aggregate([
  { $match: { timestamp: { $gte: oneDayAgo } } },
  { $group: { 
      _id: { $dateToString: { format: "%Y-%m-%d %H:00", date: "$timestamp" } },
      total_cost: { $sum: "$cost" },
      calls: { $sum: 1 }
    } 
  },
  { $sort: { _id: 1 } }
]).toArray();
```

**Results:**
```
=== DETAILED TIMELINE (Last 24 hours) ===
2026-04-09 02:00: $0.003434 (2 calls)
2026-04-09 03:00: $0.270544 (98 calls)
2026-04-09 04:00: $0.011666 (12 calls)
2026-04-09 05:00: $0.008082 (11 calls)
2026-04-09 06:00: $0.016815 (20 calls)
2026-04-09 07:00: $0.003790 (4 calls)
2026-04-09 08:00: $0.003684 (5 calls)
2026-04-09 09:00: $0.002200 (2 calls)
2026-04-09 10:00: $0.024171 (26 calls)
2026-04-09 11:00: $0.012619 (13 calls)
2026-04-09 12:00: $0.013685 (16 calls)
2026-04-09 13:00: $0.016227 (18 calls)
2026-04-09 14:00: $0.037880 (40 calls)
2026-04-09 15:00: $0.026399 (35 calls)
```

---

### Query 4: Entity Extraction Details (Cached vs Paid)

**Query:**
```javascript
const byOp = db.api_costs.aggregate([
  { $match: { timestamp: { $gte: oneDayAgo } } },
  { $group: { 
      _id: "$operation",
      total_cost: { $sum: "$cost" },
      calls: { $sum: 1 },
      cached_calls: { $sum: { $cond: ["$cached", 1, 0] } }
    }
  },
  { $sort: { total_cost: -1 } }
]).toArray();
```

**Results:**
```
=== BY OPERATION ===
narrative_generate:
  Total calls: 87
  Cached calls: 0
  Paid calls: 87
  Cost: $0.262412

entity_extraction:
  Total calls: 46001
  Cached calls: 45791
  Paid calls: 210
  Cost: $0.182703
```

---

### Query 5: All Operations in Database

**Query:**
```javascript
const ops = db.api_costs.aggregate([
  { $group: { _id: "$operation", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]).toArray();
```

**Results:**
```
=== ALL OPERATIONS IN DATABASE ===
entity_extraction: 46001
narrative_generate: 87
```

**Note:** No `briefing_generation`, `briefing_generate`, `briefing_critique`, or `briefing_refine` operations found.

---

### Query 6: Cost Timeline by Operation

**Query:**
```javascript
const timeline = db.api_costs.aggregate([
  { $group: {
      _id: { 
        hour: { $dateToString: { format: "%Y-%m-%d %H:00", date: "$timestamp" } },
        operation: "$operation"
      },
      count: { $sum: 1 },
      total_cost: { $sum: "$cost" }
    }
  },
  { $sort: { "_id.hour": 1, "_id.operation": 1 } }
]).toArray();
```

**Results:**
```
=== OPERATION TIMELINE (by hour) ===
2026-04-09 03:00 - entity_extraction: 5936 calls, $0.005485
2026-04-09 03:00 - narrative_generate: 87 calls, $0.262412
2026-04-09 04:00 - entity_extraction: 4492 calls, $0.011666
2026-04-09 05:00 - entity_extraction: 4516 calls, $0.008082
2026-04-09 06:00 - entity_extraction: 3068 calls, $0.016815
2026-04-09 07:00 - entity_extraction: 3104 calls, $0.003790
2026-04-09 08:00 - entity_extraction: 3128 calls, $0.003684
2026-04-09 09:00 - entity_extraction: 1576 calls, $0.002200
2026-04-09 10:00 - entity_extraction: 3224 calls, $0.024171
2026-04-09 11:00 - entity_extraction: 3304 calls, $0.012619
2026-04-09 12:00 - entity_extraction: 3388 calls, $0.013685
2026-04-09 13:00 - entity_extraction: 3460 calls, $0.016227
2026-04-09 14:00 - entity_extraction: 3580 calls, $0.037880
2026-04-09 15:00 - entity_extraction: 3225 calls, $0.026399
```

**Note:** Morning briefing scheduled for ~13:00 UTC (2026-04-09 13:00). No briefing operations recorded at this time.

---

### Query 7: Briefing Generation Status

**Query:**
```javascript
const oneDayAgo = new Date(Date.now() - 24*60*60*1000);

const count = db.briefing_drafts.countDocuments({ 
  timestamp: { $gte: oneDayAgo }
});

const briefingCount = db.briefings.countDocuments({ 
  created_at: { $gte: oneDayAgo }
});

const statuses = db.briefing_drafts.aggregate([
  { $group: { _id: "$status", count: { $sum: 1 } } }
]).toArray();

const latest = db.briefing_drafts.findOne({}, { sort: { timestamp: -1 } });
```

**Results:**
```
=== BRIEFING DRAFTS (Last 24h) ===
Drafts created: 0

=== BRIEFINGS (Last 24h) ===
Briefings created: 0

=== BRIEFING_DRAFTS BY STATUS (all time) ===
(empty - no documents)

=== LATEST DRAFT ===
No drafts found
```

---

### Query 8: Cost Tracking Sample Document

**Query:**
```javascript
const sample = db.llm_traces.findOne();
```

**Results:**
```json
{
  "_id": "69d7138afa7209e6093de461",
  "trace_id": "2e1fd329-ebd1-4209-b3ff-538db8ab5edc",
  "operation": "entity_extraction",
  "timestamp": "2026-04-09T02:48:42.632Z",
  "model": "claude-haiku-4-5-20251001",
  "input_tokens": 357,
  "output_tokens": 272,
  "cost": 0.001717,
  "duration_ms": 1618.8,
  "error": null,
  "quality": {
    "passed": null,
    "score": null,
    "checks": []
  }
}
```

---

## Key Findings

1. **Cost is well under limit:** $0.445115 actual spend vs $3.00 soft limit (85% under budget)
2. **Two cost tracking collections exist:** llm_traces (302 docs) and api_costs (46,088 docs)
   - llm_traces: $0.451196 (from gateway tracing)
   - api_costs: $0.445115 (older tracking system)
3. **Only two operations recorded:** narrative_generate and entity_extraction
   - **No briefing operations recorded** (briefing_generation, briefing_generate, briefing_critique, briefing_refine)
4. **Entity extraction is highly cached:** 45,791 of 46,001 calls cached (99.5%), only $0.1827 actual cost
5. **Narrative generate spike at 03:00 UTC:** 87 calls in single hour ($0.2624), then no more narrative_generate
6. **Morning briefing scheduled for 13:00 UTC:** No activity visible in cost tracking
7. **Zero briefing generation activity:** No drafts created, no briefings generated

---

## Environment

- Environment: production (Railway)
- Burn-in period: Started 2026-04-09 02:48 UTC
- Database: MongoDB Atlas (crypto_news collection)
- Hard limit: $15.00
- Soft limit: $3.00
- Query execution: 2026-04-09 (current session)

---

## Resolution

<!-- To be filled in after investigation -->

**Status:** Open
**Fixed:** 
**Branch:**
**Commit:**

### Root Cause

TBD - Requires investigation into:
1. Why no briefing operations appear in cost tracking (briefing tasks not running, or not recording costs)
2. Why narrative_generate spike occurred at 03:00 UTC and then stopped
3. Expected behavior of cost tracking across multiple collections (llm_traces vs api_costs)

### Changes Made

### Testing

### Files Changed
