# TASK-098: Revised Controlled Bootstrap Plan

**Status:** Phase 2 Complete - Ready for Phase 3 Approval  
**Date:** 2026-05-10  
**Approach:** Small, measured first refresh of top 5 narratives

---

## Executive Summary

After verification:
- ✅ **Phase 0:** Display-mode behavior - all narratives untrusted, display fields missing
- ✅ **Phase 1:** Top 5 narratives selected and verified eligible for refresh
- ✅ **Phase 2:** Dry-run completed without mutations

**Proposed action:** Flag only top 5 narratives for refresh. If successful, can bootstrap additional narratives in future phases.

---

## Phase 0: Display-Mode Verification

**Findings:**

All top active narratives have:
- `display_mode: None` (not set)
- `display_title: None` (not set)
- `display_summary: None` (not set)

**Interpretation:**
FEATURE-061/062 display-mode fields have not been populated in the database. This means the system currently cannot differentiate between trusted and untrusted narratives at the API layer. This is a separate issue from the narrative refresh and does not block Phase 4.

**Status:** Acknowledged. Will investigate FEATURE-061/062 in a separate ticket if needed.

---

## Phase 1: Select Top 5 Narratives

**Selected narratives (by recency):**

| # | Title | ID | Lifecycle | first_seen | article_count | Eligible |
|---|-------|----|-----------|----|---|---|
| 1 | Senate Banking Committee Advances Crypto Regulation Efforts | 695eb4b3ce758d67abd6e8f4 | emerging | 2026-01-06 | 4 | ✅ |
| 2 | LayerZero Admits Mistakes in $292M Kelp DAO Exploit | 698baa105278ec9e19bf2a19 | emerging | 2026-02-10 | 3 | ✅ |
| 3 | Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows | 68f32d197082f49df56956c6 | emerging | 2025-10-18 | 6 | ✅ |
| 4 | SEC Signals New Regulatory Framework for Onchain Markets | 68f03343bc9ab7390ca7af71 | emerging | 2025-10-10 | 3 | ✅ |
| 5 | Coinbase Navigates Infrastructure Crisis Amid Market Recovery | 68f03350bc9ab7390ca7af78 | emerging | 2025-10-15 | 3 | ✅ |

**Current state (all untrusted):**
- All have: `last_summary_generated_at: None`
- All have: `needs_summary_update: False`
- All have: Articles available for refresh
- All are: Non-dormant, active narratives

---

## Phase 2: Dry-Run Analysis (No Mutations)

### What Would Happen

**Phase 4A (Manual, approval-gated):**
```javascript
db.narratives.updateMany(
  {"_id": {"$in": [5 ObjectIds]}},
  {"$set": {"needs_summary_update": true}}
)
```
Result: 5 documents updated

**Phase 4B (Automated, refresh_flagged_narratives task):**
For each of the 5 narratives:
1. Task finds narratives with `needs_summary_update=True`
2. Fetches articles for each
3. Calls LLM: `generate_narrative_from_cluster(articles)`
4. Updates narrative:
   - `title`: Fresh generated title
   - `summary`: Fresh generated summary
   - `last_summary_generated_at`: NOW (makes it TRUSTED)
   - `needs_summary_update`: False

Result: 5 documents updated + 5 LLM calls

### Queue Status

**Currently flagged narratives:** 0  
**After Phase 4A:** 5  
**Would be processed:** All 5 (within MAX_REFRESH_PER_RUN=20 limit)

---

## Cost Estimate

```
5 narratives × ~0.002 cost per narrative_generate = ~$0.01

Daily budget: $10 soft, $15 hard
Impact: <1% of soft limit (negligible)
```

---

## Expected Outcome

### Before Refresh
```
Narratives with last_summary_generated_at >= 2026-05-10: 0
Trust status: All UNTRUSTED
Display mode: Cannot serve fresh summaries
Briefing synthesis: No narratives available
```

### After Refresh
```
Narratives with last_summary_generated_at >= 2026-05-10: 5
Trust status: All 5 become TRUSTED
Display mode: Can serve fresh summaries (once FEATURE-061/062 implemented)
Briefing synthesis: 5 trusted narratives available
→ Smoke briefing can proceed
→ Production briefing can resume if smoke passes
```

---

## Safety Guardrails

### Budget Protection
```python
check_llm_budget("narrative_generate")  # Enforced during refresh
# Won't exceed soft/hard limits
```

### Error Handling
```python
if articles empty:
    needs_summary_update = False  # Clear flag, continue
    
if LLM fails:
    needs_summary_update = False  # Clear flag, continue (no retry loop)
```

### Max Per-Run Limit
```python
MAX_REFRESH_PER_RUN = 20  # Our 5 well within limit
```

### No Data Corruption
- All updates use existing, tested code path
- Timestamps set by code (not manual SQL)
- If quality is poor, smoke briefing rejects (high confidence threshold)
- Can re-run to fix issues

---

## Rollback Plan

**If Phase 4A succeeds but Phase 4B fails:**
- Narratives stay with `needs_summary_update=True`
- Can re-run refresh task to complete

**If Phase 4B produces poor quality:**
- Smoke briefing rejects on low confidence_score
- Production briefing doesn't run
- Can trigger another refresh cycle to improve

**No permanent data damage possible.**

---

## Phase 3: Approval Gate

**Awaiting explicit approval for:**

```
Set needs_summary_update=True for these 5 narrative IDs:
  1. 695eb4b3ce758d67abd6e8f4
  2. 698baa105278ec9e19bf2a19
  3. 68f32d197082f49df56956c6
  4. 68f03343bc9ab7390ca7af71
  5. 68f03350bc9ab7390ca7af78

Then run refresh_flagged_narratives to generate fresh summaries.
```

**Do NOT proceed to Phase 4 without explicit approval.**

---

## Phase 4: Execute (If Approved)

**Step 1:** Run Phase 4A script
```bash
poetry run python3 scripts/task_098_phase4_execute_refresh.py
```

This will:
- Set `needs_summary_update=True` for 5 IDs
- Trigger refresh_flagged_narratives task (or show how to trigger manually)
- Monitor refresh progress
- Report LLM cost

**Step 2:** Wait for completion (~30-60 seconds)

**Step 3:** Proceed to Phase 5 (Verification)

---

## Phase 5: Post-Refresh Verification

**Run:**
```bash
poetry run python3 scripts/task_098_phase1_select_top5.py
```

**Expected output:**
- All 5 narratives have `last_summary_generated_at >= 2026-05-10`
- `needs_summary_update`: False
- New `title` and `summary` fields populated

**Metrics:**
- LLM cost during refresh window
- Number of narrative_generate traces created
- Success/error count

---

## Phase 6: Briefing Readiness

```
With 5 trusted narratives available:
  ✅ Can run smoke briefing
  ✅ If smoke confidence_score >= 0.5, can resume production briefing
```

---

## Success Criteria

- [ ] Phase 4A: 5 narratives flagged
- [ ] Phase 4B: refresh_flagged_narratives completes
- [ ] Phase 5: All 5 have `last_summary_generated_at >= 2026-05-10T00:00:00Z`
- [ ] Smoke briefing (if run): confidence_score >= 0.5
- [ ] No errors in refresh task logs
- [ ] LLM cost ~$0.01

---

## Next Actions

### Immediately After Approval:
1. Execute Phase 4 (run refresh)
2. Execute Phase 5 (verify)
3. Evaluate for Phase 6 (smoke briefing)

### Future (If Phase 4-5 Successful):
- Bootstrap additional narratives in later phases
- Investigate FEATURE-061/062 (display-mode fields)
- Plan for scheduled narrative refresh cadence

---

## Key Differences From Previous Plan

| Aspect | Previous | Revised |
|--------|----------|---------|
| Initial scope | 20 narratives | 5 narratives |
| Dry-run | Minimal | Complete (Phase 2) |
| Display-mode verification | Skipped | Included (Phase 0) |
| Approval gate | Implicit | Explicit |
| Cost | $0.04 | $0.01 |
| Risk | Moderate | Low |
| Learning opportunity | Limited | High (measure first refresh success) |

---

## Files

- **Phase 0 script:** `scripts/task_098_phase0_display_mode.py`
- **Phase 1 script:** `scripts/task_098_phase1_select_top5.py`
- **Phase 2 script:** `scripts/task_098_phase2_dryrun.py`
- **Phase 4 script:** `scripts/task_098_phase4_execute_refresh.py` (prepared, not yet run)
- **This document:** `TASK-098-REVISED-PLAN.md`
