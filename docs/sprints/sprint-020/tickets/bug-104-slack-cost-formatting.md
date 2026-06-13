---
id: BUG-104
type: bug
status: backlog
priority: low
severity: low
created: 2026-06-12
updated: 2026-06-12
---

# Cost Runaway Alert Rounds Small Dollar Amounts To $0.00

## Problem

Cost runaway alerts display "$0.00" in the Slack summary when actual spend is greater than zero but less than one cent.

## Expected Behavior

Small values should be displayed with sufficient precision to understand why the alert fired.

Example:

```text
5min spend: $0.004
```

## Actual Behavior

Slack alert displays:

```text
5min spend: $0.00
```

while metrics show:

```text
last_5_min_spend: 0.004149
```

## Steps to Reproduce

1. Lower BugOps cost thresholds
2. Trigger cost runaway detector
3. Observe Slack alert
4. Spend rounds to $0.00 despite non-zero spend

## Environment

- Environment: production
- User impact: low

## Screenshots/Logs

Observed during TASK-100C verification.

---

## Resolution

**Status:** Open
**Fixed:** TBD
**Branch:**
**Commit:**

### Root Cause

Slack formatter rounds currency values to two decimal places.

### Changes Made

TBD

### Testing

TBD

### Files Changed

TBD
