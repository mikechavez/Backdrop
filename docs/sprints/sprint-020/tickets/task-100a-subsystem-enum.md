---
ticket_id: TASK-100A
title: Add canonical BugOps subsystem enum
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-100a-subsystem-enum
effort_estimate: small
---

# TASK-100A: Add canonical BugOps subsystem enum

## Problem Statement

Subsystem names are currently bare strings scattered across detectors, BugCase
fields, and DependencyGraph logic. Without a shared enum, a typo in any one
place produces a silent mismatch that breaks cascade suppression. A canonical
enum enforces consistency at definition time.

---

## Context

The enum must be importable by detectors (TASK-104 through TASK-107),
DependencyGraph (TASK-103), BugOpsStore (TASK-102), and monitor (TASK-108).
The natural home is `models.py` alongside the other enums already there
(`AlertSeverity`, `AlertStatus`, `CaseStatus`).

`worker` and `database` are included in the enum for future detectors but are
not DependencyGraph nodes in Sprint 020.

After this ticket merges, TASK-100's `root_subsystem`, `affected_subsystems`,
and `blast_radius` field type annotations should be updated to `BugOpsSubsystem`
/ `list[BugOpsSubsystem]`. This is a follow-up annotation change — it does not
block TASK-100A acceptance.

---

## Task

1. Add `BugOpsSubsystem` enum to `models.py`
2. Write unit tests confirming enum values
3. Confirm existing tests still pass

---

## Files to Create

```text
(none — tests go in the existing test_bugops_models.py)
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/tests/bugops/test_bugops_models.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### `BugOpsSubsystem` enum

Add to `models.py` alongside the existing enums:

```python
class BugOpsSubsystem(str, Enum):
    """Canonical subsystem names for BugOps detectors and DependencyGraph."""
    SCHEDULER = "scheduler"
    INGESTION = "ingestion"
    ARTICLES = "articles"
    SIGNALS = "signals"
    NARRATIVES = "narratives"
    BRIEFINGS = "briefings"
    WORKER = "worker"    # reserved — no detector in Sprint 020
    DATABASE = "database"  # reserved — no detector in Sprint 020
```

- [ ] Inherits from `(str, Enum)` so values serialize as plain strings in MongoDB
- [ ] All eight values present with exact string values as shown
- [ ] `WORKER` and `DATABASE` have inline comments noting they are reserved

### Test cases to add to `test_bugops_models.py`

- [ ] `BugOpsSubsystem.ARTICLES.value == "articles"`
- [ ] `BugOpsSubsystem.SIGNALS.value == "signals"`
- [ ] `BugOpsSubsystem.NARRATIVES.value == "narratives"`
- [ ] `BugOpsSubsystem.BRIEFINGS.value == "briefings"`
- [ ] `BugOpsSubsystem.SCHEDULER.value == "scheduler"`
- [ ] `BugOpsSubsystem.INGESTION.value == "ingestion"`
- [ ] `BugOpsSubsystem.WORKER.value == "worker"`
- [ ] `BugOpsSubsystem.DATABASE.value == "database"`
- [ ] Enum has exactly 8 members
- [ ] `BugOpsSubsystem("articles") == BugOpsSubsystem.ARTICLES` (str construction works)

### Configuration

No new environment variables required.

### Commands to Run

```bash
pytest src/tests/bugops/test_bugops_models.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All new enum test cases pass
- [ ] All existing bugops tests pass without modification

### Manual Verification

- [ ] Import `BugOpsSubsystem` from `models.py` in a Python REPL and confirm all
  8 values are accessible
- [ ] Confirm `BugOpsSubsystem.WORKER.value == "worker"` and
  `BugOpsSubsystem.DATABASE.value == "database"`

---

## Acceptance Criteria

- [ ] `BugOpsSubsystem` enum exists in `models.py` with all 8 values
- [ ] Inherits from `(str, Enum)`
- [ ] `WORKER` and `DATABASE` have reserved comments
- [ ] All 10 test cases pass
- [ ] All existing bugops tests pass

---

## Impact

Downstream: TASK-103 (DependencyGraph), TASK-104 through TASK-107 (detectors),
TASK-108 (monitor wiring) all import and use this enum. No behavior change in
this ticket — enum definition only.

---

## Related Tickets

- Depends on: TASK-100 (enum lives in same file; merge TASK-100 first)
- Blocks: TASK-103, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
