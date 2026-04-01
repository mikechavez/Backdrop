---
ticket_id: TASK-025
title: Implement Cost Controls
priority: critical
severity: high
status: OPEN
date_created: 2026-03-31
branch:
effort_estimate: 3 hr
---

# TASK-025: Implement Cost Controls

## Problem Statement

There are no guardrails preventing runaway LLM spend. When something goes wrong (retry storm, batch re-processing, loop), costs compound silently until the budget is gone. We need per-system limits, circuit breakers, and spend visibility so this can't happen again.

**Note:** Exact scope depends on TASK-024 audit findings. The items below are the expected controls; adjust based on what the audit reveals.

---

## Task

### 1. Per-System Daily Call Limits
- Implement a daily call counter per system (briefing, entity extraction, sentiment, narrative themes)
- Store counts in Redis with daily TTL expiry
- When a system hits its daily limit, reject new calls with a clear error (not silent failure)
- Limits should be configurable via environment variables with sensible defaults

### 2. Per-Request Token Budget
- Enforce explicit `max_tokens` on every API call site identified in TASK-024
- No call should rely on the API default — every call must set `max_tokens` intentionally
- Values should be right-sized per system (briefing needs more tokens than entity extraction)

### 3. Circuit Breaker
- After N consecutive failures for a given system, stop making calls for a cooldown period
- Log when circuit breaker trips and when it resets
- Configurable thresholds: failure count, cooldown duration

### 4. Spend Logging
- Log every LLM API call with: timestamp, system, model, tokens in, tokens out, estimated cost
- Write to existing cost tracking collection (verify it's working — TASK-024 may flag issues)
- Add a daily spend summary that can be queried

---

## Verification

- [ ] **Unit tests:**
  - Rate limiter correctly tracks counts and rejects at limit
  - Circuit breaker trips after N failures, resets after cooldown
  - Token budget enforcement rejects oversized requests
  - Spend logger calculates cost correctly for each model
- [ ] **Integration tests:**
  - System gracefully degrades when daily limit hit (returns structured error, doesn't crash)
  - Circuit breaker trips on simulated consecutive failures, recovers after cooldown
  - Spend logging writes correct data to MongoDB cost tracking collection
- [ ] CC runs all new tests and confirms pass before marking complete

---

## Acceptance Criteria

- [ ] Daily call limits enforced per system with configurable thresholds
- [ ] Every LLM call site has explicit `max_tokens` set
- [ ] Circuit breaker prevents retry storms (configurable failure count + cooldown)
- [ ] Every LLM call logged with model, tokens, and estimated cost
- [ ] All controls fail-open with clear error messages (never silent)
- [ ] All new code has unit and integration tests passing

---

## Impact

Prevents budget blowouts and gives Mike visibility into daily spend. Combined with TASK-027 (health check), creates the foundation for continuous operation.

---

## Related Tickets

- TASK-024: LLM Spend Audit (blocks this ticket — findings shape exact implementation)
- TASK-026: Fix Active LLM Failures
- TASK-027: Health Check & Site Status
- TASK-028: Burn-in Validation