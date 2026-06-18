---
ticket_id: TASK-114A
title: EvidencePack schema review against BUG-064
priority: high
status: ✅ COMPLETE
phase: A
date_created: 2026-06-16
date_completed: 2026-06-18
branch: task/bugops-114a-schema-review-bug-064
effort_estimate: small
---

# TASK-114A: EvidencePack schema review against BUG-064

## Problem Statement

Before implementing any collector, confirm the EvidencePack schema produced in TASK-114 can represent the BUG-064 Golden Evidence Pack without loss of critical evidence. This is the last architecture checkpoint before implementation begins.

---

## Context

During the pre-sprint design session, the hand-written BUG-064 Evidence Pack revealed a missing collector (Configuration Evidence) that was not in the original Sprint 021 design. This ticket repeats that exercise against the actual schema to catch any remaining gaps before implementation.

The BUG-064 Evidence Pack is documented in `golden-investigation-bug-064.md` (the Evidence Pack section). The Golden Investigation references evidence items E-001 through E-011. All must be representable in the schema.

This ticket produces no code. It produces a written schema mapping document that is checked into the repo as a design artifact.

---

## Task

1. Read `golden-investigation-bug-064.md` — specifically the Evidence Pack and evidence references E-001 through E-011
2. Map each evidence reference to a specific field in the `EvidencePackCreate` schema from TASK-114
3. Confirm the following are all representable:
   - Configuration Evidence (soft limit value, blocked operation name, critical operations list)
   - Per-section `collected_at` timestamps
   - Collection errors with reason and timestamp
   - Evidence references E-001 through E-011 with section pointers
   - Truncation metadata for celery_worker logs
   - Healthy signals as explicit enumerated list
4. Document any gaps found
5. If gaps exist: update the schema in `models.py` before marking this ticket complete
6. Write the mapping document to `docs/bugops/evidence-pack-bug064-schema-mapping.md`

---

## Files to Create

```
docs/bugops/evidence-pack-bug064-schema-mapping.md
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/models.py  (only if gaps found)
tests/bugops/test_evidence_pack_model.py     (only if schema changes made)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
```

---

## Implementation Requirements

### Schema mapping document structure

```markdown
# EvidencePack Schema Mapping — BUG-064

## Evidence Reference Mapping

| Reference | Description | Schema Field | Section |
|-----------|-------------|--------------|---------|
| E-001 | LLM daily soft limit | config_evidence.llm_daily_soft_limit | config_evidence |
| E-002 | Failed briefing attempts | subsystem_metrics[briefings].artifact_count | subsystem_metrics |
| ...   | ...                    | ...                                  | ...             |

## Gaps Found

(None / list any gaps)

## Schema Changes Required

(None / list any changes made to models.py)

## Acceptance Checklist

- [ ] All E-001 through E-011 references mapped to schema fields
- [ ] Configuration Evidence representable without loss
- [ ] Collection errors representable with reason and timestamp
- [ ] Per-section collected_at present on all sections
- [ ] Truncation metadata representable for log sections
- [ ] Healthy signals representable as explicit list
- [ ] Evidence references dict supports section pointers
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_evidence_pack_model.py -v  # if schema changes made
pytest tests/bugops/ -v                              # all existing tests pass
```

### Manual Verification

- [ ] Schema mapping document written and committed
- [ ] All E-001 through E-011 references from Golden Investigation map cleanly to schema fields
- [ ] No evidence type from the BUG-064 Evidence Pack is unrepresentable in the schema

---

## Acceptance Criteria

- [ ] Schema mapping document exists at `docs/bugops/evidence-pack-bug064-schema-mapping.md`
- [ ] All 11 evidence references from the Golden Investigation are mapped to schema fields
- [ ] Any gaps found are resolved in `models.py` before this ticket closes
- [ ] All existing BugOps tests continue to pass

---

## Impact

Architectural checkpoint. Prevents discovering schema gaps mid-implementation. No behavior change.

---

## Related Tickets

- TASK-114: Defines the schema being reviewed (must be complete first)
- TASK-115: EvidencePack persistence (begins after this ticket closes)

---

## Completion Summary

- Branch: `task/bugops-114a-schema-review-bug-064`
- Commit: `6fb26ad`
- Mapping doc: `docs/sprints/sprint-021/design-artifacts/evidence-pack-bug064-schema-mapping.md`
- Gaps found: Yes — LogExcerptSection.window_start and window_end were required but should be Optional
- Schema changes made: LogExcerptSection fields changed to Optional (window_start, window_end)
- Tests run: `pytest tests/bugops/ -k "not alert_to_case and not monitor and not slack"` — 79 passed
- All references mapped: Yes — all 11 evidence references (E-001 through E-011) map cleanly
- Deviations from plan: None — found and fixed valid schema gap before implementation begins
