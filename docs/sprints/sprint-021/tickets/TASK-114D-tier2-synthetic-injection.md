---
id: TASK-114D
type: task
status: open
priority: high
parent_sprint: Sprint 021 — Evidence & Investigation
phase: Phase A Exit Gate
depends_on: [TASK-114B]
blocks: [TASK-114E]
---

# Tier 2 — Synthetic Failure Injection & Real Monitor Loop Pass

## Goal

Exercise Evidence Pack generation against failure modes that historical replay
(TASK-114C) can't cover well: partial/degraded collection, and the actual
settling-window/trigger logic in the monitor loop rather than a direct
`collect()` call. Historical replay proves the collectors produce good evidence
for known incidents; this tier proves the surrounding infrastructure (timing,
graceful degradation, error isolation) actually works.

## Scope

### In Scope

**A. Failure injection scenarios** — for each, construct or trigger the
condition, run evidence collection, and inspect the resulting pack:

- [ ] **Railway API unavailable / timeout** — simulate Railway being unreachable
      (e.g. point `RAILWAY_API_TOKEN` at an invalid value, or mock the client to
      raise a timeout) and confirm: deploy context and Railway-sourced logs are
      recorded as missing in `sections_missing` with an explicit reason, other
      collectors (metrics, related cases, config, LLM traces) still complete
      successfully, and `collection_status` reflects `PARTIAL` rather than the
      pack being silently dropped or marked `COMPLETE`
- [ ] **Disabled/missing critical operation** — construct a BugCase where a
      config value referenced by `ConfigEvidenceCollector` is missing or None;
      confirm graceful `getattr()`-with-default handling (per the existing
      pattern noted in Session 11 of the sprint log) rather than a collector
      crash that halts the whole pack
- [ ] **Broken/malformed config value** — similar to above but with a present-but-
      invalid value (wrong type, out of range) rather than missing; confirm this
      doesn't propagate a crash either
- [ ] **Worker/subsystem down signal** — construct system state input that shows
      a Celery worker or scheduler with restarts > 0 or deployment inactive, and
      confirm `subsystem_metrics` / `system_state` correctly reflect this as an
      unhealthy signal (this is the inverse of the all-healthy BUG-064 case —
      useful to confirm the collector doesn't just always report green)
- [ ] **Freshness-style alert** (per the briefing/narrative/article freshness
      detector design referenced in the sprint's design docs) — construct a
      BugCase with `alert_type` reflecting a freshness failure and confirm the
      Evidence Pack captures last-successful-output and expected-activity style
      signals if those are available to the collectors; if freshness detectors
      aren't yet wired to produce evidence-relevant fields, note this as a gap
      rather than forcing it

**B. Real monitor loop pass** (not a direct `collect()` call):

- [ ] Take one synthetic BugCase (can reuse one from the scenarios above) and run
      it through the actual monitor loop path: `get_cases_without_evidence()` →
      eligibility check → settling window → `_run_evidence_collection()`, per the
      wiring described in Session 14 of the sprint log (`bugops/monitor.py` or
      wherever that lives — confirm exact path during implementation)
- [ ] Confirm the settling window is respected (case is NOT collected immediately
      unless marked critical) and that a critical-severity case DOES bypass the
      settling window, per the sprint's documented behavior
- [ ] This is the one scenario in the entire gate review that should NOT bypass
      timing logic — let it run on real or accelerated clock time, don't
      monkey-patch collection to fire instantly, since the whole point is
      proving the wiring works, not just the collector logic

### Out of Scope
- Historical incident replay (TASK-114C)
- Modifying collector or monitor loop implementation — if a scenario reveals an
  actual bug, stop and document it rather than fixing it inline; this ticket is
  validation, not a bugfix ticket
- Production data or production Railway credentials

## Acceptance Criteria

- [ ] All 5 failure-injection scenarios executed with results recorded
- [ ] Railway-unavailable scenario specifically confirms graceful partial-pack
      handling — this directly satisfies original Phase A Exit Gate criterion
      "at least one partial Evidence Pack handled gracefully with explicit error
      record"
- [ ] Real monitor loop pass confirms settling window timing behavior, both the
      default-delay path and the critical-bypass path
- [ ] Truncation metadata verified correct when a log cap is reached (use the log
      collector's `BUGOPS_LOG_LINE_CAP` setting — construct a scenario with
      enough synthetic log volume to trigger truncation)
- [ ] Redaction verified — confirm `redactions_applied` count is accurate by
      constructing log content containing at least one of each pattern the
      `LogRedactor` handles (Mongo URIs, Bearer tokens, api_key, email, hex
      tokens) and checking the count matches
- [ ] Output is a single markdown report: `TASK-114D-SYNTHETIC-RESULTS.md`,
      one section per scenario, each stating pass/fail against what was expected
      and showing the relevant fields from the resulting Evidence Pack

## Notes for Implementing Agent

- If any scenario can't be cleanly constructed without modifying production code
  (e.g. the freshness detector scenario, if it genuinely isn't wired up yet),
  say so plainly in the report rather than forcing a workaround. A documented
  "this isn't testable yet, here's why" is a valid and useful outcome.
- Keep all synthetic data clearly fake — recognizable case IDs, summaries, etc.
  — so nothing here could be mistaken for a real incident later.
