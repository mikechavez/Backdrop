---
ticket_id: TASK-115
title: Implement EvidencePack persistence
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-115-evidence-pack-persistence
effort_estimate: small
---

# TASK-115: Implement EvidencePack persistence

## Problem Statement

The EvidencePack model exists but there is no MongoDB collection, indexes, or store methods to persist and retrieve Evidence Packs.

---

## Context

Follow existing BugOpsStore patterns from `store.py`:
- `_normalize_mongo_doc()` for ObjectId → str conversion before Pydantic hydration
- `model_dump(by_alias=False, exclude_none=False)` for MongoDB insertion
- `AsyncMock` pattern in tests for collection mocking

New collection: `evidence_packs`. Retention: permanent for record and metadata, 90 days for raw evidence data (retention enforcement deferred — just establish the collection and document the policy).

Evidence Packs are write-once with targeted updates. Once created, individual sections are added as collectors complete. The store must support partial writes (section by section) not just full document replacement.

---

## Task

1. Add `evidence_packs` collection to `BugOpsStore.__init__`
2. Add store methods for Evidence Pack operations
3. Add MongoDB indexes for `evidence_packs` collection
4. Add new config keys to `core/config.py`
5. Write unit tests for all new store methods

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/core/config.py
tests/bugops/test_evidence_pack_model.py   (add persistence tests)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/models.py  (schema locked after TASK-114A)
src/crypto_news_aggregator/bugops/monitor.py
```

---

## Implementation Requirements

### Config keys to add

Add to `core/config.py` in the BugOps section:

```python
BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES: int = 10
BUGOPS_LOG_WINDOW_MINUTES: int = 10
BUGOPS_LOG_LINE_CAP: int = 200
BUGOPS_EVIDENCE_MAX_TOTAL_CHARS: int = 60000
BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS: int = 12000
RAILWAY_API_TOKEN: str = ""
```

### Store methods to add

```python
async def create_evidence_pack(self, pack: EvidencePackCreate) -> EvidencePack:
    """Insert a new Evidence Pack. Returns persisted EvidencePack with id."""

async def get_evidence_pack(self, pack_id: str) -> Optional[EvidencePack]:
    """Retrieve an Evidence Pack by pack_id."""

async def get_evidence_pack_for_case(self, bugcase_id: str) -> Optional[EvidencePack]:
    """Retrieve the Evidence Pack attached to a BugCase. Returns None if not yet collected."""

async def update_evidence_pack_section(
    self,
    pack_id: str,
    section_data: dict,
    updated_at: Optional[datetime] = None
) -> Optional[EvidencePack]:
    """
    Update one or more fields on an existing Evidence Pack.
    Used by collectors to write their section after collection completes.
    section_data is a flat dict of field names to values.
    Sets updated_at to now if not provided.
    Returns updated EvidencePack.
    
    MERGE SEMANTICS FOR evidence_references:
    The evidence_references field must be merged, not overwritten.
    Multiple collectors each write their own references to this field.
    If section_data contains evidence_references, use MongoDB $set on individual
    keys rather than replacing the entire dict. Existing references must be preserved.
    
    Implementation: use MongoDB dot-notation to set individual reference keys:
      {"$set": {"evidence_references.E-003": {...}, "evidence_references.E-004": {...}}}
    
    Do NOT use:
      {"$set": {"evidence_references": {"E-003": {...}, "E-004": {...}}}}
    The second form replaces the entire dict, destroying references from prior collectors.
    
    All other fields in section_data are set directly (last writer wins).
    Only evidence_references requires merge semantics.
    """

async def mark_evidence_pack_complete(
    self,
    pack_id: str,
    collection_completed_at: datetime,
    collection_duration_ms: int,
    sections_collected: list[str],
    total_chars: int
) -> Optional[EvidencePack]:
    """
    Mark an Evidence Pack as complete after all collectors have run.
    Sets collection_status to:
      COMPLETE if collection_errors is empty AND sections_missing is empty
      PARTIAL if collection_errors is non-empty OR sections_missing is non-empty
    """
```

### MongoDB indexes for evidence_packs

```python
# In store initialization or an index setup method:
await self.evidence_packs_collection.create_index("pack_id", unique=True)
await self.evidence_packs_collection.create_index("bugcase_id")
await self.evidence_packs_collection.create_index("collection_status")
await self.evidence_packs_collection.create_index("created_at")
```

### Collection initialization

```python
# In BugOpsStore.__init__, add alongside existing collections:
self.evidence_packs_collection = db["evidence_packs"]
```

### pack_id generation pattern

```python
# Generate pack_id in EvidenceCollector (not store):
pack_id = f"ep_{bugcase_id}_{int(datetime.utcnow().timestamp())}"
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_evidence_pack_model.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] `create_evidence_pack` inserts document and returns `EvidencePack` with string id
- [ ] `create_evidence_pack` normalizes ObjectId to string (follows `_normalize_mongo_doc` pattern)
- [ ] `get_evidence_pack` returns `None` when not found
- [ ] `get_evidence_pack_for_case` queries by `bugcase_id` correctly
- [ ] `get_evidence_pack_for_case` returns `None` when no pack exists for case
- [ ] `update_evidence_pack_section` updates specified fields only (not full replacement)
- [ ] `update_evidence_pack_section` sets `updated_at` automatically
- [ ] `update_evidence_pack_section` merges `evidence_references` — writes E-001/E-002, then writes E-003/E-004, all four references present after both writes
- [ ] `update_evidence_pack_section` does NOT overwrite prior `evidence_references` entries when new ones are added
- [ ] `mark_evidence_pack_complete` sets `collection_status` to COMPLETE when no errors AND no missing sections
- [ ] `mark_evidence_pack_complete` sets `collection_status` to PARTIAL when `collection_errors` is non-empty
- [ ] `mark_evidence_pack_complete` sets `collection_status` to PARTIAL when `sections_missing` is non-empty even with no `collection_errors`
- [ ] Config keys accessible via `settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES` etc.

---

## Acceptance Criteria

- [ ] `evidence_packs` collection added to `BugOpsStore`
- [ ] All five store methods implemented and tested
- [ ] `update_evidence_pack_section` uses MongoDB dot-notation for `evidence_references` — merges, never overwrites prior references
- [ ] MongoDB indexes defined for `evidence_packs`
- [ ] All six new config keys added to `core/config.py`
- [ ] All new store tests pass
- [ ] All existing BugOps tests continue to pass

---

## Impact

Unlocks TASK-116 (EvidenceCollector framework) and all collector tickets. No behavior change to existing system.

---

## Related Tickets

- TASK-114: Model definition (must be complete first)
- TASK-114A: Schema review (must be complete first)
- TASK-116: EvidenceCollector framework (immediate next)

---

## Completion Summary

- Branch: `task/bugops-115-evidence-pack-persistence`
- Commit: 986ec0f (feat(bugops): Implement EvidencePack persistence layer (TASK-115))
- Changes made:
  - Added `evidence_packs` collection to `BugOpsStore` with 5 store methods
  - Implemented section-by-section updates with MongoDB dot-notation merge semantics for `evidence_references`
  - Added 6 new config keys to `core/config.py` (settling window, log parameters, investigation token budget)
  - Wired MongoDB indexes into existing `db/mongodb.py` initialization path (not orphaned)
  - 14 comprehensive tests covering create, retrieve, partial updates, reference merging, and status logic
- Tests run: 62 core bugops tests passing (14 new + 48 existing); no regressions
- Deviations from plan: None. Index wiring initially missed but fixed before merge to follow established MongoDB initialization pattern.
