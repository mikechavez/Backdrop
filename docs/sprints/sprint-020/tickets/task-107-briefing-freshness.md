---
ticket_id: TASK-107
title: Implement BriefingFreshness detector
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-107-briefing-freshness
effort_estimate: medium
---

# TASK-107: Implement BriefingFreshness detector

## Problem Statement

If briefing generation fails, operators and readers receive no briefing without
any alert. Briefings are the primary user-facing output of Backdrop. A missed
briefing is a user-visible failure.

---

## Context

### Five-part definition

| Part | Implementation |
|---|---|
| Last successful output | Most recent `daily_briefings` document `generated_at` within the current window's expected range |
| Expected input or activity | Grace period has elapsed for most recently scheduled window AND fresh narratives exist |
| Failure condition | Grace period elapsed AND no briefing `generated_at` in window range AND fresh narratives exist |
| Legitimate idle condition | Still within grace period, OR no sufficiently fresh narratives |
| Recovery condition | New briefing `generated_at` within expected window after a stall |

### Field names
- Authoritative timestamp: `generated_at` on `daily_briefings` (NOT `inserted_at`)
- Input check: `last_summary_generated_at` on `narratives`

### Schedule design
Briefings run twice daily on a known schedule (not a rolling freshness window).
The detector evaluates which scheduled window most recently elapsed and whether
a briefing exists for that window.

Two configurable schedule windows in EST:
- Morning: `BUGOPS_BRIEFING_MORNING_HOUR_EST` (default `8`) — 8:00 AM
- Evening: `BUGOPS_BRIEFING_EVENING_HOUR_EST` (default `20`) — 8:00 PM

Grace period: `BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES` (default `30`). The Celery
task has a 10-minute hard timeout and retries up to 3 times with 5-minute delays —
worst case ~25 minutes. Do not fire within this grace window.

### EST timezone
Use `from zoneinfo import ZoneInfo` with `ZoneInfo("America/New_York")`.
This is the codebase standard (`zoneinfo` is used in `admin.py`, `briefing_agent.py`).
Do not use `pytz`. Do not hardcode UTC offsets.

### Class interface

```python
class BriefingFreshnessSignalSource:
    source_type = "briefing_freshness"
    root_subsystem = BugOpsSubsystem.BRIEFINGS.value   # "briefings"
    dedupe_key = "briefing_freshness:briefings"
    suggested_manual_check = (
        "Check briefing generation schedule, recent narrative "
        "freshness, and whether a briefing insert was attempted."
    )

    async def check_failure(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def check_recovery(self, db: AsyncIOMotorDatabase) -> bool: ...
    async def collect(self) -> List[BugAlertEventCreate]: return []
```

Severity: `DETECTOR_SEVERITY["briefing_freshness"]` from `severity.py`.

Startup detection: monitor sets `detection_type`; detector is unaware.

---

## Task

1. Create `briefing_freshness.py` in `signal_sources/`
2. Implement `BriefingFreshnessSignalSource`
3. Add required configuration to `core/config.py`
4. Write unit tests covering schedule window logic, grace period, idle vs broken

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/signal_sources/briefing_freshness.py
src/tests/bugops/test_briefing_freshness.py
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

### Scheduled window resolution

- [ ] Convert current UTC time to EST using `ZoneInfo("America/New_York")`
- [ ] Identify the most recently elapsed scheduled hour (morning or evening)
- [ ] Compute `minutes_since_scheduled = (now_est - scheduled_time).total_seconds() / 60`
- [ ] If `minutes_since_scheduled < BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES`: return
  `False` — still in grace period

### Expected input check (precondition)

- [ ] Query `narratives` for any document with `last_summary_generated_at >= now - timedelta(minutes=BUGOPS_BRIEFING_NARRATIVE_LOOKBACK_MINUTES) - timedelta(seconds=60)`
- [ ] If none: return `False` — no input for briefing generation

### Failure condition

- [ ] Query `daily_briefings` for any document with `generated_at` between
  `scheduled_time` and `scheduled_time + timedelta(minutes=BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES) + timedelta(seconds=60)` (tolerance)
- [ ] If document found: return `False` (healthy)
- [ ] If grace period elapsed AND no briefing AND fresh narratives: return `True`

### Recovery condition

- [ ] Same query — `daily_briefings` document in current expected window range
- [ ] Return `True` if found

### Configuration

```python
BUGOPS_BRIEFING_MORNING_HOUR_EST: int = 8
BUGOPS_BRIEFING_EVENING_HOUR_EST: int = 20
BUGOPS_BRIEFING_GRACE_PERIOD_MINUTES: int = 30
BUGOPS_BRIEFING_NARRATIVE_LOOKBACK_MINUTES: int = 240
```

### Test cases

- [ ] Returns `False` when still within grace period of most recently elapsed window
- [ ] Returns `False` when grace period elapsed and a briefing exists in the window
- [ ] Returns `True` when grace period elapsed, no briefing, and fresh narratives exist
- [ ] Returns `False` when grace period elapsed, no briefing, but no fresh narratives
- [ ] Correctly identifies morning window as most recently elapsed between 8AM and 8PM EST
- [ ] Correctly identifies evening window as most recently elapsed after 8PM EST
- [ ] EST/EDT transition does not break logic (use `ZoneInfo`, not hardcoded offset)
- [ ] `check_recovery()` returns `True` when briefing exists in current window
- [ ] `check_recovery()` returns `False` when no briefing in current window
- [ ] Tolerance buffer applied correctly

### Commands to Run

```bash
pytest src/tests/bugops/test_briefing_freshness.py -v
```

---

## Acceptance Criteria

- [ ] `source_type = "briefing_freshness"`, `root_subsystem = "briefings"`, `dedupe_key = "briefing_freshness:briefings"`
- [ ] Uses `generated_at` on `daily_briefings`
- [ ] Evaluates against two daily schedule windows, not a rolling freshness window
- [ ] Does not fire within grace period
- [ ] Does not fire when no fresh narratives
- [ ] Uses `ZoneInfo("America/New_York")` — not `pytz`, not UTC offsets
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
