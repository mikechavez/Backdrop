---
ticket_id: TASK-116
title: Implement EvidenceCollector framework
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-116-evidence-collector-framework
effort_estimate: medium
---

# TASK-116: Implement EvidenceCollector framework

## Problem Statement

There is no EvidenceCollector class to orchestrate evidence collection for a BugCase. Individual collector tickets (TASK-117 through TASK-122) need a framework to plug into — the framework must exist first.

---

## Context

EvidenceCollector is an extension seam (see architecture doc). Its interface contract is stable; implementations may change. The framework handles:
- Eligibility checking (is this BugCase ready for evidence collection?)
- Settling window logic (wait N minutes after `first_seen_at`, or collect immediately for Critical)
- Evidence Pack creation and lifecycle
- Running each collector independently (one failure does not halt others)
- Marking the pack complete when all collectors have run
- Per-collector error recording in `collection_errors`

Individual collectors (metrics, logs, deploy context, etc.) are registered with EvidenceCollector and called in sequence. Each collector is responsible for writing its own section to the Evidence Pack via `store.update_evidence_pack_section()`.

The settling window default is `BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES=10`. Critical BugCases collect immediately. Evidence collection still runs if a BugCase resolves before the settling window elapses.

---

## Task

1. Create `EvidenceCollector` class at `bugops/evidence/collector.py`
2. Create `EvidenceCollectorBase` protocol at `bugops/evidence/base.py`
3. Create `bugops/evidence/__init__.py`
4. Wire no actual collectors yet — framework only with stub collector list
5. Write unit tests for framework logic

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/__init__.py
src/crypto_news_aggregator/bugops/evidence/base.py
src/crypto_news_aggregator/bugops/evidence/collector.py
tests/bugops/test_evidence_collector.py
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/monitor.py   (wired in TASK-123)
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/models.py
```

---

## Implementation Requirements

### EvidenceCollectorBase protocol

```python
# bugops/evidence/base.py
from typing import Protocol
from ..models import EvidencePackCreate
from ..store import BugOpsStore

class EvidenceCollectorBase(Protocol):
    """Protocol for individual evidence collectors."""
    
    collector_name: str  # e.g., "metrics", "logs", "deploy_context"
    
    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: "EvidenceReferenceAllocator",
    ) -> None:
        """
        Collect evidence and write section to Evidence Pack via store.
        Must call store.update_evidence_pack_section() with collected data.
        Use ref_allocator.next_ref() to get globally unique evidence reference IDs.
        Must NOT raise — catch exceptions internally and record in collection_errors.
        """
        ...
```

### EvidenceCollector class

```python
# bugops/evidence/collector.py

class EvidenceCollector:
    """
    Orchestrates evidence collection for a BugCase.
    Creates an Evidence Pack, runs all registered collectors,
    and marks the pack complete.
    """
    
    def __init__(self, store: BugOpsStore, settings):
        self.store = store
        self.settings = settings
        self.collectors: list[EvidenceCollectorBase] = []
        # Collectors registered by TASK-117 through TASK-122
    
    def register_collector(self, collector: EvidenceCollectorBase) -> None:
        """Register a collector. Called during monitor initialization."""
        self.collectors.append(collector)
    
    async def is_eligible(self, bugcase: BugCase) -> bool:
        """
        Return True if this BugCase is eligible for evidence collection.
        
        Eligible when:
        - Status is NOT manually closed (CaseStatus.CLOSED)
        - No Evidence Pack already attached (store.get_evidence_pack_for_case returns None)
        - Settling window has elapsed since first_seen_at OR severity is Critical
        
        Resolved BugCases ARE eligible if they have no Evidence Pack and the
        settling window has elapsed. Short-lived failures that auto-resolved
        before collection still need Evidence Packs for the operational corpus.
        Only CaseStatus.CLOSED (operator manually closed) excludes a case.
        """
        ...
    
    async def collect(self, bugcase: BugCase) -> Optional[EvidencePack]:
        """
        Main entry point. Creates Evidence Pack, runs all registered collectors,
        marks complete. Returns completed EvidencePack or None if not eligible.
        
        Rules:
        - Check eligibility first. Return None if not eligible.
        - Create Evidence Pack immediately on eligibility confirmation.
        - Create one EvidenceReferenceAllocator per collection cycle — passed to all collectors.
        - Run each collector in sequence inside independent try/except.
        - Record CollectionError for any collector that raises.
        - Call store.mark_evidence_pack_complete() after all collectors run.
        - Never raise — log errors and return partial pack.
        """
        ...
    
    def _is_settling_window_elapsed(self, bugcase: BugCase) -> bool:
        """
        Return True if BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES have elapsed
        since bugcase.first_seen_at, or if severity is Critical.
        """
        ...
    
    def _generate_pack_id(self, bugcase_id: str) -> str:
        """Generate unique pack_id: ep_{bugcase_id}_{unix_timestamp}"""
        ...
```

### Collector isolation requirement

Each collector runs inside an independent try/except block:

```python
ref_allocator = EvidenceReferenceAllocator()

for collector in self.collectors:
    try:
        await collector.collect(bugcase, pack_id, self.store, ref_allocator)
        sections_collected.append(collector.collector_name)
    except Exception as e:
        error = CollectionError(
            source=collector.collector_name,
            error_type=type(e).__name__,
            error_message=str(e)[:200],
        )
        collection_errors.append(error)
        # Record error to Evidence Pack immediately
        await self.store.update_evidence_pack_section(
            pack_id,
            {"collection_errors": existing_errors + [error.model_dump()]}
        )
        logger.error(f"EvidenceCollector: {collector.collector_name} failed: {e}")
```

### Settling window logic

```python
from datetime import datetime, timedelta

settling_minutes = self.settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES

if bugcase.severity == AlertSeverity.CRITICAL:
    return True  # Collect immediately for Critical

if bugcase.first_seen_at is None:
    return False  # Cannot determine elapsed time

elapsed = datetime.utcnow() - bugcase.first_seen_at
return elapsed >= timedelta(minutes=settling_minutes)
```

### Evidence Pack initial creation

When `collect()` is called and eligibility is confirmed, create the Evidence Pack immediately with snapshot data from the BugCase before running any collectors:

```python
pack_create = EvidencePackCreate(
    pack_id=self._generate_pack_id(bugcase.case_id),
    bugcase_id=bugcase.case_id,
    incident_first_seen_at=bugcase.first_seen_at,
    incident_last_seen_at=bugcase.last_seen_at,
    root_subsystem=bugcase.root_subsystem,
    severity=bugcase.severity,
    blast_radius=bugcase.blast_radius,
    primary_signal=bugcase.summary,
)
pack = await self.store.create_evidence_pack(pack_create)
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_evidence_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] `is_eligible` returns False for manually closed BugCase (`CaseStatus.CLOSED`)
- [ ] `is_eligible` returns True for resolved BugCase (`CaseStatus.RESOLVED`) when no Evidence Pack exists and settling window elapsed
- [ ] `is_eligible` returns False when Evidence Pack already exists for case
- [ ] `is_eligible` returns False when settling window has not elapsed (non-Critical)
- [ ] `is_eligible` returns True when settling window has elapsed
- [ ] `is_eligible` returns True immediately for Critical severity regardless of elapsed time
- [ ] `collect` creates Evidence Pack before running collectors
- [ ] `collect` runs all registered collectors
- [ ] `collect` records CollectionError when a collector raises, continues to next collector
- [ ] `collect` marks pack complete after all collectors run
- [ ] `collect` returns partial pack (not None) when some collectors fail
- [ ] `collect` returns None when BugCase is not eligible
- [ ] Collector with no registered collectors completes with empty sections

---

## Acceptance Criteria

- [ ] `EvidenceCollectorBase` protocol updated to include `ref_allocator` parameter
- [ ] `EvidenceReferenceAllocator` passed to each collector — no two collectors receive the same reference ID
- [ ] Resolved BugCases are eligible when no Evidence Pack exists and settling window elapsed
- [ ] Manually closed BugCases (`CaseStatus.CLOSED`) are never eligible
- [ ] `EvidenceCollector` class implemented at `bugops/evidence/collector.py`
- [ ] Settling window logic correct for both Critical and non-Critical cases
- [ ] Each collector runs in independent try/except — one failure does not halt others
- [ ] `CollectionError` recorded for each failed collector
- [ ] Evidence Pack created at start of collection, marked complete at end
- [ ] Framework works with zero registered collectors (no crash)
- [ ] All framework tests pass
- [ ] All existing BugOps tests continue to pass

---

## Impact

Unblocks TASK-117 through TASK-122 (all collectors). No behavior change to existing system — not yet wired into monitor.

---

## Related Tickets

- TASK-115: Persistence (must be complete first)
- TASK-117, TASK-118, TASK-119, TASK-120, TASK-121, TASK-122: Collectors (depend on this)
- TASK-123: Monitor wiring (depends on all collectors)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Deviations from plan:
