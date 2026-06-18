---
ticket_id: TASK-118
title: Collect related BugCases
priority: medium
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-118-related-bugcase-collector
effort_estimate: small
---

# TASK-118: Collect related BugCases

## Problem Statement

The Evidence Pack has no collector for related BugCases. Historical incident patterns are useful investigation context — knowing whether the same subsystem has failed before, and how often, informs hypothesis confidence and fix area identification.

---

## Context

Related BugCases share subsystems with the current BugCase, within a 7-day lookback window. This is deterministic — no LLM, no Railway API.

A BugCase is related if:
- Its `root_subsystem` OR any `affected_subsystems` value overlaps with the current case's `root_subsystem`, `blast_radius`, or `affected_subsystems`
- Created within 7 days of the current case's `first_seen_at`
- Is not the current BugCase itself

Store at most 10 related cases, sorted by `first_seen_at` descending (most recent first).

Use `EvidenceReferenceAllocator` for evidence reference IDs — call `ref_allocator.next_ref()`. Do not hardcode.

Can run in parallel with TASK-117, TASK-119, and TASK-121 — no dependencies on those tickets.

---

## Task

1. Create `RelatedCaseCollector` at `bugops/evidence/collectors/related_cases.py`
2. Add `get_related_cases()` store method to `BugOpsStore`
3. Register collector with `EvidenceCollector`
4. Write unit tests

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/collectors/related_cases.py
tests/bugops/test_related_case_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/store.py               (add get_related_cases)
src/crypto_news_aggregator/bugops/evidence/collector.py  (register collector)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/evidence/base.py
```

---

## Implementation Requirements

### Store method to add

```python
async def get_related_cases(
    self,
    bugcase_id: str,
    subsystems: list[str],
    lookback_days: int = 7,
    limit: int = 10,
) -> list[BugCase]:
    """
    Find BugCases sharing subsystems with the current case.
    
    Query: cases where root_subsystem OR any value in affected_subsystems
    is in the provided subsystems list, AND first_seen_at >= (now - lookback_days),
    AND case_id != bugcase_id.
    
    Returns up to limit cases sorted by first_seen_at descending.
    """
```

### RelatedCaseCollector

Implements `EvidenceCollectorBase`. `collector_name = "related_cases"`.

```python
async def collect(
    self,
    bugcase: BugCase,
    pack_id: str,
    store: BugOpsStore,
    ref_allocator: EvidenceReferenceAllocator,
) -> None:
    subsystems = list(set(
        ([bugcase.root_subsystem] if bugcase.root_subsystem else []) +
        (bugcase.blast_radius or []) +
        (bugcase.affected_subsystems or [])
    ))
    
    related = await store.get_related_cases(
        bugcase_id=bugcase.case_id,
        subsystems=subsystems,
        lookback_days=7,
        limit=10,
    )
    
    related_dicts = [
        {
            "case_id": c.case_id,
            "root_subsystem": c.root_subsystem,
            "severity": c.severity,
            "status": c.status,
            "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
            "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
            "title": c.title,
        }
        for c in related
    ]
    
    section_data = {
        "related_cases": related_dicts,
        "related_cases_collected_at": datetime.utcnow(),
    }
    
    if related:
        ref_id = ref_allocator.next_ref()
        section_data["evidence_references"] = {
            ref_id: {
                "description": f"{len(related)} related BugCases sharing subsystems in past 7 days",
                "section": "related_cases",
            }
        }
    
    await store.update_evidence_pack_section(pack_id, section_data)
```

Note: when `related` is empty, write an empty list and `related_cases_collected_at` — do not skip the section. An empty related cases section is itself evidence (no prior incidents for this subsystem).

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_related_case_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] Queries by `root_subsystem` overlap with current case subsystems
- [ ] Queries by `affected_subsystems` overlap
- [ ] Excludes current BugCase by `case_id`
- [ ] Respects 7-day lookback window
- [ ] Returns at most 10 results
- [ ] Sorts results by `first_seen_at` descending
- [ ] Handles zero related cases — writes empty list and timestamp, does not raise
- [ ] Adds evidence reference when related cases found
- [ ] Does NOT add evidence reference when no related cases (empty section is fine)
- [ ] Writes `related_cases_collected_at` timestamp
- [ ] Uses `ref_allocator.next_ref()` — does not hardcode reference IDs

---

## Acceptance Criteria

- [ ] `RelatedCaseCollector` implemented and registered with `EvidenceCollector`
- [ ] `get_related_cases()` store method added and tested
- [ ] Zero related cases handled gracefully — section written with empty list, not omitted
- [ ] Evidence reference added only when related cases found
- [ ] Uses `ref_allocator` for reference IDs
- [ ] All tests pass, no regressions

---

## Related Tickets

- TASK-116: Framework (must be complete first)
- TASK-123: Monitor wiring (depends on all collectors)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Deviations from plan:
