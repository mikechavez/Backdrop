---
ticket_id: TASK-100B
title: Add deterministic severity mapping for Sprint 020 detectors
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-100b-severity-mapping
effort_estimate: small
---

# TASK-100B: Add deterministic severity mapping for Sprint 020 detectors

## Problem Statement

Sprint 020 freshness detectors each hardcode their severity as `AlertSeverity.HIGH`.
Without a shared mapping, each detector independently defines severity, making the
routing table in TASK-111 dependent on convention rather than an enforceable contract.
A shared mapping makes severity assignment explicit, testable, and easy to change
in one place.

---

## Context

Sprint 020 severity mapping:

```
ArticleFreshness:   High
SignalFreshness:    High
NarrativeFreshness: High
BriefingFreshness:  High
```

Severity is assigned deterministically at detection time. It is not computed
dynamically from observation count, blast radius, or any runtime state in Sprint 020.

The mapping lives in a new file `signal_sources/severity.py`. Each detector
(TASK-104 through TASK-107) imports its severity from there instead of hardcoding
`AlertSeverity.HIGH` inline.

TASK-111 notification routing depends on this mapping — Critical and High receive
immediate Slack; Medium logs digest intent; Low logs only.

---

## Task

1. Create `signal_sources/severity.py` with the `DETECTOR_SEVERITY` mapping
2. Write unit tests confirming the mapping values
3. Do not modify any detector files — they will import from here in TASK-104 to TASK-107

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/signal_sources/severity.py
src/tests/bugops/test_severity_mapping.py
```

---

## Files to Modify

```text
(none)
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/core/config.py
```

---

## Implementation Requirements

### `severity.py`

```python
from ..models import AlertSeverity

# Deterministic severity mapping for Sprint 020 freshness detectors.
# Severity is assigned at detection time, not computed dynamically.
DETECTOR_SEVERITY: dict[str, AlertSeverity] = {
    "article_freshness": AlertSeverity.HIGH,
    "signal_freshness": AlertSeverity.HIGH,
    "narrative_freshness": AlertSeverity.HIGH,
    "briefing_freshness": AlertSeverity.HIGH,
}
```

- [ ] Dict keys match the detector name strings used in dedupe keys
  (e.g. `"article_freshness"` matches the first segment of
  `"article_freshness:articles"`)
- [ ] All four values are `AlertSeverity.HIGH`
- [ ] Module-level docstring explains this is Sprint 020 only and escalation
  is not implemented

### Test cases in `test_severity_mapping.py`

- [ ] `DETECTOR_SEVERITY["article_freshness"] == AlertSeverity.HIGH`
- [ ] `DETECTOR_SEVERITY["signal_freshness"] == AlertSeverity.HIGH`
- [ ] `DETECTOR_SEVERITY["narrative_freshness"] == AlertSeverity.HIGH`
- [ ] `DETECTOR_SEVERITY["briefing_freshness"] == AlertSeverity.HIGH`
- [ ] Mapping has exactly 4 keys
- [ ] All values are `AlertSeverity.HIGH` (no dynamic computation)

### Configuration

No new environment variables required.

### Commands to Run

```bash
pytest src/tests/bugops/test_severity_mapping.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All 6 test cases pass
- [ ] All existing bugops tests pass without modification

### Manual Verification

- [ ] Import `DETECTOR_SEVERITY` in a Python REPL and confirm all four values
  are `AlertSeverity.HIGH`

---

## Acceptance Criteria

- [ ] `severity.py` exists with the `DETECTOR_SEVERITY` dict
- [ ] All four freshness detectors map to `AlertSeverity.HIGH`
- [ ] No dynamic severity computation
- [ ] All test cases pass
- [ ] Existing tests unaffected

---

## Impact

TASK-104 through TASK-107 will import severity from here. TASK-111 notification
routing reads `AlertSeverity` values from BugCase, so this mapping must be
consistent with what TASK-111 expects. No behavior change in this ticket —
mapping definition only.

---

## Related Tickets

- Depends on: TASK-100 (AlertSeverity enum must exist)
- Blocks: TASK-104, TASK-105, TASK-106, TASK-107, TASK-111

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
