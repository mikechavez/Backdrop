# BUG-108 Investigation: Complete Documentation

**Ticket:** `BUG-108-signals-page-no-signals.md` — Start here for the original problem statement.

**Status:** Investigation complete. Fix design defined with explicit state machine and retry policy. Awaiting operator decision on backlog cutoff and Railway evidence collection.

---

## Quick Navigation

### For Decision-Makers
Start here to understand what needs to happen next:

1. **`FINAL_SUMMARY_FOR_DECISION.md`** — Executive summary, decision checklist, timeline
2. **`RAILWAY_EVIDENCE_REQUIRED.md`** — What evidence you need to collect (15-30 min read-only inspection)

### For Engineers (Code Review)
Complete technical design ready for implementation:

1. **`STATE_MACHINE_CORRECTED.md`** — **REVISED** state machine design with corrections:
   - Fixed MongoDB query syntax (dotted paths for nested fields)
   - Fixed atomic update syntax ($inc separate from $set)
   - Clarified retry count (exactly 3 attempts)
   - Corrected hung timeout (600s, not 60s)
   - Handled legacy records (backfill on startup)
   - 4 comprehensive test cases covering all scenarios

2. **`IMPLEMENTATION_DIFF.md`** — Exact code changes required (7 sections, ~115 lines total):
   - Can review before any deployment decision
   - Shows MongoDB syntax correctness
   - Includes decision points (backlog age cutoff, timeout values, retry count)
   - Lists deployment gates (evidence, tests, regressions)

3. **`mongodb_investigation_queries.js`** — 6 read-only queries to validate root cause

### For Reference
Earlier analysis documents (useful for context, not required for decision):

- **`bug_108_investigation.md`** — Initial deep code analysis (5,000 words)
- **`INVESTIGATION_SUMMARY.md`** — First summary (now superseded)
- **`OPERATOR_ACTION_CHECKLIST.md`** — Early attempt at operator flow
- **`proposed_recovery_fix.md`** — Original (rejected) bounded-query proposal
- **`INVESTIGATION_REVISED.md`** — Summary of revision from original to state machine

---

## Root Cause (Summary)

Two separate issues:

1. **Unbounded backlog query** — Loads all 13,496+ unenriched articles without age cutoff
2. **Tier 2/3 infinite retry** — Articles classified as tier 2/3 have only `relevance_tier` set, but other fields remain missing; they stay eligible for enrichment query and are re-selected every cycle

**Result:** No entity mentions created → Empty Signals page

---

## Proposed Solution (Summary)

**State machine + retry policy:**
- Track article state: `pending` → `in_progress` → `completed` (or `failed`)
- Mark articles as `completed` after tier classification (regardless of tier)
- Retry failed articles up to 3 times with backoff (0min, 5min, 30min)
- Exclude `completed` articles from future processing

**Three backlog cutoff options:**
- **Option A:** Unlimited (process all historical articles)
- **Option B:** 30-day fresh articles only (recommended for safety)
- **Option C:** Progressive (prioritize fresh, eventually historical)

**Code complexity:** ~40-50 lines in `rss_fetcher.py`

---

## What's Required Before Fix Can Be Authorized

### Operator Must Provide:

1. **Railway Evidence** (read-only inspection, ~15 min)
   - Confirm deployment topology: single instance or replicas?
   - Trace extraction batch progression: did processing halt or complete?
   - Establish E11000 baseline: how often do duplicate-key errors occur?
   - See: `RAILWAY_EVIDENCE_REQUIRED.md` for detailed steps

2. **Operator Decision:**
   - Which backlog cutoff? Option A, B, or C?
   - See: `STATE_MACHINE_AND_RETRY_POLICY.md` (Backlog Cutoff Decision section)

### Engineer/Reviewer Will:

1. **Code review:** Verify atomic claims, state transitions, interrupt safety
2. **Unit tests:** Run 6 local tests (no staging needed) demonstrating:
   - Tier 1 happy path
   - Tier 2/3 not re-selected
   - Hung detection after 60s
   - Backoff schedule (0/5/30 min)
   - Max retries exceeded
   - Atomic claim prevents double-processing
3. **Merge to main:** Standard PR workflow
4. **Deploy:** Railway standard process

---

## Timeline

**Today (Phase 1: Validation)**
- Operator reviews `FINAL_SUMMARY_FOR_DECISION.md`
- Operator collects Railway evidence (15-30 min)
- Operator decides on backlog cutoff (A/B/C)
- Engineer reviews state machine design

**Tomorrow (Phase 2: Implementation)**
- Engineer implements state machine + retry policy (~2-3 hours)
- Run 6 unit tests locally (~30 min)
- Code review + merge

**Day 3 (Phase 3: Deployment)**
- Deploy to production
- Monitor for 48 hours

**Day 5 (Phase 4: Validation)**
- Confirm Signals page shows results
- Establish baselines
- Mark BUG-108 resolved

---

## Guarantees (What IS Guaranteed)

✅ No article processed by two concurrent processes (atomic `find_one_and_update` claim)
✅ Articles marked `completed` never re-selected (even if fields missing)
✅ Hung `in_progress` articles detected after 600s (10 min) and re-attempted
✅ Transient failures retry exactly 3 times with backoff (0/5/30 min delays)
✅ Progress preserved across restarts (only articles reaching `completed` status skipped)
✅ Legacy articles without `enrichment_state` are backfilled on startup

## What IS NOT Guaranteed

❌ "No article selected twice" — If crash before `completed` written, re-selected on next startup (legitimate retry of lost work)
❌ "Immediate processing" — Failed articles only retry after backoff delays (5-30 min)
❌ "All historical articles" — With age cutoff (Option B, recommended), articles >30d are skipped unless backfill requested

## Critical Implementation Fixes (From Review)

**Previous document had these errors, now corrected in `STATE_MACHINE_CORRECTED.md`:**

- ❌ MongoDB query used `{"enrichment_state": {"$in": [{"status": "pending"}]}}` → ✅ Now uses `{"enrichment_state.status": {"$in": ["pending"]}}`
- ❌ Update syntax put `$inc` inside `$set` (invalid) → ✅ Now separate `$set` and `$inc` operators
- ❌ Hung timeout was 60 seconds (too short) → ✅ Now 600 seconds (10 min)
- ❌ Retry count unclear (3 vs 4) → ✅ Explicit: exactly 3 attempts (attempt_count 1, 2, 3)
- ❌ Legacy articles not handled → ✅ Backfill on startup in `init_enrichment_state()`

---

## Separate Issues (Not Fixed)

- **BUG-108-A:** E11000 duplicate-key errors in ingestion (blocking enrichment cycles)
- **BUG-108-B:** NoneType errors in LLM extraction (batch processing failures)
- **PRODUCT-X:** Signals UI timeframe mismatch (24h label vs. 7d API default)

These should be separate tickets investigated after this fix is stable.

---

## Files in This Folder

| File | Purpose | Status |
|------|---------|--------|
| **DECISION & CODE REVIEW** |  |  |
| `BUG-108-signals-page-no-signals.md` | Original ticket (problem statement & investigation plan) | Reference |
| `FINAL_SUMMARY_FOR_DECISION.md` | Executive summary for authorization | Current |
| `RAILWAY_EVIDENCE_REQUIRED.md` | Step-by-step guide to collect evidence | Current |
| `STATE_MACHINE_CORRECTED.md` | **CORRECTED** technical design with 4 test cases | Current (use this) |
| `IMPLEMENTATION_DIFF.md` | **NEW** exact code changes for review (7 sections, ~115 lines) | Current (use this) |
| **ANALYSIS & CONTEXT** |  |  |
| `bug_108_investigation.md` | Initial deep code analysis (5,000 words) | Reference |
| `mongodb_investigation_queries.js` | 6 read-only MongoDB queries to validate root cause | Reference |
| **PREVIOUS VERSIONS (Superseded)** |  |  |
| `STATE_MACHINE_AND_RETRY_POLICY.md` | Original state machine design (had implementation bugs) | Superseded by CORRECTED version |
| `REVISED_FIX_PROPOSAL.md` | Earlier revision showing flaw with tier 2/3 | Reference |
| `INVESTIGATION_REVISED.md` | Summary of revision | Reference |
| `INVESTIGATION_SUMMARY.md` | First summary | Reference |
| `OPERATOR_ACTION_CHECKLIST.md` | Early operator flow | Reference |
| `proposed_recovery_fix.md` | Original proposal (rejected) | Reference |
| `README.md` | This file | Current |

---

## Critical Implementation Issues Found (Now Fixed)

You identified 5 critical bugs in the original state machine design:

1. **MongoDB query syntax** — Used wrong syntax for nested fields
2. **Atomic update syntax** — Placed $inc inside $set (invalid)
3. **Retry count confusion** — Unclear whether 3 or 4 attempts
4. **Hung timeout too short** — 60 seconds risks double-claiming
5. **Legacy records ignored** — Articles without enrichment_state never processed

**Status:** All 5 fixed in `STATE_MACHINE_CORRECTED.md` with corrected test cases.

---

## Next Step: Code Review Before Operator Decision

**BEFORE** asking operator for evidence and backlog cutoff decision:

1. **Review `IMPLEMENTATION_DIFF.md`** — Exact code changes (7 sections, ~115 lines)
   - Verify MongoDB syntax correctness
   - Check decision points (backlog age, timeout, retry count)
   - List deployment gates

2. **Review `STATE_MACHINE_CORRECTED.md`** — Corrected design and 4 test cases
   - Verify fixes to the 5 implementation issues
   - Check test coverage (legacy backfill, concurrent claim, interruption, retry count)

3. **Once code review approved:**
   - Ask operator for Railway evidence (topology, batch trace, E11000 baseline)
   - Ask operator to decide on backlog cutoff (Option A/B/C in IMPLEMENTATION_DIFF.md)
   - Proceed to deployment gate checklist

---

## Strong Hypothesis → Not Yet Confirmed

**Root cause suspected but not proven:**
- Code clearly has unbounded query + tier 2/3 reselection problem
- This alone doesn't prove it caused the observed restarts
- **Railway evidence will confirm or point to separate issue** (E11000, OOM, etc.)

Once operator provides evidence, root cause either confirmed or redirected to separate issue (BUG-108-A, BUG-108-B).

