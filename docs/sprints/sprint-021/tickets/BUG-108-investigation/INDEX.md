# BUG-108 Investigation Index

**Last Updated:** 2026-09-13 after implementation corrections

---

## Reading Path (Recommended Order)

### 1. Understand the Problem (5 min)
- **`BUG-108-signals-page-no-signals.md`** — Original ticket
- **`FINAL_SUMMARY_FOR_DECISION.md`** — Problem summary & decision checklist

### 2. What Code Review Found (2 min)
- **`CORRECTIONS_SUMMARY.md`** — The 5 implementation bugs and how they were fixed

### 3. Code Review (20 min)
- **`IMPLEMENTATION_DIFF.md`** — Exact code changes (reviewable independently)
- **`STATE_MACHINE_CORRECTED.md`** (sections 1-2 only) — Design with corrections

### 4. Operator Input (15 min)
- **`RAILWAY_EVIDENCE_REQUIRED.md`** — How to collect topology/trace/baseline
- Decide on backlog age cutoff (see IMPLEMENTATION_DIFF.md decision points)

### 5. Detailed Understanding (Optional)
- **`STATE_MACHINE_CORRECTED.md`** (sections 3-7) — Full state machine details
- **`STATE_MACHINE_CORRECTED.md`** (test cases) — Verify implementation correctness

---

## What Each Document Contains

### Decision Documents (Use These)

| Document | Purpose | Length | Audience |
|----------|---------|--------|----------|
| `CORRECTIONS_SUMMARY.md` | **NEW** - What was wrong and how it was fixed | 1 page | Everyone (before anything else) |
| `FINAL_SUMMARY_FOR_DECISION.md` | Executive summary & decision checklist | 4 pages | Operator/leadership |
| `RAILWAY_EVIDENCE_REQUIRED.md` | How to collect evidence (15-30 min) | 3 pages | Operator |

### Implementation Documents (Use These)

| Document | Purpose | Length | Audience |
|----------|---------|--------|----------|
| `IMPLEMENTATION_DIFF.md` | **FINAL** - Exact code changes, ready for review | 5 pages | Engineers/reviewers |
| `STATE_MACHINE_CORRECTED.md` | **FINAL** - Corrected design with 4 test cases | 8 pages | Engineers/reviewers |
| `mongodb_investigation_queries.js` | 6 read-only MongoDB queries | 1 page | Operator (optional) |

### Reference Documents (Background Only)

| Document | Purpose | Status |
|----------|---------|--------|
| `bug_108_investigation.md` | Initial root cause analysis | Superseded by STATE_MACHINE_CORRECTED |
| `STATE_MACHINE_AND_RETRY_POLICY.md` | Original design (had bugs) | Superseded by STATE_MACHINE_CORRECTED |
| `REVISED_FIX_PROPOSAL.md` | Earlier revision | Reference |
| `INVESTIGATION_REVISED.md` | Earlier summary | Reference |
| All other .md files | Early attempts | Reference |

---

## The 5 Implementation Bugs (Now Fixed)

See `CORRECTIONS_SUMMARY.md` for details. Quick reference:

1. **MongoDB query syntax** — Used wrong syntax for nested fields
2. **Atomic update syntax** — $inc inside $set (invalid)
3. **Retry count** — Unclear whether 3 or 4 attempts (now: exactly 3)
4. **Hung timeout** — 60s too short, now 600s (10 min)
5. **Legacy records** — Not handled, now backfilled on startup

---

## Key Decision Points

**Before deployment, decide:**

1. **Backlog age cutoff** (in `IMPLEMENTATION_DIFF.md` Change 3):
   - Option A: Unlimited (process all historical)
   - Option B: 30 days fresh only (recommended)
   - Option C: Progressive (complex)

2. **Hung detection timeout** (default 600s, adjustable):
   - Must be longer than expected cycle time
   - 600s = 10 min; cycle time ~30 min, so safe

3. **Retry count** (default 3, adjustable):
   - Exactly 3 attempts with 0/5/30 min backoff
   - Can adjust if different policy needed

---

## Testing Before Deployment

**4 unit tests (ready to run locally):**

1. **Legacy article backfill** — Articles without enrichment_state processed
2. **Atomic claim prevents double-processing** — Concurrent processes can't both claim same article
3. **Process interruption recovery** — Hung articles detected after 600s and re-attempted
4. **Exact retry count** — Exactly 3 attempts, then marked completed

All in `STATE_MACHINE_CORRECTED.md` test section.

---

## Deployment Gate Checklist

**Before any code merge/deployment:**

- [ ] Code review approved: `IMPLEMENTATION_DIFF.md`
- [ ] Design review approved: `STATE_MACHINE_CORRECTED.md`
- [ ] 4 unit tests pass locally
- [ ] Railway evidence collected (topology, trace, E11000 baseline)
- [ ] Backlog age cutoff decided (A/B/C)
- [ ] No regressions in existing functionality

---

## Root Cause Status

**Strongly suspected but not yet confirmed:**

✅ Code clearly has:
- Unbounded backlog query (loads all 13,496 articles)
- Tier 2/3 infinite reselection issue (articles re-selected every cycle)

❓ Railway evidence pending to confirm:
- Deployment topology (single vs. replicas)
- Batch extraction progress (did it halt or complete?)
- Whether E11000 or other errors blocked progress

**Once evidence arrives:** Either confirms root cause or redirects to separate issue (E11000, OOM, coordinator issue, etc.)

---

## Files to Ignore

**These are superseded; use the CORRECTED/FINAL versions instead:**

- `STATE_MACHINE_AND_RETRY_POLICY.md` — Original (has bugs; replaced by STATE_MACHINE_CORRECTED.md)
- `REVISED_FIX_PROPOSAL.md` — Earlier revision (background only)
- `INVESTIGATION_REVISED.md` — Earlier summary (background only)
- `bug_108_investigation.md` — Initial analysis (reference only)
- All others dated before 2026-09-13 16:57 UTC

---

## Quick Reference: MongoDB Query Fixes

**WRONG (what was in original):**
```python
{"enrichment_state": {"$in": [{"status": "pending"}]}}
```

**RIGHT (what's in IMPLEMENTATION_DIFF):**
```python
{"enrichment_state.status": {"$in": ["pending", "failed", "in_progress"]}}
```

**WRONG (atomic claim):**
```python
{"$set": {"attempt_count": {"$inc": 1}}}
```

**RIGHT (atomic claim):**
```python
{
    "$set": {"status": "in_progress", ...},
    "$inc": {"attempt_count": 1}
}
```

---

## Questions to Answer Before Proceeding

1. **Code review:** Is `IMPLEMENTATION_DIFF.md` correct? Any concerns?
2. **Design:** Is `STATE_MACHINE_CORRECTED.md` logic sound? Any issues with 4 test cases?
3. **Operator:** Can you collect Railway evidence (15-30 min)?
4. **Decision:** Which backlog cutoff (A/B/C)? Any other settings to adjust?

Once these are answered, fix is ready for merge and deployment.

