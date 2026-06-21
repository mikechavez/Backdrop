---
id: TASK-114E
type: task
status: open
priority: high
parent_sprint: Sprint 021 — Evidence & Investigation
phase: Phase A Exit Gate
depends_on: [TASK-114C, TASK-114D]
blocks: [TASK-124]
---

# Phase A Exit Gate — Consolidated Scorecard

## Goal

Produce the single document Mike actually reads to decide whether Phase B
(TASK-124 onward) starts. Pull results from TASK-114C (historical replay) and
TASK-114D (synthetic injection), check them against the full consolidated exit
criteria list below, and output a clear pass/fail/needs-judgment status per item.

This ticket does NOT make the go/no-go call. The three judgment-call criteria
are explicitly flagged for Mike's manual sign-off, not auto-passed.

## Consolidated Exit Criteria

Mechanical criteria (checkable from TASK-114C / TASK-114D output, mark
PASS / FAIL / N/A with the supporting evidence cited):

- [ ] At least 3 Evidence Packs generated (historical or synthetic) and stored
      successfully in the local Mongo instance
- [ ] No Evidence Pack has a missing section without an explicit reason recorded
      in `collection_errors` or `sections_missing`
- [ ] Configuration Evidence section populated with LLM budget settings and
      critical operations list (check at least one pack, ideally BUG-064 replay)
- [ ] LLM Trace Evidence section populated with operation counts, costs, and
      recent traces (check at least one pack)
- [ ] Log excerpts present for at least 2 of 3 services (FastAPI, Celery worker,
      Celery scheduler) in at least one pack
- [ ] Truncation metadata recorded correctly when log cap reached
      (from TASK-114D)
- [ ] Redaction applied — `redactions_applied` count accurate (from TASK-114D)
- [ ] Per-section `collected_at` timestamps present on all collected sections,
      across all packs from both TASK-114C and TASK-114D
- [ ] Evidence references (E-001, E-002...) indexable with no collisions, across
      ALL packs generated in both tiers combined — not just within a single pack
- [ ] At least one partial Evidence Pack (Railway unavailable/timeout) handled
      gracefully with explicit error record (from TASK-114D)
- [ ] BUG-064 replay reproduces the documented incident: resulting pack contains
      `llm_trace_summary.total_cost`, `config_evidence.critical_operations`,
      the blocked operation name (`briefing_generate`), and the 8 healthy
      signals listed in TASK-114C eliminating other subsystems
- [ ] Settling window timing verified via real monitor loop pass: default delay
      respected, critical-severity bypass confirmed (from TASK-114D)

Judgment-call criteria — **flag these clearly, do not mark pass/fail yourself**:

- [ ] Configuration Evidence is useful — would the budget settings and critical
      operations list have helped diagnose a real incident? Summarize what's in
      the section and let Mike judge.
- [ ] Log excerpts add signal beyond what metrics already show — summarize what
      the logs contained in the BUG-073 or BUG-064 replay vs. what the metrics
      alone would have shown, and let Mike judge.
- [ ] Evidence Pack is readable by a human unfamiliar with the incident — this
      is effectively what the TASK-114C blind diagnosis exercise already tested.
      Report the MATCH/PARTIAL/MISS scores from TASK-114C as direct input to
      this judgment, but don't convert it into a pass/fail yourself.

## Scope

### In Scope
- [ ] Pull and synthesize results from `TASK-114C-REPLAY-RESULTS.md` and
      `TASK-114D-SYNTHETIC-RESULTS.md`
- [ ] Score each mechanical criterion PASS/FAIL/N/A with a one-line citation of
      which pack/scenario it's based on
- [ ] Summarize (don't score) each judgment-call criterion with enough concrete
      detail that Mike can decide in under a minute per item
- [ ] Call out the known BUG-084 coverage gap from TASK-114C as a named, explicit
      finding — not buried in a pass/fail table. This is a real product gap
      (Evidence Packs can't currently catch content fabrication) that's worth
      Mike's attention independent of whether it blocks the gate
- [ ] Produce a one-line overall recommendation: READY FOR PHASE B / NOT READY /
      READY WITH CAVEATS, with reasoning — but make clear in the document this
      is a recommendation, not a decision Claude Code is making unilaterally

### Out of Scope
- Starting any Phase B work (TASK-124+) regardless of outcome
- Modifying any collector, schema, or monitor loop code
- Re-running TASK-114C or TASK-114D — if their output is incomplete or missing,
  stop and say so rather than re-deriving results

## Acceptance Criteria

- [ ] Single document: `PHASE-A-EXIT-GATE-SCORECARD.md`
- [ ] Every mechanical criterion has a PASS/FAIL/N/A and a citation
- [ ] All 3 judgment-call criteria are clearly separated from the mechanical
      table and explicitly marked as requiring Mike's sign-off
- [ ] BUG-084 coverage gap has its own named section, not folded into a checkbox
- [ ] One-line recommendation at the top of the document, full reasoning below
- [ ] Document assumes the reader has NOT read TASK-114C/114D in detail — it
      should be self-contained enough that Mike can act on it without opening
      the other two reports, while still linking to them for anyone who wants
      the raw detail

## Notes for Implementing Agent

- Resist the urge to round judgment-call items up to "pass" because the
  mechanical criteria mostly passed. They're separated for a reason — self-
  certification risk is exactly what this ticket structure is designed to avoid.
- If TASK-114C or TASK-114D surfaced any finding that contradicts something in
  the original sprint doc's assumptions (e.g. a collector behaving differently
  than documented), surface it here even if it's not one of the listed criteria.
