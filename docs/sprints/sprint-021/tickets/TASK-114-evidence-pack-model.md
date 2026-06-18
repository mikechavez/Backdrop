---
ticket_id: TASK-114
title: Define EvidencePack model and schema
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-114-evidence-pack-model
effort_estimate: medium
---

# TASK-114: Define EvidencePack model and schema

## Problem Statement

BugOps has no model for Evidence Packs. Before any collector can be built, the schema must exist and be validated against the BUG-064 Golden Incident to confirm it can represent all evidence types without loss.

---

## Context

Evidence Packs are the primary durable artifact of Sprint 021. Every subsequent ticket in Phase A produces a collector that writes into an Evidence Pack. The schema must be locked before any collector is implemented.

Key design decisions already made (see `20-sprint-021-evidence-investigation-interface-v2.md`):
- Evidence Packs may be partial but must never be ambiguous — missing sources are recorded explicitly
- Each section has its own `collected_at` timestamp
- Evidence references (E-001, E-002...) index into the pack for Investigation use
- Truncation metadata is recorded per section
- `collection_status` is either `complete` or `partial`

The Golden Investigation for BUG-064 (`golden-investigation-bug-064.md`) uses evidence references E-001 through E-011. The schema must support this indexing pattern.

Follow existing model conventions in `src/crypto_news_aggregator/bugops/models.py`:
- Create model (`EvidencePackCreate`) + Persisted model (`EvidencePack`) pattern
- Pydantic v2 with `@field_validator` for enum-validated fields
- `id: Optional[str] = Field(default=None, alias="_id")` on persisted model
- `class Config: populate_by_name = True` on persisted model
- `datetime = Field(default_factory=datetime.utcnow)` for auto timestamps
- `Optional[T] = None` for nullable fields
- `Field(default_factory=list)` for list fields
- `Field(default_factory=dict)` for dict fields

---

## Task

1. Add `EvidencePackCreate` and `EvidencePack` models to `models.py`
2. Add `EvidencePackStatus` enum to `models.py`
3. Add `CollectionError` nested model to `models.py`
4. Add `LogExcerptSection` nested model to `models.py`
5. Add `SectionMetrics` nested model to `models.py`
6. Write unit tests for all new models

---

## Files to Create

```
tests/bugops/test_evidence_pack_model.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/models.py
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### Enums to add

```python
class EvidencePackStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
```

### Nested models to add

```python
class CollectionError(BaseModel):
    """Records a failure to collect from one evidence source."""
    source: str                          # e.g., "railway_logs", "deploy_context"
    error_type: str                      # Exception class name
    error_message: str                   # Truncated to 200 chars
    attempted_at: datetime = Field(default_factory=datetime.utcnow)

class LogExcerptSection(BaseModel):
    """Log excerpt metadata and content for one service."""
    service: str                         # "fastapi" | "celery_worker" | "celery_scheduler"
    lines_fetched: int
    lines_stored: int
    truncated: bool
    window_start: datetime
    window_end: datetime
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    excerpts: list[str] = Field(default_factory=list)  # Redacted log lines

class SectionMetrics(BaseModel):
    """Freshness and count metrics for one subsystem."""
    subsystem: str                       # BugOpsSubsystem value
    last_artifact_at: Optional[datetime] = None
    artifact_count: Optional[int] = None
    freshness_indicator: Optional[str] = None  # human-readable e.g. "47 minutes ago"
```

### EvidencePackCreate fields

```python
class EvidencePackCreate(BaseModel):
    # Identifiers
    pack_id: str                         # Unique ID e.g. "ep_<case_id>_<timestamp>"
    bugcase_id: str                      # Links to BugCase.case_id

    # Collection metadata
    collection_started_at: datetime = Field(default_factory=datetime.utcnow)
    collection_completed_at: Optional[datetime] = None
    collection_duration_ms: Optional[int] = None
    collection_status: EvidencePackStatus = EvidencePackStatus.PARTIAL

    # Incident context (snapshot at collection time)
    incident_first_seen_at: Optional[datetime] = None
    incident_last_seen_at: Optional[datetime] = None
    root_subsystem: Optional[str] = None   # BugOpsSubsystem value
    severity: Optional[str] = None         # AlertSeverity value
    primary_signal: Optional[str] = None
    blast_radius: list[str] = Field(default_factory=list)

    # Evidence sections — each Optional to support partial packs
    subsystem_metrics: list[SectionMetrics] = Field(default_factory=list)
    subsystem_metrics_collected_at: Optional[datetime] = None

    system_state: dict = Field(default_factory=dict)
    # Shape: {"mongodb": {"status": "ok", "latency_ms": 12}, "redis": {...},
    #         "fastapi": {...}, "pipeline": {...},
    #         "celery_worker": {...}, "celery_scheduler": {...}}
    system_state_collected_at: Optional[datetime] = None

    healthy_signals: list[str] = Field(default_factory=list)
    # Plain strings: ["MongoDB reachable (12ms)", "Celery worker deployment active"]

    related_cases: list[dict] = Field(default_factory=list)
    # Each dict: {"case_id": str, "root_subsystem": str, "severity": str,
    #             "status": str, "first_seen_at": datetime, "last_seen_at": datetime}
    related_cases_collected_at: Optional[datetime] = None

    deploy_context: list[dict] = Field(default_factory=list)
    # Each dict: {"service": str, "deployment_id": str, "status": str,
    #             "created_at": datetime, "updated_at": datetime}
    deploy_context_collected_at: Optional[datetime] = None

    config_evidence: dict = Field(default_factory=dict)
    # Shape: {"llm_daily_soft_limit": float, "llm_daily_hard_limit": float,
    #         "critical_operations": list[str], "bugops_thresholds": dict}
    config_evidence_collected_at: Optional[datetime] = None

    log_excerpts: list[LogExcerptSection] = Field(default_factory=list)
    # One LogExcerptSection per service

    # Evidence reference index
    # Maps reference ID (e.g. "E-001") to a description and section pointer
    evidence_references: dict = Field(default_factory=dict)
    # Shape: {"E-001": {"description": "Cost controls daily_soft_limit",
    #                   "section": "config_evidence",
    #                   "field": "llm_daily_soft_limit"}}

    # Collection statistics
    sections_collected: list[str] = Field(default_factory=list)
    sections_missing: list[dict] = Field(default_factory=list)
    # Each dict: {"section": str, "reason": str, "attempted_at": datetime}
    redactions_applied: int = 0
    truncation_applied: list[str] = Field(default_factory=list)
    total_chars: int = 0

    # Collection errors
    collection_errors: list[CollectionError] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### EvidencePack (persisted)

```python
class EvidencePack(EvidencePackCreate):
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True
```

### Evidence reference pattern

Evidence references use the format `E-NNN` (E-001, E-002...). They are allocated by a central `EvidenceReferenceAllocator` on the `EvidencePack` to prevent collisions across collectors.

**Problem without central allocation:** Multiple collectors independently starting from E-001 would collide. MetricsCollector writes E-001, ConfigEvidenceCollector also writes E-001 — last writer wins and evidence is lost.

**Solution:** `EvidencePackCreate` includes a `_next_ref_index: int = 1` field (not persisted) or the allocator is passed to each collector. The recommended approach is a thread-safe allocator passed through `EvidenceCollector.collect()`.

Add `EvidenceReferenceAllocator` as a simple class:

```python
class EvidenceReferenceAllocator:
    """
    Central allocator for evidence reference IDs.
    Prevents collision across collectors.
    One instance per Evidence Pack collection cycle.
    """
    def __init__(self):
        self._counter = 0
    
    def next_ref(self) -> str:
        """Return next reference ID: E-001, E-002, ..."""
        self._counter += 1
        return f"E-{self._counter:03d}"
    
    def current_count(self) -> int:
        return self._counter
```

`EvidenceCollector.collect()` creates one `EvidenceReferenceAllocator` per collection cycle and passes it to each collector's `collect()` method. The `EvidenceCollectorBase` protocol signature must include the allocator parameter.

Update `EvidenceCollectorBase.collect()` signature:
```python
async def collect(
    self,
    bugcase: BugCase,
    pack_id: str,
    store: BugOpsStore,
    ref_allocator: EvidenceReferenceAllocator,
) -> None:
    ...
```

Each collector calls `ref_allocator.next_ref()` to get a globally unique reference ID. Example:
```python
# In MetricsCollector:
ref_id = ref_allocator.next_ref()  # Returns "E-001" on first call globally
evidence_references[ref_id] = {
    "description": "Last article created_at",
    "section": "subsystem_metrics",
    "subsystem": "articles"
}
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_evidence_pack_model.py -v
pytest tests/bugops/ -v  # all existing tests must still pass
```

### Required Test Coverage

- [ ] `EvidencePackCreate` instantiates with all required fields
- [ ] `EvidencePackCreate` instantiates with only required fields (all optional fields default correctly)
- [ ] `EvidencePack` adds `id`/`_id` mapping correctly (`populate_by_name=True`)
- [ ] `EvidencePackStatus` enum values are correct strings
- [ ] `CollectionError` instantiates and auto-sets `attempted_at`
- [ ] `LogExcerptSection` instantiates with truncated=False for short logs
- [ ] `SectionMetrics` instantiates with all optional fields as None
- [ ] `collection_status` defaults to `PARTIAL`
- [ ] `sections_missing` records reason and attempted_at correctly
- [ ] `evidence_references` dict accepts E-NNN keys with section pointers
- [ ] `model_dump(by_alias=False)` produces flat dict suitable for MongoDB insert
- [ ] `_normalize_mongo_doc` pattern works with `EvidencePack` (ObjectId → str)

---

## Acceptance Criteria

- [ ] `EvidencePackCreate` and `EvidencePack` added to `models.py` following existing conventions
- [ ] All nested models (`CollectionError`, `LogExcerptSection`, `SectionMetrics`) defined
- [ ] `EvidencePackStatus` enum defined
- [ ] `EvidenceReferenceAllocator` defined and tested — `next_ref()` returns E-001, E-002... sequentially with no reuse
- [ ] `evidence_references` dict supports E-NNN keys with section pointers
- [ ] `sections_missing` records explicit reason and timestamp per missing section
- [ ] All new model tests pass
- [ ] All existing BugOps tests continue to pass (no regressions)

---

## Impact

Unlocks all subsequent Phase A tickets. No behavior change to existing system — models only.

---

## Related Tickets

- TASK-114A: Schema review against BUG-064 (immediate next)
- TASK-115: EvidencePack persistence (depends on this)

---

## Completion Summary

- **Branch:** task/bugops-114-evidence-pack-model
- **Commit:** d2109c8
- **Changes made:**
  - Added EvidencePackStatus enum (COMPLETE, PARTIAL)
  - Added nested models: CollectionError, LogExcerptSection, SectionMetrics
  - Added LLMTraceRecord and LLMTraceSummary (first-class LLM evidence)
  - Added EvidenceReferenceAllocator (E-001, E-002... generator, no reuse)
  - Added EvidencePackCreate and EvidencePack models with full field structure
  - Added validators for root_subsystem, severity, blast_radius against BugOpsSubsystem and AlertSeverity
- **Tests run:** pytest src/tests/bugops/test_evidence_pack_model.py (34 tests, all passing)
- **Regression tests:** pytest src/tests/bugops/ (214 total, 180 existing + 34 new, all passing)
- **Deviations from plan:** 
  - Added LLMTraceSummary as typed nested model instead of permissive dict to lock schema for BUG-064 cost-control diagnosis
  - Clarified allocator is tested but integration deferred to TASK-116 framework
  - Documented 5 critical TASK-114A lockdown points in memory for production compatibility verification
