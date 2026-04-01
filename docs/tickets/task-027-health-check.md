---
ticket_id: TASK-027
title: Health Check & Site Status
priority: high
severity: medium
status: OPEN
date_created: 2026-03-31
branch:
effort_estimate: 2 hr
---

# TASK-027: Health Check & Site Status

## Problem Statement

There's no way to know if Backdrop is healthy without manually testing each system. When hiring managers visit the site, there's no indicator of whether data is fresh and systems are running. When something breaks, Mike discovers it days later by accident. The site needs a health check endpoint and a visible status indicator.

---

## Task

### 1. `/health` Endpoint
- Add a `GET /health` endpoint that checks all subsystems:
  - **API key valid:** Anthropic API key is set and not empty
  - **Database connected:** MongoDB is reachable and responding
  - **Redis connected:** Redis is reachable and responding
  - **LLM callable:** A lightweight ping to the Anthropic API (use cheapest model, minimal tokens — not a full briefing generation)
  - **Celery workers alive:** At least one worker is responding
  - **Data freshness:** Most recent article ingested within expected timeframe (e.g., last 24 hours)
- Response format:
  ```json
  {
    "status": "healthy" | "degraded" | "unhealthy",
    "timestamp": "...",
    "checks": {
      "database": {"status": "ok", "latency_ms": 12},
      "redis": {"status": "ok", "latency_ms": 3},
      "llm": {"status": "ok", "model": "claude-haiku-..."},
      "celery": {"status": "ok", "workers": 2},
      "data_freshness": {"status": "ok", "latest_article": "..."}
    }
  }
  ```
- Overall status: `healthy` if all pass, `degraded` if non-critical checks fail, `unhealthy` if critical checks fail (DB, LLM)
- Endpoint should not require authentication (it's a status page)

### 2. Frontend Status Indicator
- Simple visual indicator on the Backdrop frontend (green/yellow/red dot or banner)
- Polls `/health` on page load (not continuously — one check per visit)
- Green: all systems healthy. Yellow: degraded (some non-critical checks failing). Red: unhealthy
- If health check itself fails (network error), show grey/unknown state

### 3. LLM Ping Cost Control
- The LLM health check must use the cheapest model available with minimal tokens (e.g., "respond with OK", max_tokens=5)
- Must not run more than once per health check request (no retry on health ping)
- Cost per health check should be effectively zero

---

## Verification

- [ ] **Unit tests:**
  - Health endpoint returns correct structure
  - Overall status logic: healthy when all pass, degraded when non-critical fails, unhealthy when critical fails
  - Each individual check handles timeout/failure gracefully
- [ ] **Integration tests:**
  - Health endpoint returns 200 with all checks when systems are up
  - Simulate one subsystem down — confirm degraded/unhealthy response (not crash)
  - LLM ping uses cheap model and minimal tokens (verify model string and max_tokens in test)
- [ ] CC runs all tests and confirms pass before marking complete

---

## Acceptance Criteria

- [ ] `GET /health` endpoint returns structured status for all subsystems
- [ ] Overall status correctly reflects system health (healthy/degraded/unhealthy)
- [ ] Frontend displays status indicator based on health endpoint
- [ ] LLM health ping costs effectively zero per check
- [ ] Health endpoint handles subsystem failures gracefully (no crashes, no hangs)
- [ ] All new code has unit and integration tests passing

---

## Impact

Gives Mike (and hiring managers visiting the site) immediate visibility into whether Backdrop is operational. Combined with TASK-025 cost controls and TASK-026 error handling, creates a system that surfaces problems instead of hiding them.

---

## Related Tickets

- TASK-026: Fix Active LLM Failures (should be done first so health check has something healthy to check)
- TASK-025: Implement Cost Controls (health check LLM ping must respect cost controls)
- TASK-028: Burn-in Validation (health endpoint is a key monitoring tool during burn-in)