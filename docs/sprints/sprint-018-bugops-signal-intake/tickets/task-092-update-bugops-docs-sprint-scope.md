---
ticket_id: TASK-092
title: Update BugOps Docs with Sprint 018 Scope
priority: medium
severity: low
status: DONE
date_created: 2026-05-08
date_completed: 2026-05-08
branch: feature/bugops-signal-intake
effort_estimate: small
---

# TASK-092: Update BugOps Docs with Sprint 018 Scope

## Problem Statement

The BugOps docs need to reflect the final Sprint 018 scope: thinnest end-to-end signal path, SignalSource seam, no correlation engine yet, one-way Slack only, manual-only lifecycle, and Railway log data-shape spike.

---

## Task

Update BugOps docs after implementation decisions are finalized.

### Files to Modify

```text
docs/bugops/00-bugops-system-overview.md
docs/bugops/10-bugops-runtime-model.md
docs/bugops/20-bugops-data-model.md
docs/bugops/30-bugops-observability.md
docs/bugops/80-bugops-use-cases.md
docs/bugops/90-bugops-critiques-and-open-questions.md
```

If these docs live elsewhere, update the actual BugOps doc path used in the repo.

### Required Content Updates

- Add: “Sprint 018 is not trying to solve BugOps. It is trying to prove the smallest end-to-end signal path while preserving the seam for additional signal sources.”
- Clarify: BugOps v1 detects and escalates; it does not autonomously prevent cost cascades.
- Clarify: LLM synthesis is deferred.
- Clarify: Slack in Sprint 018 is outbound webhook only, not Slack UI.
- Clarify: Case lifecycle is manual-only.
- Clarify: Alert-to-case flow is exact `dedupe_key` passthrough, not a correlation engine.
- Add: Cost-runaway dedupe key format: `llm_traces:cost_runaway:{YYYY-MM-DD}:{HH}`.
- Add: `severity` required on `bug_alert_events`.
- Add: Railway log intake is not implemented yet; Sprint 018 only captures real sample output and validates the SignalSource interface.
- Add: BUG-055/056/057 walkthrough is a counterfactual/current-system replay, not literal historical telemetry.

---

## Verification

Manual review:

- [x] Docs no longer imply full case correlation engine in Sprint 018.
- [x] Docs no longer imply Slack UI exists.
- [x] Docs no longer imply BugOps autonomously stops pipelines.
- [x] Docs describe SignalSource seam and Railway log sample spike.

---

## Acceptance Criteria

- [x] All required content updates are present.
- [x] Scope boundaries match Sprint 018 tickets.
- [x] Open questions remain documented for future sprints.

---

## Impact

Keeps implementation and architecture docs aligned so future coding agents do not build beyond v1 scope.

---

## Related Tickets

- FEATURE-056
- FEATURE-057
- FEATURE-058
- FEATURE-059
- TASK-093
