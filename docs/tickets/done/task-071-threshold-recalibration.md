---
ticket_id: TASK-071
title: Threshold Recalibration — Based on Eval Results + Actual Baseline
priority: high
severity: medium
status: OPEN
date_created: 2026-04-27
effort_estimate: 1-2 hours
---

# TASK-071: Threshold Recalibration — Based on Eval Results + Actual Baseline

## Problem Statement

Current cost thresholds (soft=$0.70, hard=$1.00 per day) were set based on estimates. Actual baseline spend is ~$0.18/day. Additionally, FEATURE-053 (Flash evals) will provide cost data for variant models. Thresholds need recalibration to be realistic and actionable.

---

## Task

### Phase 1: Gather Data

**From TASK-075 (Narrative Cache Investigation):**
- Current baseline spend: $0.18/day (confirmed via cost dashboard)
- After cache fix (if applied): estimated new baseline

**From FEATURE-053 (Flash Evaluations):**
- Cost savings estimate per operation (e.g., "entity_extraction saves $X/day if swapped")
- Variant (Flash) cost per operation
- Projected total spend if X operations swap to Flash

### Phase 2: Calculate New Thresholds

**Soft Threshold (Warning Level):**
- Purpose: Alert when spending is elevated but not critical
- Formula: baseline × 3 to 4
- Rationale: Catches 3-4x normal spend (likely anomaly, needs investigation)
- Example: If baseline=$0.18, soft ≈ $0.54-$0.72

**Hard Threshold (Kill Switch):**
- Purpose: Cut off requests if spending is dangerously high
- Formula: baseline × 5 to 6
- Rationale: Prevents runaway spending beyond 5-6x normal
- Example: If baseline=$0.18, hard ≈ $0.90-$1.08

**Post-Flash Threshold (Optional, for future):**
- If Flash swap is approved for multiple operations, recalculate expected new baseline
- Soft/hard multipliers stay the same, but baseline shifts down (lower thresholds)

### Phase 3: Update Code

**File:** `src/crypto_news_aggregator/services/cost_tracker.py`

**Current:**
```python
DAILY_SOFT_LIMIT = 0.70  # dollars
DAILY_HARD_LIMIT = 1.00  # dollars
```

**Update to:**
```python
# Baseline: ~$0.18/day (as of 2026-04-27)
# Soft threshold: 3.5x baseline = $0.63/day
# Hard threshold: 5.5x baseline = $0.99/day
# These are conservative; actual variance is typically <$0.25/day
DAILY_SOFT_LIMIT = 0.63  # dollars (alert threshold)
DAILY_HARD_LIMIT = 0.99  # dollars (kill switch)
```

**Optional: Add config-driven thresholds**
```python
# config.py
COST_SOFT_LIMIT_MULTIPLIER: float = 3.5  # times baseline
COST_HARD_LIMIT_MULTIPLIER: float = 5.5  # times baseline
COST_BASELINE: float = 0.18  # dollars/day (updated quarterly)

# cost_tracker.py
DAILY_SOFT_LIMIT = settings.COST_BASELINE * settings.COST_SOFT_LIMIT_MULTIPLIER
DAILY_HARD_LIMIT = settings.COST_BASELINE * settings.COST_HARD_LIMIT_MULTIPLIER
```

### Phase 4: Document Decision

Create brief decision note in code comments + ticket:

```python
# TASK-071 Decision (2026-04-28):
# 
# Baseline: $0.18/day (measured from cost dashboard, Feb-Apr 2026)
# Soft threshold: $0.63/day (3.5x baseline, warning level)
# Hard threshold: $0.99/day (5.5x baseline, kill switch)
#
# Rationale:
# - Previous thresholds ($0.70/$1.00) were overestimates
# - Actual variance is typically <$0.25/day
# - 3.5x and 5.5x multipliers provide safety margin without false alarms
# - Post-Flash evaluation: if multiple ops swap, baseline drops to ~$0.12-0.14
#   (recalculate thresholds in Sprint 17)
#
# Override conditions:
# - If evaluation confirms stable Flash swap: update baseline to new cost
# - If variance increases: adjust multipliers (currently conservative)
```

---

## Verification

- [ ] New thresholds based on actual $0.18/day baseline
- [ ] Soft threshold: 3.5-4x baseline (realistic warning level)
- [ ] Hard threshold: 5.5-6x baseline (prevents runaway)
- [ ] Code updated in cost_tracker.py
- [ ] Config supports multiplier-based thresholds (optional, nice-to-have)
- [ ] Decision documented in code comments + TASK-071

---

## Acceptance Criteria

- [ ] Thresholds recalculated using true $0.18/day baseline
- [ ] Soft limit ≤ $0.70 (previous soft, now justified as alert)
- [ ] Hard limit ≤ $1.00 (previous hard, now justified as kill switch)
- [ ] Thresholds are based on visible data (cost dashboard), not estimates
- [ ] Decision rationale documented
- [ ] Unit test: confirm thresholds are applied correctly in cost_tracker

---

## Impact

- Cost monitoring becomes more realistic (fewer false alarms)
- Hard limit actually prevents runaway spending
- Sets foundation for Flash-adjusted thresholds (Sprint 17)

---

## Related Tickets

- TASK-075 (provides baseline cost data)
- FEATURE-053 (provides Flash cost projections)
- Cost tracking system (consumes these thresholds)