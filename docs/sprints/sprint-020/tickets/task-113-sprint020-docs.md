---
ticket_id: TASK-113
title: Update Sprint 020 docs and success criteria
priority: low
severity: low
status: OPEN
date_created: 2025-01-01
branch: task/bugops-113-sprint020-docs
effort_estimate: small
---

# TASK-113: Update Sprint 020 docs and success criteria

## Problem Statement

Sprint 020 scope changed from the original plan. The sprint doc, success criteria,
and inline documentation must reflect the final implemented scope before Sprint 021
begins. Sprint 021 does not start until Sprint 020 success criteria are fully met
and documented.

---

## Context

This is a documentation-only ticket. No production code changes.

### What changed from original scope

- TASK-110 (flapping detection) removed — Recovery Window repeated-failure
  handling is sufficient; dedicated flapping not implemented
- TASK-100A added (canonical subsystem enum)
- TASK-100B added (deterministic severity mapping)
- TASK-100C added (Slack webhook Railway config)
- TASK-108A added (startup detection)
- TASK-111A added (notification attempt persistence)
- TASK-112A added (suppression expiry summary)
- TASK-113 added (this ticket)
- Suppression mechanism changed: single `BUGOPS_SUPPRESSED_UNTIL` timestamp
  variable replaces `BUGOPS_SUPPRESSION_ACTIVE` + `BUGOPS_SUPPRESSION_EXPIRES_AT`
- `detection_type` field added to BugCase model
- `reopen_count` field added to BugCase model
- `observation_count` default changed from 0 to 1
- Railway log ingestion explicitly deferred to Sprint 021
- RuntimeExceptionSignalSource explicitly out of scope

---

## Task

1. Update `sprint-020-bugops-outcome-freshness.md` — ticket table, scope,
   success criteria, key decisions
2. Update inline comments in `models.py` where noted
3. Update `signal_sources/__init__.py` to export the four new detectors

---

## Files to Create

```text
(none)
```

---

## Files to Modify

```text
sprint-020-bugops-outcome-freshness.md (or wherever the sprint doc lives)
src/crypto_news_aggregator/bugops/signal_sources/__init__.py
```

---

## Do Not Modify

```text
(any production logic files)
```

---

## Implementation Requirements

### Sprint doc updates

**Ticket table:** confirm all 18 tickets are listed with correct status after
sprint completion.

**Success criteria — remove:**
```
Flapping protection activates and notifies correctly under rapid oscillation
```

**Success criteria — confirm present:**
```
A BugCase does not auto-resolve if the failure condition recurs during the Recovery Window
Active failures present at BugOps startup create BugCases with detection_type=startup
Startup-created Critical and High BugCases send Slack notifications
Slack messages include severity, root_subsystem, affected_subsystems, summary,
  first_seen_at, last_seen_at, observation_count, dedupe_key, detection_type,
  and suggested_manual_check
Slack send failure records a failed notification attempt and does not block
  BugCase creation
Deploy suppression suppresses notification delivery without suppressing BugCase
  creation or updates
Suppression expiry sends one summary for unresolved Critical and High BugCases
  active during suppression
Canonical subsystem names used consistently across all components
Railway log ingestion and runtime exception monitoring are not implemented in Sprint 020
```

**Key decisions — add:**
```
Flapping detection deferred | Recovery Window handles practical oscillation;
  no evidence Backdrop needs dedicated flapping yet | TASK-110 removed

Railway log ingestion deferred to Sprint 021 | Log access requires validation
  of programmatic Railway API access; does not affect outcome freshness detection

Startup detection creates BugCases for active failures | Operator needs to know
  if production is broken when BugOps starts | TASK-108A added; detection_type
  field added to BugCase model

Suppression mechanism simplified to single timestamp variable | Two-variable
  design (active bool + expires timestamp) replaced with BUGOPS_SUPPRESSED_UNTIL
  ISO timestamp | Simpler to reason about; no risk of boolean/timestamp mismatch
```

**Out of scope — confirm these entries exist:**
```
Railway log ingestion
RuntimeExceptionSignalSource
Runtime exception monitoring from Railway logs
Slack interactive UI, buttons, slash commands, or acknowledgement actions
Dedicated flapping detection with manual escalation
```

### `signal_sources/__init__.py` update

Export the four new detector classes so TASK-108 imports cleanly:

```python
from .article_freshness import ArticleFreshnessSignalSource
from .signal_freshness import SignalFreshnessSignalSource
from .narrative_freshness import NarrativeFreshnessSignalSource
from .briefing_freshness import BriefingFreshnessSignalSource
from .severity import DETECTOR_SEVERITY

__all__ = [
    "ArticleFreshnessSignalSource",
    "SignalFreshnessSignalSource",
    "NarrativeFreshnessSignalSource",
    "BriefingFreshnessSignalSource",
    "DETECTOR_SEVERITY",
]
```

### Commands to Run

```bash
pytest src/tests/bugops/ -v
```

(Confirm full suite still passes after doc/export changes.)

---

## Verification

### Automated Verification

- [ ] Full bugops test suite passes

### Manual Verification

- [ ] Sprint doc ticket table has 18 tickets, all with correct status
- [ ] Flapping criterion absent from success criteria
- [ ] Recovery Window repeated-failure criterion present
- [ ] Railway log and RuntimeExceptionSignalSource explicitly out of scope
- [ ] `signal_sources/__init__.py` exports all four detectors

---

## Acceptance Criteria

- [ ] Sprint doc reflects final Sprint 020 scope
- [ ] Removed success criteria: flapping
- [ ] Added success criteria: startup detection, Slack contract, notification
  attempts, suppression expiry, canonical subsystems, Railway out of scope
- [ ] Four new key decisions documented
- [ ] `signal_sources/__init__.py` exports the four new detectors
- [ ] Full bugops test suite passes

---

## Impact

Closes Sprint 020 formally. Required before Sprint 021 begins.

---

## Related Tickets

- Depends on: all other Sprint 020 tickets
- Blocks: Sprint 021

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
