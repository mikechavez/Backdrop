---
ticket_id: TASK-012
title: Remove Unnecessary allowDiskUse=True from Non-Sorting Aggregations
priority: low
severity: low
status: COMPLETED
date_created: 2026-02-24
date_completed: 2026-02-25
branch: docs/bug-041-bug-033-vercel-deployment-fix
commit: 2f535a1
effort_estimate: 15 min
effort_actual: 10 min
---

# TASK-012: Remove Unnecessary allowDiskUse=True from Non-Sorting Aggregations

## Problem Statement

After BUG-036/037/038 remove `$sort` stages from signal pipelines, several aggregation calls retain `allowDiskUse=True` despite having no `$sort`. On Atlas M0, this parameter is silently ignored anyway. Removing it keeps the code honest — no false sense of safety.

---

## Task

Remove `allowDiskUse=True` from aggregation calls that have **no `$sort` stage**:

**signal_service.py:**
- `_count_filtered_mentions()` — ends with `$count`, no `$sort`
- `calculate_source_diversity()` — ends with `$count`, no `$sort`
- `compute_trending_signals()` narrative_counts aggregation — no `$sort`

**signals.py:**
- `get_signals()` narrative_counts aggregation — no `$sort`

**Do NOT remove** from any aggregation that still has a `$sort` stage.

---

## Verification

```bash
# After changes, grep for remaining allowDiskUse and verify each has a $sort
rg -n "allowDiskUse" --type py src/crypto_news_aggregator/services/signal_service.py
rg -n "allowDiskUse" --type py src/crypto_news_aggregator/api/v1/endpoints/signals.py
```

Each remaining instance should be justified by a `$sort` stage in that pipeline.

---

## Acceptance Criteria

- [x] `allowDiskUse=True` removed from aggregations with no `$sort` in signal_service.py
- [x] `allowDiskUse=True` removed from aggregations with no `$sort` in signals.py
- [x] No behavioral change — these aggregations never needed disk-based sort

---

## Impact

Code hygiene only. No functional change. Prevents future confusion about what `allowDiskUse` actually does on M0.

---

## Related Tickets

- BUG-036, BUG-037, BUG-038 (parent fixes)
- BUG-034, BUG-035 (original allowDiskUse additions being superseded)