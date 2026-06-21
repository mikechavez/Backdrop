---
id: TASK-114C
type: task
status: open
priority: high
parent_sprint: Sprint 021 — Evidence & Investigation
phase: Phase A Exit Gate
depends_on: [TASK-114B]
blocks: [TASK-114E]
---

# Tier 1 — Historical Incident Replay (BUG-064, BUG-084, BUG-073)

## Goal

Construct synthetic BugCases for three real, closed, documented incidents, run
them through the real `EvidenceCollector`, and produce a blind diagnosis from
each resulting Evidence Pack — written *before* comparing against the original
incident's documented root cause. This tests whether the Evidence Pack alone is
sufficient for a stranger to diagnose a known incident correctly.

This replaces the original Phase A Exit Gate's "wait for 3 real production
Evidence Packs" criterion with something that doesn't depend on production
breaking, and that can be scored against known-correct answers instead of
eyeballed for plausibility.

## Background — the three incidents

All three are closed/fixed and documented in tickets already shared with you in
this conversation (uploaded as markdown). Treat the documented resolution in
each as ground truth — do not re-verify against git history or production state.

### BUG-064 — Cost control failure / briefing generation halt
- Root subsystem: Briefing generation pipeline (Celery worker)
- Incident window: failure at `2026-04-13T00:00:10Z`, lasting 70+ minutes
- Soft limit: $0.25 (`LLM_DAILY_SOFT_LIMIT`); actual spend at failure: $0.2954
- Hard limit: $15.00 (default)
- Blocked operation: `briefing_generate`
- Healthy signals that should eliminate other subsystems (use these to construct
  `system_state` / `subsystem_metrics` for the synthetic case):
  - MongoDB reachable, 12ms latency
  - Redis reachable, 4ms latency
  - FastAPI healthy
  - Celery worker deployment active, 0 restarts in 24h
  - Celery scheduler deployment active, 0 restarts in 24h
  - No deployments in prior 24 hours
  - Article ingestion pipeline healthy
  - RSS fetch heartbeat healthy
- Ground truth reference: `docs/sprints/sprint-021/golden-investigation-bug-064.md`
  and `docs/sprints/sprint-021/design-artifacts/evidence-pack-bug064-schema-mapping.md`

### BUG-084 — Narrative summary fabrication
- Root subsystem: Narrative generation (`generate_narrative_summary()` in
  `optimized_anthropic.py`)
- Three source articles about Kraken's IPO filing produced a fabricated narrative
  titled "Kraken Faces Extortion Over Stolen Internal Data" — a completely
  invented security breach story with no basis in the source articles
- Root cause: prompt encouraged "synthesis" into a "cohesive narrative" even when
  articles shared only an entity, not a story; article text truncated to 300
  characters (insufficient grounding); wrong model used (Sonnet instead of Haiku,
  contradicting standardization)
- Narrative ObjectId: `68f102d6f791cb6cf711833c`
- Source article ObjectIds: `69dea2e61b80de5043c19775`, `69df1202b8ea0f0ffa9dfeb5`,
  `69dea94c2adcac6279c197a4`
- **Known limitation, flag this explicitly in your output**: BugOps' Evidence Pack
  sections (subsystem metrics, logs, deploy context, config, LLM traces, related
  cases) were not designed to capture "the LLM's output contradicts its input."
  This replay may legitimately fail or produce a weak diagnosis — that is a valid
  and useful finding about Evidence Pack coverage, not a bug in your harness. Do
  not force the Evidence Pack to contain something it structurally can't.

### BUG-073 — Articles missing fingerprints / deduplication broken
- Root subsystem: RSS ingestion pipeline (`db/operations/articles.py`)
- First observed: ~2 AM UTC, April 14, 2026
- Root cause: `create_or_update_articles()` inserted directly into MongoDB via
  `collection.insert_one()`, bypassing `ArticleService.create_article()` — the
  only code path that generates fingerprints. Result: 100% of April 14 inserts
  had `fingerprint: null`, breaking deduplication
- Related incidents (should plausibly surface via the related-case collector):
  BUG-070 (tier-1 filtering), BUG-071 (compressed system prompt), BUG-072 (LLM
  cache wiring) — these three fixes were explicitly noted as ineffective without
  working fingerprints
- This incident is a good test of the deploy-context and related-case collectors
  specifically, since it's a code-path regression rather than an infra failure

## Scope

### In Scope
- [ ] Build a small, reusable replay harness: given a structured incident
      definition (subsystem, timestamps, healthy/unhealthy signals, related case
      IDs), construct a valid synthetic `BugCaseCreate` per the schema in
      `bugops/models.py` lines 74-140, persist it to the local Mongo instance
      from TASK-114B, then call `EvidenceCollector.collect(bugcase)` per the
      entry point at `bugops/evidence/collector.py` lines 93-177
- [ ] Use this harness to replay all three incidents above
- [ ] For each resulting Evidence Pack: write a blind diagnosis BEFORE re-reading
      this ticket's "Root cause" sections above. The diagnosis should answer:
      "Based solely on what's in this Evidence Pack, what happened and why?"
      Output this as a separate markdown block per incident, clearly labeled
      `BLIND DIAGNOSIS — BUG-0XX` and timestamped, so it's verifiably written
      before the comparison step
- [ ] Then compare each blind diagnosis against the documented ground truth above.
      Score each as: MATCH (diagnosis correctly identifies root cause), PARTIAL
      (correct subsystem, wrong specific cause), or MISS (diagnosis is wrong or
      Evidence Pack lacked sufficient signal)
- [ ] For BUG-084 specifically: explicitly note in your output which Evidence
      Pack sections were searched for fabrication-relevant signal and confirm
      none exist — don't manufacture a false MATCH by reasoning outside the pack

### Out of Scope
- Modifying EvidenceCollector or any collector implementation
- Modifying the EvidencePack or BugCase schemas
- Synthetic failure injection (worker kills, broken configs, etc.) — that's TASK-114D
- Production data of any kind

## Acceptance Criteria

- [ ] Three Evidence Packs successfully generated and persisted to the local
      Mongo instance, one per incident
- [ ] Three blind diagnoses written before ground-truth comparison, each clearly
      timestamped/ordered to prove the blind step happened first
- [ ] Each diagnosis scored MATCH / PARTIAL / MISS against documented ground truth
- [ ] BUG-084's likely coverage gap is explicitly named, not glossed over
- [ ] No evidence reference ID collisions across any of the three packs
      (verify via `evidence_references` dict and allocator's `current_count()`)
- [ ] Per-section `collected_at` timestamps present on all collected sections
      for all three packs
- [ ] Output is a single markdown report: `TASK-114C-REPLAY-RESULTS.md`

## Notes for Implementing Agent

- Don't try to make BUG-064's replay "easy" by over-fitting the synthetic
  BugCase to exactly what the golden investigation already says — construct it
  from the raw facts (timestamps, costs, healthy signals) and let the collector
  do its job. The point is testing the collector, not confirming what you
  already typed in.
- If constructing a valid `BugCaseCreate` for any of these three reveals a
  required field with no obvious value (e.g. no natural `dedupe_key` for a
  historical incident), pick a reasonable synthetic value and note the
  assumption in your output — don't block on it.
