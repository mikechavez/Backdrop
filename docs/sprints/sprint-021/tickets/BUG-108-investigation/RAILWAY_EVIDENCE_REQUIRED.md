# Railway Evidence Required for BUG-108 Authorization

**Purpose:** Confirm restart loop hypothesis and validate that fix targets the actual root cause.

**Without this evidence, the fix design is theoretically sound but unvalidated.**

---

## Evidence 1: Deployment Topology

**Question:** Is this single instance or multiple replicas?

### How to Check

**In Railway Dashboard:**
1. Navigate to your environment/service
2. Go to **Deployments** tab
3. Find the deployment active on 2026-09-13 (around 21:45 UTC)
4. Note the instance configuration: `replicas: 1` or `replicas: >1`?
5. Go to **Events** tab
6. Search for restart/crash events between 21:00-23:00 UTC on 2026-09-13
7. Count how many restart events occurred

### What You're Looking For

**If `replicas: 1`:**
- Expect 1-5 restart events in the 21:00-23:00 UTC window
- Each restart logs "Running initial RSS fetch on startup..."
- Confirms single instance crashing repeatedly ✅

**If `replicas: >1`:**
- Multiple instances could be starting up
- Each logs independently
- Less likely to cause 13,496-article backlog (less coordinated work)

### Report Template

```
Instance configuration: replicas = [__]
Restart events (21:00-23:00 UTC on 2026-09-13): [__] total
Event timestamps: [list them]
Event types: [crash, health check failure, manual restart, deployment, etc.]
```

---

## Evidence 2: Extraction Batch Progression

**Question:** Did batch processing complete, halt, or error?

### How to Check

**In Railway Logs:**

1. **Find batch 0-10 log entry:**
   - Search for: `"Processing entity extraction batch 0-10"`
   - Expected time: ~21:45:58 UTC
   - Copy the exact timestamp

2. **Look for subsequent batches:**
   - Search for: `"Processing entity extraction batch 10-20"`
   - Search for: `"Processing entity extraction batch 20-30"`
   - Continue until you find where batches stop
   
3. **Look for completion message:**
   - Search for: `"Entity extraction complete:"`
   - If found, note the timestamp
   - Count articles processed, entities extracted

4. **Look for error messages around the halt point:**
   - Search for: `"E11000"` (duplicate key error)
   - Search for: `"NoneType"` (extraction failure)
   - Search for: `"rate_limit"` or `"timeout"` (provider issues)
   - Search for: `"Exception"` or `"Error"` (any error)
   - Get full traceback if available

### What You're Looking For

**Complete extraction (success):**
```
21:45:58 Processing entity extraction batch 0-10 of 13496
21:46:15 Processing entity extraction batch 10-20 of 13496
...
22:30:00 Entity extraction complete: articles=13496, entities=X, processing_time=Y
```
✅ Confirms enrichment ran to completion; issue is elsewhere

**Partial extraction (halted at batch):**
```
21:45:58 Processing entity extraction batch 0-10 of 13496
21:46:15 Processing entity extraction batch 10-20 of 13496
[no further batch logs]
22:00:00 [different process starts, e.g., "Running initial RSS fetch"]
```
❌ Confirms extraction halted; need to find why

**Error-triggered halt:**
```
21:45:58 Processing entity extraction batch 0-10 of 13496
21:46:15 ERROR: E11000 duplicate key error dup key: { url: "..." }
[no further logs for this cycle]
22:00:00 [container restarts]
```
❌ Confirms E11000 blocking enrichment; separate issue from backlog

### Report Template

```
Batch 0-10: Found at [timestamp]
Batch 10-20: Found? [Yes/No] at [timestamp]
Batch 20-30: Found? [Yes/No] at [timestamp]
Last batch found: [batch X-Y] at [timestamp]
Extraction complete message: Found? [Yes/No] at [timestamp]

Error messages:
- E11000: [Yes/No] [timestamp] [error details]
- NoneType: [Yes/No] [timestamp] [error details]
- Other: [list any other errors]

Conclusion: Extraction [completed successfully / halted at batch X / failed with error]
```

---

## Evidence 3: E11000 Baseline Frequency

**Question:** How often do duplicate-key errors block enrichment?

### How to Check

**In Railway Logs:**

1. **Set time range:** Last 7 days (from 2026-09-06 to 2026-09-13)

2. **Search for E11000 errors:**
   - Search for: `"E11000"`
   - Note each occurrence with timestamp and URL causing the duplicate

3. **Estimate frequency:**
   - Count total E11000 errors in 7 days
   - Estimate per-cycle impact (enrichment runs ~48 times per 7 days = ~30 min intervals)
   - Calculate: E11000 errors / 48 cycles = errors per cycle on average

4. **Identify patterns:**
   - Same URL repeated? (malformed URL dedupe?)
   - Same source duplicating? (RSS feed publishing duplicates?)
   - Different sources? (content syndication?)

### What You're Looking For

**Low frequency (acceptable):**
```
Last 7 days: 2-5 E11000 errors total
Per cycle: ~0.04-0.1 errors/cycle
Pattern: Different URLs, no clear pattern
```
✅ E11000 is not a major blocker; may not explain empty Signals page

**High frequency (problematic):**
```
Last 7 days: 20+ E11000 errors
Per cycle: ~0.4+ errors/cycle
Pattern: Same URL repeatedly, same source, or malformed URLs
```
❌ E11000 likely blocking cycles; separate ticket needed (BUG-108-A)

### Report Template

```
E11000 errors in last 7 days: [__] total
Average per cycle (48 cycles): [__]
Timestamps: [list a few examples]
URLs causing duplicates: [patterns or examples]
Sources involved: [which news sources?]
Baseline conclusion: E11000 is [rare / moderate / frequent] blocker
```

---

## Integration: Combining the Evidence

### Scenario 1: Confirms Restart Loop Hypothesis ✅

```
Topology: replicas = 1
Restarts: 4 events between 21:00-23:00 UTC
Batches: Halt at 0-10, no subsequent batches logged
E11000: Low frequency (not the cause)
Extraction: No completion message; no error message in logs

Conclusion:
- Container restarted 4 times in 2 hours
- Each restart re-ran batch 0-10
- Extraction halted mid-batch (possible OOM?)
- No error logged; suggests silent crash
- E11000 not the blocker
=> FIX TARGETS CORRECT ROOT CAUSE ✅
```

### Scenario 2: E11000 Is the Actual Blocker ❌

```
Topology: replicas = 1
Restarts: 2 events
Batches: Halt at 0-10
E11000: 8 errors in 7 days, 2 on 2026-09-13 around 21:45
Extraction: Error logged "E11000 duplicate key error"

Conclusion:
- Single restart isn't explaining empty Signals
- E11000 error is blocking enrichment in multiple cycles
- Backlog fix won't help if E11000 re-occurs
=> NEED SEPARATE BUG-108-A FIX FOR INGESTION ❌
```

### Scenario 3: Multiple Replicas (Coordination Issue) ❌

```
Topology: replicas = 3
Restarts: 6-9 events (multiple instances restarting)
Batches: Multiple instances logging "batch 0-10"
E11000: High frequency

Conclusion:
- Multiple instances racing to process same articles
- Duplicate work, duplicate key errors, coordination issues
- Backlog issue is secondary; need instance coordination fix first
=> BACKLOG FIX INSUFFICIENT; NEED COORDINATION/LOCKING ❌
```

---

## Timeline for Evidence Collection

**Estimated effort:** 15-30 minutes

1. **Check topology:** 2 minutes (Railway dashboard)
2. **Find batch logs:** 5 minutes (search logs for "batch")
3. **Trace extraction completion:** 5 minutes (search for "Entity extraction complete")
4. **Search for errors:** 5 minutes (E11000, NoneType, etc.)
5. **Compile report:** 3 minutes

**No code changes or production writes needed** — Read-only queries only.

---

## Decision Gate

**Do NOT proceed with fix authorization until:**

- [ ] Evidence 1 (Topology): Single instance vs. replicas confirmed
- [ ] Evidence 2 (Batch progression): Extraction halted or completed confirmed
- [ ] Evidence 3 (E11000 baseline): Frequency and impact established
- [ ] Integration analysis: Evidence supports backlog hypothesis OR points to separate issue

**If evidence points to separate root cause (E11000, replicas, etc.):**
- Document findings as separate ticket (BUG-108-A, BUG-108-B, etc.)
- Defer backlog fix until primary cause is addressed
- OR fix both in parallel (backlog + E11000 handling + coordination)

---

## What Evidence Does NOT Need

- ❌ Permission to modify production data
- ❌ Permission to restart services or clear caches
- ❌ Permission to run production API calls
- ❌ New monitoring infrastructure setup
- ❌ Database migrations or schema changes yet

**Just read-only inspection of existing logs and configuration.**

