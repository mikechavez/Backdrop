---
ticket_id: TASK-106
title: Implement NarrativeFreshness detector
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-106-narrative-freshness
effort_estimate: medium
---

# TASK-106: Implement NarrativeFreshness detector

## Problem Statement

If narrative refresh stalls, briefings go stale without any visible error.
Narratives sit between signals and briefings; a stall here degrades briefing
quality silently.

---

## Context

### Five-part definition

| Part | Implementation |
|---|---|
| Last successful output | Most recent narrative `last_summary_generated_at` within freshness window |
| Expected input or activity | At least one `signal_scores` document with `last_updated` within the freshness window |
| Failure condition | Signal scores exist within window AND no narrative `last_summary_generated_at` within window |
| Legitimate idle condition | No signal scores updated within the freshness window |
| Recovery condition | At least one narrative with `last_summary_generated_at` within window after a stall |

### Field names
- Authoritative timestamp: `last_summary_generated_at` on narrative documents
  (primary); ObjectId creation timestamp as fallback when `last_summary_generated_at`
  is absent
- Input check timestamp: `last_updated` on `signal_scores`

### Collection access
`narratives` collection has no formal Pydantic model. Query as `db["narratives"]`
directly (no constant defined for this collection in mongodb.py).

### ObjectId fallback
The `narratives` collection may have documents without `last_summary_generated_at`.
For these, extract the creation timestamp from the ObjectId:
`from bson import ObjectId` — `ObjectId.generation_time` returns a UTC-aware
datetime. This is a fallback only. If `last_summary_generated_at` is present,
always prefer it.

### Class interface (same pattern as TASK-104)

```python
class NarrativeFreshnessSignalSource:
    source_type = "narrative_freshness"
    root_subsystem = BugOpsSubsystem.NARRATIVES.value   # "narratives"
    dedupe_key = "narrative_freshness:narratives"
    suggested_manual_check = (
        "Check narrative refresh job health and confirm "
        "recent signals are available as input."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def collect(self) -> List[BugAlertEventCreate]: return []
```

Severity: `DETECTOR_SEVERITY["narrative_freshness"]` from `severity.py`.

Startup detection: monitor sets `detection_type`; detector is unaware.

---

## Task

1. Create `narrative_freshness.py` in `signal_sources/`
2. Implement `NarrativeFreshnessSignalSource`
3. Add required configuration to `core/config.py`
4. Write unit tests

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/signal_sources/narrative_freshness.py
src/tests/bugops/test_narrative_freshness.py
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

- [ ] Query `signal_scores`:
  `{"last_updated": {"$gte": now - timedelta(minutes=BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES) - timedelta(seconds=60)}}`
- [ ] If no document: return `False` — legitimate idle

### Failure condition

- [ ] Primary query on `narratives`:
  `{"last_summary_generated_at": {"$gte": cutoff}}`
- [ ] If document found: return `False` (healthy)
- [ ] If no document found: fallback query — fetch all `narratives` documents
  (or a reasonable limit), extract `ObjectId.generation_time` from `_id`, check
  if any falls within the window
- [ ] If neither query finds a document AND precondition met: return `True`

### Recovery condition

- [ ] Same two-step query (primary + ObjectId fallback)
- [ ] Return `True` if either query finds a fresh document

### 60-second tolerance buffer applied to all window comparisons

### Configuration

```python
BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES: int = 120
```

### Test cases

- [ ] Returns `False` when no recent signal scores (legitimate idle)
- [ ] Returns `False` when signal scores fresh and narratives have recent
  `last_summary_generated_at`
- [ ] Returns `True` when signal scores fresh and no narrative has
  `last_summary_generated_at` within window (and no recent ObjectId either)
- [ ] Falls back to ObjectId timestamp when `last_summary_generated_at` absent;
  returns `False` if ObjectId is recent
- [ ] `check_recovery()` returns `True` when fresh narrative exists
- [ ] `check_recovery()` returns `False` when no fresh narrative
- [ ] Tolerance buffer applied correctly

### Commands to Run

```bash
pytest src/tests/bugops/test_narrative_freshness.py -v
```

---

## Acceptance Criteria

- [ ] `source_type = "narrative_freshness"`, `root_subsystem = "narratives"`, `dedupe_key = "narrative_freshness:narratives"`
- [ ] Uses `last_summary_generated_at` as primary; ObjectId timestamp as fallback
- [ ] Uses `last_updated` on `signal_scores` for input check
- [ ] Correct idle vs broken behavior
- [ ] `collect()` returns `[]`
- [ ] All test cases pass

---

## Related Tickets

- Depends on: TASK-100, TASK-100A, TASK-100B, TASK-101, TASK-102
- Blocks: TASK-108, TASK-109

---

## Completion Summary

- Branch: `task/bugops-105-signal-freshness`
- Commits: 
  - c92d88d — initial implementation
  - 83442e3 — fix ObjectId fallback precedence (critical bug fix)
- Changes made:
  - Created `narrative_freshness.py` with `NarrativeFreshnessSignalSource` class
  - Implements two-part freshness check: primary field (`last_summary_generated_at`) + ObjectId fallback
  - Fallback query bounded to 1000 docs, sorted descending by _id, projected to _id only
  - Fallback only checks narratives WITHOUT `last_summary_generated_at` field (prevents overriding stale explicit timestamps)
  - Added `BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES = 120` config
  - Created comprehensive test suite with 20 tests including 2 regression tests for primary/fallback precedence
- Tests run: `poetry run pytest src/tests/bugops/test_narrative_freshness.py -v` — **20 passed**
  - All 5 metadata tests pass
  - All 6 failure condition tests pass
  - All 2 primary-vs-fallback regression tests pass
  - All 4 recovery condition tests pass
  - All tolerance and exception handling tests pass
- Manual verification: All 76 bugops tests pass (no regressions)
- Deviations from plan: 
  - Initial implementation used full collection scan; corrected to bounded query with sort/limit/projection
  - Initial implementation didn't exclude narratives WITH stale `last_summary_generated_at`; added `$exists: False` filter
  - Both deviations caught before merge and fixed with regression tests to prevent recurrence
