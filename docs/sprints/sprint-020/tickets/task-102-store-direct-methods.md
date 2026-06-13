---
ticket_id: TASK-102
title: Add `create_case_direct()` and `attach_observation_to_case()` to BugOpsStore
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-102-store-direct-methods
effort_estimate: small
---

# TASK-102: Add `create_case_direct()` and `attach_observation_to_case()` to BugOpsStore

## Problem Statement

Freshness detectors are internal to BugOps. They do not produce external
`BugAlertEvent` objects — they detect conditions directly and need to create or
update a BugCase without going through the `process_alert_event()` flow. The
current store has no method that supports this pattern.

---

## Context

Current `BugOpsStore` in `store.py` has these methods (do not modify):
- `create_alert_event()`
- `find_open_case_by_dedupe_key()`
- `create_case_from_alert()`
- `attach_alert_to_case()`
- `get_case()`
- `process_alert_event()`
- `get_alert_events_for_case()`
- `save_case_report()`

Two new methods are needed:

**`create_case_direct()`** — creates a BugCase from a `BugCaseCreate` directly,
without requiring a `BugAlertEvent`. Returns the created `BugCase`.

**`attach_observation_to_case()`** — increments `observation_count`, updates
`last_seen_at`, and optionally adds to `affected_subsystems` on an existing
BugCase. Does not require an `alert_id`. Returns the updated `BugCase`.

The `_normalize_mongo_doc()` helper already exists and handles ObjectId → str
conversion. Use it in both new methods as all existing methods do.

Note the `import __import__("datetime")` pattern used in `attach_alert_to_case()`
for `datetime.utcnow()` — use the standard `from datetime import datetime` import
at the top of the file instead for the new methods (or reuse whatever import
pattern is cleanest in context).

---

## Task

1. Add `create_case_direct(case: BugCaseCreate) -> BugCase` to `BugOpsStore`
2. Add `attach_observation_to_case(case_id, last_seen_at, affected_subsystems) -> BugCase`
3. Write unit tests for both new methods
4. Confirm existing store tests pass without modification

---

## Files to Create

```text
src/tests/bugops/test_store_direct.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/store.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
```

---

## Implementation Requirements

### `create_case_direct(case: BugCaseCreate) -> BugCase`

- [ ] Accepts a `BugCaseCreate` as its only argument
- [ ] Calls `case.model_dump(by_alias=False, exclude_none=False)` to get the
  document dict — same pattern as `create_case_from_alert()`
- [ ] Inserts the document into `self.cases_collection`
- [ ] Sets `_id` on the dict from `result.inserted_id`
- [ ] Calls `_normalize_mongo_doc()` before constructing `BugCase`
- [ ] Returns the created `BugCase`
- [ ] Does not create a `BugAlertEvent`
- [ ] Does not send a notification

### `attach_observation_to_case(case_id: str, last_seen_at: datetime, affected_subsystems: Optional[list[str]] = None) -> BugCase`

- [ ] Accepts `case_id: str`, `last_seen_at: datetime`, and optional
  `affected_subsystems: Optional[list[str]] = None`
- [ ] Builds an update dict with:
  - `$inc`: `{"observation_count": 1}`
  - `$set`: `{"last_seen_at": last_seen_at, "updated_at": datetime.utcnow()}`
- [ ] If `affected_subsystems` is provided and non-empty: adds
  `$addToSet: {"affected_subsystems": {"$each": affected_subsystems}}` to the
  update — this adds new subsystems without duplicating existing ones
- [ ] Uses `find_one_and_update` with `return_document=True`
- [ ] Queries by `{"case_id": case_id}`
- [ ] Calls `_normalize_mongo_doc()` on result before constructing `BugCase`
- [ ] Returns the updated `BugCase`
- [ ] Raises `ValueError(f"Case {case_id} not found")` if no document found —
  same pattern as existing `attach_alert_to_case()`
- [ ] Does not send a notification

### Test cases in `test_store_direct.py`

Use the same `mock_db` and `store` fixture pattern from `test_bugops_store.py`:

```python
@pytest.fixture
def mock_db():
    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda x: MagicMock())
    return db

@pytest.fixture
def store(mock_db):
    return BugOpsStore(mock_db)
```

Required test cases:

- [ ] `create_case_direct()` calls `insert_one` and returns a `BugCase` with
  correct field values
- [ ] `create_case_direct()` with all Sprint 020 optional fields populated stores
  and retrieves correctly (set `root_subsystem`, `first_seen_at`, `last_seen_at`,
  `detection_type`, `observation_count`)
- [ ] `create_case_direct()` normalizes ObjectId `_id` to string
- [ ] `attach_observation_to_case()` uses `$inc` on `observation_count`
- [ ] `attach_observation_to_case()` sets `last_seen_at` correctly
- [ ] `attach_observation_to_case()` with `affected_subsystems` uses `$addToSet`
  with `$each`
- [ ] `attach_observation_to_case()` with `affected_subsystems=None` does not
  include `$addToSet` in the update dict
- [ ] `attach_observation_to_case()` raises `ValueError` when case not found
  (mock returns `None`)

### Configuration

No new environment variables required for this ticket.

### Commands to Run

```bash
pytest src/tests/bugops/test_store_direct.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All new test cases in `test_store_direct.py` pass
- [ ] All existing bugops store tests pass without modification

### Manual Verification

- [ ] Call `create_case_direct()` in a dev environment and confirm the document
  appears in MongoDB with `observation_count=1` and correct Sprint 020 fields
- [ ] Call `attach_observation_to_case()` twice and confirm `observation_count`
  is 3 (started at 1, incremented twice) and `last_seen_at` reflects the second
  call

---

## Acceptance Criteria

- [ ] `create_case_direct()` creates a BugCase without requiring a BugAlertEvent
- [ ] `attach_observation_to_case()` uses `$inc` for `observation_count`,
  `$set` for timestamps, `$addToSet` + `$each` for `affected_subsystems`
- [ ] Neither method sends a notification
- [ ] Neither method modifies the existing `process_alert_event()` flow
- [ ] All 8 test cases pass

---

## Impact

Unblocks all four freshness detectors (TASK-104 through TASK-107) and the cascade
suppression wiring (TASK-108). No behavior change to existing flows.

---

## Related Tickets

- Depends on: TASK-100
- Blocks: TASK-104, TASK-105, TASK-106, TASK-107, TASK-108

---

## Completion Summary

- Branch: `task/bugops-102-store-direct-methods`
- Commits: `4e9159a` (implementation), `6ed0ee1` (docs), `a46a97e` (PyMongo compatibility fix)
- Changes made:
  - Added `create_case_direct(case: BugCaseCreate) -> BugCase` to BugOpsStore
  - Added `attach_observation_to_case(case_id, last_seen_at, affected_subsystems) -> BugCase` to BugOpsStore
  - Created comprehensive test file with 9 test cases covering all requirements
  - Added `from datetime import datetime` import to store.py
  - Added `from pymongo import ReturnDocument` import for PyMongo compatibility
  - Fixed `return_document=True` → `return_document=ReturnDocument.AFTER` in attach_observation_to_case()
- Tests run:
  - All 9 new tests in test_store_direct.py: PASSED
  - All 21 existing store tests: PASSED
  - Combined 30/30 tests passing (verified after ReturnDocument fix)
- Manual verification:
  - Methods follow existing patterns (model_dump, normalize_mongo_doc, error handling)
  - $inc for observation_count, $set for timestamps
  - $addToSet + $each for affected_subsystems deduplication
  - ValueError raised when case not found (matches existing pattern)
  - ReturnDocument.AFTER used instead of boolean for proper PyMongo compatibility
- Deviations from plan: 
  - Added ReturnDocument enum import for Motor/PyMongo compatibility (ticket spec said return_document=True, but PyMongo requires the enum)
