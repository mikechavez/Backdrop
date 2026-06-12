---
ticket_id: TASK-105
title: Implement SignalFreshness detector
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-105-signal-freshness
effort_estimate: medium
---

# TASK-105: Implement SignalFreshness detector

## Problem Statement

If signal score computation stalls, BugOps has no way to detect it. Signal scores
feed narratives and briefings. A stall here degrades all downstream content without
any visible error.

---

## Context

### Five-part definition

| Part | Implementation |
|---|---|
| Last successful output | Most recent `signal_scores` document `last_updated` within freshness window |
| Expected input or activity | At least one Article with `created_at` within the freshness window |
| Failure condition | Article(s) with `created_at` within window AND no `signal_scores` document with `last_updated` within window |
| Legitimate idle condition | No articles with `created_at` within the freshness window |
| Recovery condition | At least one `signal_scores` document with `last_updated` within window after a stall |

### Field names
- Authoritative timestamp: `last_updated` on `signal_scores` collection (NOT `inserted_at`, NOT `first_seen`)
- Input check timestamp: `created_at` on `articles` collection

### Class interface (same pattern as TASK-104)

```python
class SignalFreshnessSignalSource:
    source_type = "signal_freshness"
    root_subsystem = BugOpsSubsystem.SIGNALS.value   # "signals"
    dedupe_key = "signal_freshness:signals"
    suggested_manual_check = (
        "Check signal generation worker health and confirm "
        "recent articles are being processed into signals."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def collect(self) -> List[BugAlertEventCreate]: return []
```

Severity: `DETECTOR_SEVERITY["signal_freshness"]` from `severity.py`.

Startup detection: same as TASK-104 — monitor sets `detection_type` based on
`is_startup_poll` flag; detector is unaware.

---

## Task

1. Create `signal_freshness.py` in `signal_sources/`
2. Implement `SignalFreshnessSignalSource`
3. Add required configuration to `core/config.py`
4. Write unit tests

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/signal_sources/signal_freshness.py
src/tests/bugops/test_signal_freshness.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/core/config.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/models.py
```

---

## Implementation Requirements

### Expected input check (precondition)

- [ ] Query `articles` collection:
  `{"created_at": {"$gte": now - timedelta(minutes=BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES) - timedelta(seconds=60)}}`
- [ ] If no document found: return `False` — legitimate idle (no article input)

### Failure condition

- [ ] Query `signal_scores` collection:
  `{"last_updated": {"$gte": now - timedelta(minutes=BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES) - timedelta(seconds=60)}}`
- [ ] If document found: return `False` (healthy)
- [ ] If no document found AND precondition met: return `True`

### Recovery condition

- [ ] Same query as failure condition on `signal_scores`
- [ ] Return `True` if document found

### 60-second tolerance buffer applied to both queries

### Configuration

```python
BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES: int = 90
```

### Test cases

- [ ] Returns `False` from `check_failure()` when no recent articles (legitimate idle)
- [ ] Returns `False` from `check_failure()` when recent articles and signals are fresh
- [ ] Returns `True` from `check_failure()` when recent articles but no fresh signals
- [ ] `check_recovery()` returns `True` when fresh signal exists
- [ ] `check_recovery()` returns `False` when no fresh signal
- [ ] Tolerance buffer applied correctly

### Commands to Run

```bash
pytest src/tests/bugops/test_signal_freshness.py -v
```

---

## Acceptance Criteria

- [ ] `source_type = "signal_freshness"`, `root_subsystem = "signals"`, `dedupe_key = "signal_freshness:signals"`
- [ ] Uses `last_updated` on `signal_scores`
- [ ] Uses `created_at` on `articles` for input check
- [ ] Correct idle vs broken behavior
- [ ] `collect()` returns `[]`
- [ ] All test cases pass

---

## Related Tickets

- Depends on: TASK-100, TASK-100A, TASK-100B, TASK-101, TASK-102
- Blocks: TASK-108, TASK-109

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
