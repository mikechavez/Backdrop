---
ticket_id: TASK-104
title: Implement ArticleFreshness detector
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-104-article-freshness
effort_estimate: medium
---

# TASK-104: Implement ArticleFreshness detector

## Problem Statement

If article ingestion stalls, BugOps currently has no way to detect it. Articles
are the base of the entire Backdrop pipeline — if they stop being produced,
signals, narratives, and briefings all go stale downstream. This detector closes
that gap.

---

## Context

### Five-part definition

| Part | Implementation |
|---|---|
| Last successful output | Most recent Article `created_at` within freshness window |
| Expected input or activity | Any Article with `fetched_at` within lookback window |
| Failure condition | No Article `created_at` within freshness window AND at least one source has historically produced articles in this time-of-day window |
| Legitimate idle condition | No Article `fetched_at` within lookback window, OR no historical activity in this time-of-day window |
| Recovery condition | At least one Article `created_at` within freshness window after a stall |

### Field names
- Authoritative timestamp: `created_at` on `articles` collection (NOT `inserted_at`, NOT `published_at`)
- Expected input proxy: `fetched_at` on Article records (no RSS fetch job collection exists in Backdrop)

### Protocol

The detector must implement the `SignalSource` protocol from `signal_sources/base.py`:

```python
class SignalSource(Protocol):
    source_type: str
    async def collect(self) -> List[BugAlertEventCreate]: ...
```

However, freshness detectors work differently from `LLMTraceCostSignalSource`:
they do NOT return `BugAlertEventCreate` objects. Instead, the monitor loop
(TASK-108) calls a separate method to get a signal object, then handles BugCase
creation itself. See the "Return type" section below.

### Severity and subsystem
- Import severity from `signal_sources/severity.py`: `DETECTOR_SEVERITY["article_freshness"]`
- Import subsystem from `models.py`: `BugOpsSubsystem.ARTICLES`

### Startup detection
If the failure condition is active on the first poll after BugOps starts, the
BugCase must be created with `detection_type="startup"`. The detector itself does
not track whether it's the first poll — the monitor (TASK-108) passes a
`is_startup_poll: bool` flag when calling `check_failure()`. The detector returns
the same signal regardless; the monitor sets `detection_type` based on the flag.

---

## Task

1. Create `article_freshness.py` in `signal_sources/`
2. Implement `ArticleFreshnessSignalSource` class
3. Add required configuration to `core/config.py`
4. Write unit tests covering idle vs. broken logic

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/signal_sources/article_freshness.py
src/tests/bugops/test_article_freshness.py
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

### Class structure

```python
class ArticleFreshnessSignalSource:
    source_type = "article_freshness"
    root_subsystem = BugOpsSubsystem.ARTICLES.value   # "articles"
    dedupe_key = "article_freshness:articles"
    suggested_manual_check = (
        "Check RSS ingestion health, recent fetch attempts, "
        "source availability, and whether articles are being "
        "inserted with created_at timestamps."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool:
        """Return True if the failure condition is met."""
        ...

    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool:
        """Return True if the recovery condition is met."""
        ...

    async def collect(self) -> List[BugAlertEventCreate]:
        """Required by SignalSource protocol. Not used by freshness detectors.
        Returns empty list — freshness detectors use check_failure() directly."""
        return []
```

The monitor (TASK-108) calls `check_failure(db)` and `check_recovery(db)` directly.
`collect()` satisfies the protocol but is not called for freshness detectors.

### Expected input check (precondition — must pass before evaluating failure)

- [ ] Query `articles` collection:
  `{"fetched_at": {"$gte": now - timedelta(minutes=BUGOPS_ARTICLE_FETCH_LOOKBACK_MINUTES)}}`
- [ ] If no document found: return `False` from `check_failure()` — legitimate idle

### Historical activity check (second precondition)

- [ ] Determine current hour of day in UTC
- [ ] Query `articles` collection for any document with `created_at` whose UTC
  hour is within ±1 of the current hour, with a `created_at` within the last
  `BUGOPS_ARTICLE_HISTORY_LOOKBACK_DAYS` days:
  ```python
  # Pseudocode — use $expr with $hour operator or post-filter
  # Match documents where hour(created_at) is in the window
  ```
- [ ] If no historical activity found for this time-of-day window: return `False`
  from `check_failure()` — legitimate idle (sources don't publish at this hour)

### Failure condition

- [ ] Query `articles` collection:
  `{"created_at": {"$gte": now - timedelta(minutes=BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES) - timedelta(seconds=60)}}`
- [ ] If document found: return `False` (healthy)
- [ ] If no document found AND both preconditions above are met: return `True`

### Recovery condition

- [ ] Same query as failure condition (any Article `created_at` within the freshness
  window + tolerance buffer)
- [ ] Return `True` if a document is found, `False` otherwise

### 60-second tolerance buffer

- [ ] Subtract an additional 60 seconds from all freshness window cutoffs before
  evaluating. Prevents boundary false positives from processing latency.
  `cutoff = now - timedelta(minutes=window_minutes) - timedelta(seconds=60)`

### Configuration — add to `core/config.py` via the existing `Settings` class

```python
BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES: int = 60
BUGOPS_ARTICLE_FETCH_LOOKBACK_MINUTES: int = 90
BUGOPS_ARTICLE_HISTORY_LOOKBACK_DAYS: int = 7
```

Use the existing `get_settings()` pattern. Do not add to `bugops/config.py` directly.

### Test cases in `test_article_freshness.py`

Use `AsyncMock` and `MagicMock` following the pattern in `test_llm_traces_cost_source.py`.
Mock `mongo_manager.get_async_database` and the collection `.find()` / `.find_one()` calls.

- [ ] Returns `False` from `check_failure()` when no articles fetched recently
  (no `fetched_at` in lookback window)
- [ ] Returns `False` from `check_failure()` when articles fetched recently but
  no historical activity at this time-of-day
- [ ] Returns `False` from `check_failure()` when articles are fresh (recent
  `created_at` within window)
- [ ] Returns `True` from `check_failure()` when fetch activity exists, historical
  activity exists, and no recent `created_at`
- [ ] `check_recovery()` returns `True` when a fresh article exists
- [ ] `check_recovery()` returns `False` when no fresh article exists
- [ ] Tolerance buffer applied: an article arriving 30 seconds after the strict
  window boundary is not treated as stale

### Commands to Run

```bash
pytest src/tests/bugops/test_article_freshness.py -v
```

---

## Verification

### Automated Verification

- [ ] All test cases listed above pass

### Manual Verification

- [ ] Run detector in a dev environment with a real MongoDB connection
- [ ] Confirm `check_failure()` returns `False` when articles are being produced
  normally
- [ ] Confirm `check_failure()` returns `True` when `created_at` of the most
  recent article is outside the freshness window and preconditions are met

---

## Acceptance Criteria

- [x] `source_type = "article_freshness"`
- [x] `root_subsystem = "articles"`
- [x] `severity = AlertSeverity.HIGH` (via DETECTOR_SEVERITY)
- [x] `dedupe_key = "article_freshness:articles"`
- [x] Uses `created_at` on `articles` (not `inserted_at` or `published_at`)
- [x] Returns `False` from `check_failure()` when either precondition not met
- [x] Returns `True` from `check_failure()` when both preconditions met and no
  recent article
- [x] `check_recovery()` works correctly
- [x] `collect()` returns `[]` (satisfies protocol, not used by monitor)
- [x] 60-second tolerance buffer applied
- [x] All config from `core/config.py`
- [x] All test cases pass (11/11)

---

## Impact

Closes the article ingestion visibility gap. When ingestion stalls, operators
will be notified automatically.

---

## Related Tickets

- Depends on: TASK-100, TASK-100A, TASK-100B, TASK-101, TASK-102
- Blocks: TASK-108, TASK-109

---

## Completion Summary

- Branch: `task/bugops-104-article-freshness`
- Commits: 708b5dc (initial implementation), a8f6ec5 (add severity attribute)
- Changes made:
  - Created `src/crypto_news_aggregator/bugops/signal_sources/article_freshness.py` with `ArticleFreshnessSignalSource` class
  - Three-check failure logic: fetch activity precondition, historical time-of-day precondition, freshness window check
  - Added `check_recovery()` method for recovery condition detection
  - Recovery and failure queries use 60-second tolerance buffer
  - Exception handling: logs errors and returns False (detector isolation per TASK-108)
  - Static metadata exposed: `source_type`, `root_subsystem`, `severity`, `dedupe_key`, `suggested_manual_check`
  - Added three settings to `core/config.py`: `BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES`, `BUGOPS_ARTICLE_FETCH_LOOKBACK_MINUTES`, `BUGOPS_ARTICLE_HISTORY_LOOKBACK_DAYS`
  - Created `src/tests/bugops/test_article_freshness.py` with 11 unit tests

- Tests run: `poetry run pytest src/tests/bugops/test_article_freshness.py -v` — all 11 tests pass
  - test_class_attributes (includes severity == AlertSeverity.HIGH assertion)
  - test_check_failure_no_fetch_activity
  - test_check_failure_no_historical_activity
  - test_check_failure_articles_are_fresh
  - test_check_failure_stale_articles_with_preconditions
  - test_check_recovery_returns_true_when_fresh
  - test_check_recovery_returns_false_when_no_fresh
  - test_tolerance_buffer_30_seconds
  - test_collect_returns_empty_list
  - test_check_failure_handles_exception
  - test_check_recovery_handles_exception

- Manual verification: Detector ready for integration into monitor (TASK-108). Static metadata complete for cascade suppression and BugCase creation.

- Deviations from plan: None. Added severity class attribute as required by TASK-108 pattern.
