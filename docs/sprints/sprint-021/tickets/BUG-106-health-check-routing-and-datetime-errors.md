---
ticket_id: BUG-106
title: Health check endpoint reports LLM routing and datetime offset errors
priority: medium
status: OPEN
phase: A
date_created: 2026-09-11
branch: null
effort_estimate: small
---

# BUG-106: Health check endpoint reports LLM routing and datetime offset errors

## Problem Statement

Health endpoint `/api/v1/health` reports two errors during checks:

1. **LLM Check Error:** `Operation 'health_check' has no routing strategy. Available: ['narrative_generate', 'entity_extracti...`
2. **Pipeline Check Error:** `Failed to check pipeline heartbeats: can't subtract offset-naive and offset-aware datetimes`

These errors were observed at 2026-09-11T20:26:48Z during BUG-105 MongoDB recovery verification. They are pre-existing and unrelated to the storage quota cleanup.

## Observations

- Database and Redis health checks pass
- Data freshness check passes
- Errors appear to be in LLM gateway routing and pipeline timestamp handling
- Service startup completes successfully despite errors

## Next Steps

Investigate:
- Why `health_check` operation is not registered in LLM routing
- Pipeline heartbeat datetime timezone handling in health checks

---

**Linked to:** BUG-105 (MongoDB storage quota recovery)
