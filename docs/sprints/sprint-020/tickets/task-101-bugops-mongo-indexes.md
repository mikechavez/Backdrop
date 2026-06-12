---
ticket_id: TASK-101
title: Add MongoDB indexes for BugOps collections
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-101-mongodb-indexes
effort_estimate: small
---

# TASK-101: Add MongoDB indexes for BugOps collections

## Problem Statement

BugOps collections currently have no indexes defined. Sprint 020 adds four
freshness detectors running on every polling cycle, cascade suppression that
queries for open upstream BugCases by subsystem, idempotency logic that queries
for open BugCases by dedupe key, and notification attempt persistence. Without
indexes these queries degrade linearly with collection size. Indexes must be in
place before detectors run.

---

## Context

The existing index pattern in `mongodb.py` is:

```python
# At module level, define a list of index dicts:
BUG_CASES_INDEXES = [
    {"keys": [("dedupe_key", 1), ("status", 1)], "name": "dedupe_key_status"},
    ...
]

# In MongoManager.initialize_indexes(), for each collection:
collection = await self.get_async_collection("bug_cases")
for index_info in BUG_CASES_INDEXES:
    index_options = index_info.copy()
    keys = index_options.pop("keys")
    if not await self._has_index(collection, index_options.get("name")):
        await collection.create_index(keys, **index_options)
```

The `_has_index()` helper already exists — it checks by name before creating,
making the operation idempotent. Follow this exact pattern.

`initialize_indexes()` is called from `initialize_mongodb()` at application
startup, which is called from the FastAPI lifespan and from the BugOps monitor's
`run()` method via `mongo_manager.initialize()` → `ensure_indexes()`.

Three collections need indexes in this ticket: `bug_cases`, `bug_alert_events`,
and `notification_attempts` (added by TASK-111A).

---

## Task

1. Add `BUG_CASES_INDEXES` list at module level in `mongodb.py`
2. Add `BUG_ALERT_EVENTS_INDEXES` list at module level in `mongodb.py`
3. Add `NOTIFICATION_ATTEMPTS_INDEXES` list at module level in `mongodb.py`
4. Wire all three into `initialize_indexes()` following the existing pattern
5. Confirm no duplicate index errors on startup

---

## Files to Create

```text
(none)
```

---

## Files to Modify

```text
src/crypto_news_aggregator/db/mongodb.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
```

---

## Implementation Requirements

### Indexes on `bug_cases`

- [ ] `{"keys": [("dedupe_key", 1), ("status", 1)], "name": "bug_cases_dedupe_key_status"}` — supports `find_open_case_by_dedupe_key()`; most frequent query
- [ ] `{"keys": [("status", 1), ("created_at", -1)], "name": "bug_cases_status_created_at"}` — supports listing open and recent cases
- [ ] `{"keys": [("root_subsystem", 1), ("status", 1)], "name": "bug_cases_root_subsystem_status"}` — supports `find_open_case_by_root_subsystem()` in cascade suppression
- [ ] `{"keys": [("first_seen_at", 1)], "name": "bug_cases_first_seen_at"}` — supports freshness window queries in auto-resolution

### Indexes on `bug_alert_events`

- [ ] `{"keys": [("dedupe_key", 1)], "name": "bug_alert_events_dedupe_key"}` — supports alert lookups
- [ ] `{"keys": [("created_at", -1)], "name": "bug_alert_events_created_at"}` — supports retention policy queries

### Indexes on `notification_attempts`

- [ ] `{"keys": [("bugcase_id", 1)], "name": "notification_attempts_bugcase_id"}` — supports lookup of all attempts for a BugCase
- [ ] `{"keys": [("attempted_at", -1)], "name": "notification_attempts_attempted_at"}` — supports retention queries

### Wiring in `initialize_indexes()`

Add after the existing entity_mentions index block:

```python
# BugOps collections
bug_cases_col = await self.get_async_collection("bug_cases")
for index_info in BUG_CASES_INDEXES:
    index_options = index_info.copy()
    keys = index_options.pop("keys")
    if not await self._has_index(bug_cases_col, index_options.get("name")):
        await bug_cases_col.create_index(keys, **index_options)

bug_alert_events_col = await self.get_async_collection("bug_alert_events")
for index_info in BUG_ALERT_EVENTS_INDEXES:
    index_options = index_info.copy()
    keys = index_options.pop("keys")
    if not await self._has_index(bug_alert_events_col, index_options.get("name")):
        await bug_alert_events_col.create_index(keys, **index_options)

notification_attempts_col = await self.get_async_collection("notification_attempts")
for index_info in NOTIFICATION_ATTEMPTS_INDEXES:
    index_options = index_info.copy()
    keys = index_options.pop("keys")
    if not await self._has_index(notification_attempts_col, index_options.get("name")):
        await notification_attempts_col.create_index(keys, **index_options)
```

Also add all three collection names to the `force_recreate` drop block if that
block exists.

### Configuration

No new environment variables required for this ticket.

### Commands to Run

```bash
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] Existing bugops tests pass without modification
- [ ] No duplicate index errors on startup (idempotent due to `_has_index` check)

### Manual Verification

- [ ] Connect to the development MongoDB instance after startup and run:
  ```
  db.bug_cases.getIndexes()
  db.bug_alert_events.getIndexes()
  db.notification_attempts.getIndexes()
  ```
- [ ] Confirm all 8 indexes appear (4 on bug_cases, 2 on bug_alert_events,
  2 on notification_attempts)

---

## Acceptance Criteria

- [ ] 4 indexes on `bug_cases` with names as specified
- [ ] 2 indexes on `bug_alert_events` with names as specified
- [ ] 2 indexes on `notification_attempts` with names as specified
- [ ] All follow the `_has_index` idempotent pattern from existing collections
- [ ] Application starts without errors
- [ ] Existing bugops tests pass

---

## Impact

Required for query performance as BugOps collections grow. No behavior change.
Unblocks Phase 3 detectors and Phase 4 suppression/resolution logic.

---

## Related Tickets

- Depends on: TASK-100
- Blocks: TASK-104, TASK-105, TASK-106, TASK-107, TASK-108, TASK-109, TASK-111A

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
