---
ticket_id: TASK-100
title: Extend BugCase model with Sprint 020 fields
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-100-bugcase-model-sprint020
effort_estimate: small
---

# TASK-100: Extend BugCase model with Sprint 020 fields

## Problem Statement

The current `BugCaseCreate` and `BugCase` models do not have the fields required by
Sprint 020: freshness tracking, cascade suppression metadata, recovery tracking,
operator flags, and notification state. All Sprint 020 behavior depends on these
fields existing before any detector, suppression, or resolution logic is written.

---

## Context

`BugCase` lives in `src/crypto_news_aggregator/bugops/models.py`.

Current `BugCaseCreate` fields (do not remove or rename any of these):
```python
case_id: str
status: CaseStatus = CaseStatus.OPEN
severity: AlertSeverity
alert_type: str
title: str
summary: str
dedupe_key: str
source_types: list[str]
alert_ids: list[str] = Field(default_factory=list)
correlation_keys: list[str] = Field(default_factory=list)
metric: dict = Field(default_factory=dict)
suggested_manual_check: Optional[str] = None
created_at: datetime = Field(default_factory=datetime.utcnow)
updated_at: datetime = Field(default_factory=datetime.utcnow)
resolved_at: Optional[datetime] = None
closed_at: Optional[datetime] = None
deterministic_report: Optional[str] = None
```

All new fields must be optional or have defaults so existing Sprint 018 cases,
tests, and the cost-runaway detector are completely unaffected.

`BugCase` inherits from `BugCaseCreate` — confirm new fields are accessible on
retrieved documents after this change.

`root_subsystem`, `affected_subsystems`, and `blast_radius` are typed as `str` /
`list[str]` in this ticket. TASK-100A adds the canonical subsystem enum; once
TASK-100A is merged, the type annotation for these three fields should be updated
to use `BugOpsSubsystem`. Do not block this ticket on TASK-100A.

Architecture invariant: `muted_until` and `snoozed_until` are flags that affect
notification behavior only. They are not lifecycle statuses and do not block
auto-resolution or case progression.

---

## Task

1. Add all new fields to `BugCaseCreate` in `models.py`
2. Confirm `BugCase` (read model) reflects the same fields via inheritance
3. Run existing tests to confirm no regressions

---

## Files to Create

```text
(none)
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/models.py
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

Add the following fields to `BugCaseCreate`. All are optional or have defaults.

### Subsystem tracking
- [ ] `root_subsystem: Optional[str] = None` — subsystem closest to originating failure
- [ ] `affected_subsystems: list[str] = Field(default_factory=list)` — downstream subsystems impacted by cascade suppression attachments
- [ ] `blast_radius: list[str] = Field(default_factory=list)` — all reachable downstream nodes from DependencyGraph at creation time

### Observation tracking
- [ ] `observation_count: int = 1` — starts at 1 (the creating observation); incremented by `attach_observation_to_case()`
- [ ] `first_seen_at: Optional[datetime] = None` — when the failure condition was first observed; distinct from `created_at`
- [ ] `last_seen_at: Optional[datetime] = None` — when the failure condition was most recently observed

### Recovery tracking
- [ ] `recovery_candidate_at: Optional[datetime] = None` — internal field; set when recovery condition is first met; cleared if failure recurs before Recovery Window elapses; never operator-facing

### Resolution metadata
- [ ] `resolution_type: Optional[str] = None` — not required in Sprint 020; reserved for future use; add inline comment: `# reserved: real_issue | false_positive | duplicate | operator_error | expected_idle`

### Detection metadata
- [ ] `detection_type: Optional[str] = None` — how the BugCase was created; valid values: `startup`, `runtime`, `reopen`; add inline comment: `# startup | runtime | reopen`
- [ ] `reopen_count: int = 0` — incremented each time a resolved BugCase is reopened

### Operator flags (affect notification only — do not block auto-resolution)
- [ ] `muted_until: Optional[datetime] = None`
- [ ] `snoozed_until: Optional[datetime] = None`

### Notification tracking
- [ ] `last_notified_at: Optional[datetime] = None`
- [ ] `notification_count: int = 0`

### Configuration

No new environment variables required for this ticket.

### Commands to Run

```bash
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All existing bugops tests pass without modification
- [ ] A `BugCaseCreate` can be instantiated with no new fields provided and defaults are applied correctly
- [ ] A `BugCaseCreate` can be instantiated with all new fields provided and values are stored correctly

### Manual Verification

- [ ] Confirm the existing cost-runaway detector test creates a BugCase successfully after this change
- [ ] Confirm `observation_count` defaults to `1` (not `0`)
- [ ] Confirm `detection_type` accepts `None` and the string values `startup`, `runtime`, `reopen`

---

## Acceptance Criteria

- [ ] All 14 new fields are present on `BugCaseCreate` with correct types and defaults
- [ ] `observation_count` defaults to `1`
- [ ] `detection_type` and `resolution_type` have inline comments as specified
- [ ] Existing Sprint 018 tests pass without modification
- [ ] No existing BugCase creation call requires changes to continue working

---

## Impact

Unblocks all of Phase 3 and Phase 4 of Sprint 020. No behavior change in this
ticket — schema only.

---

## Related Tickets

- Blocks: TASK-101, TASK-102, TASK-104, TASK-105, TASK-106, TASK-107, TASK-108,
  TASK-109, TASK-111, TASK-112
- Related: TASK-100A (canonical subsystem enum — update type annotations after merge)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
