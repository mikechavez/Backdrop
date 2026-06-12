---
ticket_id: TASK-108
title: Wire freshness detectors into monitor with cascade suppression
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-108-cascade-suppression
effort_estimate: medium
---

# TASK-108: Wire freshness detectors into monitor with cascade suppression

## Problem Statement

The four freshness detectors exist as isolated classes after TASK-104 through
TASK-107. This ticket wires them into the polling loop and implements the
deterministic cascade suppression logic that prevents a scheduler failure from
generating four separate BugCases and four Slack notifications.

---

## Context

### Current monitor structure

`monitor.py` has:
- `BugOpsMonitor.__init__()` — instantiates settings, store (None until run),
  and `signal_sources` list (currently `LLMTraceCostSignalSource` and
  `RailwayLogSignalSource`)
- `BugOpsMonitor.run()` — initializes MongoDB, sets `self.store`, loops calling
  `_poll_signals()`
- `BugOpsMonitor._poll_signals()` — iterates `self.signal_sources`, calls
  `source.collect()`, calls `store.process_alert_event()` for each event, sends
  Slack for new cases
- `BugOpsMonitor.stop()` — sets `self.running = False`

The existing `_poll_signals()` flow for `LLMTraceCostSignalSource` must not change.
Freshness detectors use a separate polling path — do not mix them into the existing
`collect()` / `process_alert_event()` flow.

### Cascade suppression processing order (must not vary)

```
1. Detector's check_failure(db) returns True
2. Check open upstream BugCase: DependencyGraph.get_upstream_nodes(root_subsystem)
   → For each upstream node (nearest first):
     call store.find_open_case_by_root_subsystem(upstream_node)
     If found: call store.attach_observation_to_case(
         case_id, last_seen_at=now, affected_subsystems=[signal.root_subsystem]
     )
     Log suppression. Stop. No new BugCase. No notification.
3. Check open BugCase with same dedupe_key:
   call store.find_open_case_by_dedupe_key(dedupe_key)
   If found: call store.attach_observation_to_case(case_id, last_seen_at=now)
   Log attachment. Stop. No new BugCase. No notification.
4. Create new BugCase via store.create_case_direct(BugCaseCreate(...))
   Send notification per TASK-111 routing rules.
```

Upstream-wins is unconditional regardless of downstream severity or observation count.

### `detection_type` assignment

The monitor tracks whether the current poll is the first poll since startup
(`is_first_poll: bool`). When creating a new BugCase in Step 4:
- If `is_first_poll`: `detection_type = "startup"`
- Else: `detection_type = "runtime"`

Set `is_first_poll = False` after the first complete poll cycle finishes.

### New store method needed: `find_open_case_by_root_subsystem()`

Add this to `store.py` as part of this ticket:

```python
async def find_open_case_by_root_subsystem(self, root_subsystem: str) -> Optional[BugCase]:
    """Find an open BugCase by root_subsystem."""
    doc = await self.cases_collection.find_one({
        "root_subsystem": root_subsystem,
        "status": "open"
    })
    if doc:
        doc = _normalize_mongo_doc(doc)
        return BugCase(**doc)
    return None
```

---

## Task

1. Instantiate `DependencyGraph` once at monitor startup
2. Instantiate all four freshness detectors once at startup
3. Add `_poll_freshness_detectors()` method to `BugOpsMonitor` — separate from
   existing `_poll_signals()`
4. Implement cascade suppression processing order inside `_poll_freshness_detectors()`
5. Add `find_open_case_by_root_subsystem()` to `store.py`
6. Call `_poll_freshness_detectors()` from the main loop after `_poll_signals()`
7. Write integration tests for cascade suppression processing order

---

## Files to Create

```text
src/tests/bugops/test_cascade_suppression.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/signal_sources/__init__.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/dependency_graph.py
```

---

## Implementation Requirements

### Monitor `__init__()` changes

- [ ] Import and instantiate `DependencyGraph` once:
  `self.dependency_graph = DependencyGraph()`
- [ ] Import and instantiate all four freshness detectors:
  ```python
  from .signal_sources.article_freshness import ArticleFreshnessSignalSource
  from .signal_sources.signal_freshness import SignalFreshnessSignalSource
  from .signal_sources.narrative_freshness import NarrativeFreshnessSignalSource
  from .signal_sources.briefing_freshness import BriefingFreshnessSignalSource

  self.freshness_detectors = [
      ArticleFreshnessSignalSource(),
      SignalFreshnessSignalSource(),
      NarrativeFreshnessSignalSource(),
      BriefingFreshnessSignalSource(),
  ]
  ```
- [ ] Add `self.is_first_poll: bool = True`
- [ ] Build detector lookup map for auto-resolution (TASK-109 uses this):
  `self.detector_by_subsystem = {d.root_subsystem: d for d in self.freshness_detectors}`

### New `_poll_freshness_detectors()` method

For each detector in `self.freshness_detectors`:

```python
async def _poll_freshness_detectors(self) -> None:
    db = await mongo_manager.get_async_database()
    now = datetime.utcnow()

    for detector in self.freshness_detectors:
        start = time.monotonic()
        try:
            failure = await detector.check_failure(db)
            if not failure:
                continue

            # Step 2: upstream check
            upstream_nodes = self.dependency_graph.get_upstream_nodes(detector.root_subsystem)
            upstream_case = None
            for node in upstream_nodes:
                upstream_case = await self.store.find_open_case_by_root_subsystem(node)
                if upstream_case:
                    break

            if upstream_case:
                await self.store.attach_observation_to_case(
                    upstream_case.case_id,
                    last_seen_at=now,
                    affected_subsystems=[detector.root_subsystem],
                )
                logger.info(
                    "Cascade suppression: attached to upstream case",
                    extra={
                        "detector": detector.source_type,
                        "upstream_case_id": upstream_case.case_id,
                        "upstream_subsystem": upstream_case.root_subsystem,
                    }
                )
                continue

            # Step 3: dedupe check
            existing = await self.store.find_open_case_by_dedupe_key(detector.dedupe_key)
            if existing:
                await self.store.attach_observation_to_case(
                    existing.case_id, last_seen_at=now
                )
                continue

            # Step 4: create new BugCase
            detection_type = "startup" if self.is_first_poll else "runtime"
            blast_radius = self.dependency_graph.get_downstream_nodes(detector.root_subsystem)
            case_create = BugCaseCreate(
                case_id=f"bc_{detector.root_subsystem}_{int(now.timestamp())}",
                severity=DETECTOR_SEVERITY[detector.source_type],
                alert_type=detector.source_type,
                title=f"{detector.root_subsystem.capitalize()} Freshness Failure",
                summary=f"No {detector.root_subsystem} output within expected window.",
                dedupe_key=detector.dedupe_key,
                source_types=[detector.source_type],
                root_subsystem=detector.root_subsystem,
                blast_radius=blast_radius,
                affected_subsystems=[],
                first_seen_at=now,
                last_seen_at=now,
                observation_count=1,
                detection_type=detection_type,
                suggested_manual_check=detector.suggested_manual_check,
            )
            new_case = await self.store.create_case_direct(case_create)
            # Notification is TASK-111's responsibility.
            # Until TASK-111 is merged, send Slack for High severity:
            if self.settings.BUGOPS_SLACK_ENABLED:
                from .slack import send_case_notification
                await send_case_notification(new_case)

        except Exception as e:
            logger.error(
                "Detector run failed",
                extra={
                    "detector_name": detector.__class__.__name__,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "duration_ms": int((time.monotonic() - start) * 1000),
                }
            )

    # After first complete poll, set is_first_poll = False
    self.is_first_poll = False
```

### Main loop change

In `run()`, after `await self._poll_signals()`:
```python
await self._poll_freshness_detectors()
```

### `find_open_case_by_root_subsystem()` in `store.py`

- [ ] Queries `{"root_subsystem": root_subsystem, "status": "open"}`
- [ ] Returns first match as `BugCase` or `None`
- [ ] Uses `_normalize_mongo_doc()` before constructing `BugCase`

### Required imports in `monitor.py`

```python
import time
from datetime import datetime
from .dependency_graph import DependencyGraph
from .models import BugCaseCreate
from .signal_sources.severity import DETECTOR_SEVERITY
```

### Test cases in `test_cascade_suppression.py`

Use `AsyncMock` / `MagicMock` pattern from existing test files.
Mock `self.store`, `self.dependency_graph`, and the detector `check_failure()`.

- [ ] Upstream BugCase exists → `attach_observation_to_case()` called with
  upstream case ID, no `create_case_direct()` called
- [ ] No upstream BugCase, same `dedupe_key` open → `attach_observation_to_case()`
  called with existing case ID, no `create_case_direct()`
- [ ] No upstream BugCase, no open dedupe key → `create_case_direct()` called
  with correct fields
- [ ] `detection_type="startup"` when `is_first_poll=True`
- [ ] `detection_type="runtime"` when `is_first_poll=False`
- [ ] `is_first_poll` set to `False` after first complete poll
- [ ] `blast_radius` populated from `DependencyGraph.get_downstream_nodes()`
- [ ] `affected_subsystems` populated on upstream case attachment
- [ ] Detector throws exception → error logged with structured fields, loop
  continues, other detectors run
- [ ] Processing order respected: upstream check always before dedupe check

### Commands to Run

```bash
pytest src/tests/bugops/test_cascade_suppression.py -v
pytest src/tests/bugops/ -v
```

---

## Verification

### Automated Verification

- [ ] All cascade suppression test cases pass
- [ ] Existing `_poll_signals()` tests pass without modification
- [ ] Cost-runaway detector behavior unchanged

### Manual Verification

- [ ] Inject a failure for `articles` while an open BugCase exists for
  `ingestion` — confirm no new BugCase created and `affected_subsystems` updated
- [ ] Inject a detector exception — confirm the loop continues and other detectors run
- [ ] Confirm `is_first_poll=True` on first call, `False` on second

---

## Acceptance Criteria

- [ ] All four freshness detectors run in `_poll_freshness_detectors()` each cycle
- [ ] Cascade suppression order is deterministic: upstream → dedupe → create
- [ ] `detection_type` is `"startup"` on first poll, `"runtime"` thereafter
- [ ] `blast_radius` populated at BugCase creation
- [ ] `find_open_case_by_root_subsystem()` added to `store.py`
- [ ] Detector failures isolated — do not halt loop
- [ ] Existing `_poll_signals()` / cost-runaway behavior unchanged
- [ ] All test cases pass

---

## Related Tickets

- Depends on: TASK-100, TASK-100A, TASK-100B, TASK-101, TASK-102, TASK-103,
  TASK-104, TASK-105, TASK-106, TASK-107
- Blocks: TASK-108A, TASK-109

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
