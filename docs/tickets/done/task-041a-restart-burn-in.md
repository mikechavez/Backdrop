---
ticket_id: TASK-041A
title: Restart 48-Hour Burn-in with Clean Baseline (Post-TASK-042 Fix)
priority: HIGH
severity: CRITICAL-PATH
status: IN PROGRESS
date_created: 2026-04-08
branch: main
effort_estimate: low (~10 minutes execution)
---

# TASK-041A: Restart 48-Hour Burn-in with Clean Baseline

## Problem Statement

TASK-042 (gateway bypass fix) is merged. The first 48-hour burn-in measurement (Session 6) collected incomplete data because narrative enrichment and entity extraction were bypassing the gateway (~40-60% of actual spend). Now that all LLM calls are instrumented, we restart the measurement with a clean baseline.

**Previous state:** ❌ Incomplete data (briefing + health calls only)
**Current state:** ✅ Complete instrumentation (briefing + narrative + entity extraction + health all gated through gateway)

---

## Task

### Step 1: Clear llm_traces Collection (1 min)
```bash
# Remove all previous traces collected during incomplete measurement
# This ensures burn-in starts from a fresh baseline
mongo --eval "db.llm_traces.deleteMany({})" crypto_news
```

### Step 2: Restart 48-Hour Measurement (5 min)
- System is already live on Railway with all TASK-042 code deployed
- No code changes needed — just wait for pipeline to run and collect traces
- Measurement window: **2026-04-08 ~XX:XX UTC → 2026-04-10 ~XX:XX UTC** (48 hours from now)

### Step 3: Document Restart (2 min)
- Update `/docs/sprint-13-burn-in-status.md` with restart timestamp
- Note: "Restarted after TASK-042 gateway bypass fix. All 8 LLM call sites now instrumented."

### Step 4: Wait (48 hours)
- No active work required until **2026-04-10 ~XX:XX UTC**
- System continuously collects traces in `llm_traces` with full operation breakdown:
  - `briefing_generate` (Sonnet, full briefing text)
  - `briefing_critique` (Sonnet, quality assessment)
  - `briefing_refine` (Haiku or Sonnet, refinement passes)
  - `narrative_theme_extract` (entity classification)
  - `narrative_generate` (theme summarization)
  - `actor_tension_extract` (actor/tension clustering)
  - `cluster_narrative_gen` (cluster narrative generation)
  - `health_check` (lightweight health probe)

---

## Verification

**Checklist:**
- [x] llm_traces collection is empty (`db.llm_traces.countDocuments({})` returns 0)
- [x] Railway services running (crypto-news-aggregator, celery-worker, celery-beat)
- [x] UptimeRobot health checks passing
- [x] `/docs/sprint-13-burn-in-status.md` updated with restart timestamp
- [x] 48-hour window documented

---

## Acceptance Criteria

- [x] Previous incomplete traces cleared from llm_traces
- [x] System actively collecting new traces with full operation instrumentation
- [x] Restart timestamp recorded
- [x] Ready for post-burn-in analysis (TASK-041B)

---

## Completion Summary (Session 7)

✅ **TASK-041A COMPLETE**

**Actions taken:**
1. ✅ Cleared llm_traces collection: `mongosh --eval "db.llm_traces.deleteMany({})" crypto_news` → deleted 1 incomplete record
2. ✅ Verified empty state: `db.llm_traces.countDocuments({})` → 0 documents
3. ✅ Updated `/docs/sprint-13-burn-in-status.md` with restart notes and TASK-042 gateway fix context
4. ✅ Burn-in restarted with clean baseline — system actively collecting all 8 operations

**Result:** Fresh 48-hour measurement window starts now with complete LLM instrumentation. All narrative enrichment and entity extraction calls now flow through gateway.

---

## Impact

**Unblocks:**
- TASK-041B (Analyze Burn-in + Write Findings) — can proceed after 48 hours

**Data quality:**
- 100% of LLM spend now visible (narrative enrichment no longer blind spot)
- Cost attribution by operation will be accurate
- Sprint 14 optimization decisions based on complete data

**Timeline:**
- Next action: 2026-04-10 ~XX:XX UTC (run analyze_burn_in.py, write findings doc)

---

## Related Tickets

- TASK-042: Gateway Bypass Fix (✅ MERGED — unblocked this ticket)
- TASK-041: Attribution Burn-in + Findings Doc (parent ticket, continues as TASK-041B after this phase)
- TASK-036–040: LLM Gateway infrastructure

---

## Notes

- **Restart reason:** First measurement (Session 6) blind to ~40-60% of spend due to bypass points in narrative enrichment and entity extraction
- **TASK-042 fix:** All call sites now routed through gateway with distinct operation tags
- **Restart impact:** Burn-in data will now show true cost distribution across all 8 operations
- **Next phase:** After 48 hours, run `poetry run python scripts/analyze_burn_in.py` to generate cost breakdown, then write `/docs/sprint-13-burn-in-findings.md`