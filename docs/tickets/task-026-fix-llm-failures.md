---
ticket_id: TASK-026
title: Fix Active LLM Failures (BUG-052 Resolution)
priority: critical
severity: critical
status: OPEN
date_created: 2026-03-31
branch:
effort_estimate: 3 hr
---

# TASK-026: Fix Active LLM Failures (BUG-052 Resolution)

## Problem Statement

All LLM-dependent systems are non-functional: briefing generation, entity extraction, sentiment analysis. This has been a recurring pattern — systems go down silently and stay down until manually discovered. BUG-052 was created during Sprint 11 with an investigation guide, but the root cause was never identified. TASK-024 audit findings will likely pinpoint the issue.

**Previous known failures:**
- 2026-02-27: Insufficient Anthropic credits (resolved by adding credits)
- 2026-03-11: BUG-052 filed — all LLM systems down, credits ruled out
- Current: LLM spend burning through budget (possibly related)

---

## Task

**Note:** Root cause will be identified by TASK-024. The tasks below cover the fix and hardening work.

### 1. Fix Root Cause
- Based on TASK-024 audit findings, fix the identified root cause of LLM failures
- If multiple issues found, fix in order of impact

### 2. Eliminate Silent Failures
- Audit every LLM call site for error handling (TASK-024 inventory is the map)
- Every failure must be logged with: timestamp, system, model, error type, error message, request context
- No bare `except` blocks — catch specific exceptions
- No swallowed errors — every exception must be logged at minimum, raised or returned as structured error

### 3. Structured Error Responses
- When an LLM call fails, the calling system must return a structured error that propagates to the API/frontend
- Format: `{"error": true, "system": "briefing", "error_type": "api_failure", "message": "...", "timestamp": "..."}`
- Frontend should be able to display meaningful status (not just a blank page or spinner)

### 4. Verify All Three Systems
- After fixes, verify each system works end-to-end:
  - **Briefing generation:** Trigger a briefing, confirm it generates and saves correctly
  - **Entity extraction:** Process a test article, confirm entities are extracted and stored
  - **Sentiment analysis:** Process a test article, confirm sentiment is computed and stored

---

## Verification

- [ ] **Integration tests for each LLM system:**
  - Briefing generation: successful call returns expected output shape and saves to DB
  - Entity extraction: successful call returns entities in expected format
  - Sentiment analysis: successful call returns sentiment score in expected format
  - Each system: failed API call returns structured error (not silent swallow, not unhandled exception)
- [ ] **Error handling audit:**
  - CC confirms every LLM call site in `src/` has proper error handling (no bare except, no swallowed errors)
  - CC lists any error handling changes made, with before/after
- [ ] CC runs all tests and confirms pass before marking complete

---

## Acceptance Criteria

- [ ] Root cause identified and fixed (documented in completion summary)
- [ ] All three LLM systems operational and verified end-to-end
- [ ] No silent failures — every error logged with context
- [ ] Structured error responses propagate to API layer
- [ ] All error handling changes documented (before/after)
- [ ] Integration tests passing for all three systems (happy path + error path)

---

## Impact

Resolves BUG-052 and the recurring pattern of silent LLM failures. Combined with TASK-025 (cost controls), ensures systems stay up and failures are immediately visible.

---

## Related Tickets

- BUG-052: All LLM Systems Non-Functional (this ticket resolves BUG-052)
- TASK-024: LLM Spend Audit (blocks this ticket)
- TASK-025: Implement Cost Controls (parallel work)
- TASK-027: Health Check & Site Status (depends on this ticket)