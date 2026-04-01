---
ticket_id: TASK-028
title: Burn-in Validation (72hr)
priority: high
severity: medium
status: OPEN
date_created: 2026-03-31
branch:
effort_estimate: 1 hr (setup, then 72hr passive monitoring)
---

# TASK-028: Burn-in Validation (72hr)

## Problem Statement

Backdrop has a pattern of working after a fix, then breaking again days later. Before moving to Phase 2 (NeMo integration), we need to prove the system is stable under normal operating conditions for a sustained period. This is the gate between Phase 1 and Phase 2.

---

## Task

### 1. Define Burn-in Criteria
Before starting the 72-hour window, confirm these are passing:
- All three LLM systems operational (TASK-026 complete)
- Cost controls in place (TASK-025 complete)
- Health endpoint live (TASK-027 complete)
- Celery beat schedule running normally

### 2. Monitor for 72 Hours
Track the following daily:
- **Uptime:** Health endpoint returns `healthy` or `degraded` (not `unhealthy`) on each check
- **LLM spend:** Daily cost stays under the target set after TASK-024 audit
- **Briefing generation:** At least one successful briefing generated per day
- **Error rate:** No unhandled exceptions or silent failures in logs
- **Data freshness:** Articles being ingested within expected timeframe

### 3. Document Results
Write a burn-in report to `docs/_generated/evidence/14-burn-in-report.md` with:
- **Summary:** Pass/fail against each criterion
- **Daily snapshots:** Key metrics for each of the 3 days
- **Issues found:** Any anomalies, even if they didn't cause failure
- **Phase 2 readiness:** Explicit go/no-go recommendation

---

## Verification

- [ ] Burn-in criteria confirmed met before starting the 72hr window
- [ ] Daily check performed for all 3 days (can be manual or automated)
- [ ] Burn-in report written to `docs/_generated/evidence/14-burn-in-report.md`
- [ ] Report includes explicit Phase 2 go/no-go

---

## Acceptance Criteria

- [ ] System runs 72 hours without manual intervention
- [ ] No `unhealthy` status from health endpoint during the window
- [ ] Daily LLM spend within target budget for all 3 days
- [ ] At least one successful briefing generated per day
- [ ] No silent failures or unhandled exceptions in logs
- [ ] Burn-in report complete with go/no-go for Phase 2

---

## Impact

This is the Phase 1 → Phase 2 gate. If burn-in passes, Backdrop is stable enough to layer on NeMo instrumentation without risking the site. If it fails, we know what to fix before proceeding.

---

## Related Tickets

- TASK-025: Implement Cost Controls (must be complete)
- TASK-026: Fix Active LLM Failures (must be complete)
- TASK-027: Health Check & Site Status (must be complete)
- TASK-029: NeMo Research & Integration Plan (unblocked by this ticket passing)