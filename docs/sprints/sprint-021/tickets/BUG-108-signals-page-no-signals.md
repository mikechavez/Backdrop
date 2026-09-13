---
ticket_id: BUG-108
title: Investigate empty Signals page despite recent article ingestion
priority: high
status: OPEN
phase: A
date_created: 2026-09-13
branch: null
effort_estimate: medium
---

# BUG-108: Investigate empty Signals page despite recent article ingestion

## Problem Statement

The production Signals page displays “No signals detected yet.” The health endpoint recently reported fresh articles, but the trending-signals API returned no results for the page's effective timeframe. The underlying cause is not yet established; investigate the complete path from article ingestion and entity extraction through `entity_mentions` aggregation and frontend rendering before proposing a fix.

## Production Evidence (2026-09-13)

- `GET /api/v1/signals/trending?limit=15&timeframe=7d` returned HTTP 200 with `count: 0`, `total_count: 0`, and an empty `signals` array at 19:48:58 UTC.
- The same endpoint returned zero signals for `timeframe=24h` at 19:49:14 UTC.
- The endpoint returned one result for `timeframe=30d` at 19:49:16 UTC: Bitcoin, one current-period mention, seven sources, and score 1.17.
- A health response around 19:42 UTC reported `data_freshness.status=ok` and a latest article age of about 0.3 hours. This confirms recent article data, but does not establish that those articles produced recent primary `entity_mentions`.
- `context-owl-ui/src/pages/Signals.tsx` calls `signalsAPI.getSignals()` without a timeframe. The API helper omits undefined filters, and the backend defaults the endpoint to `7d`. The page description says “Most talked-about keywords in the last 24 hours,” so its label and effective query window currently disagree.

## Investigation Plan

1. Inspect production-safe counts and timestamps for recent `articles` and `entity_mentions`, including `created_at`, `is_primary`, entity type, and source. Do not expose article contents or MongoDB credentials in logs or ticket updates.
2. Trace the deployed ingestion and entity-extraction tasks: verify their schedules, dispatch, successful completion, and whether recent articles are yielding primary entity mentions.
3. Compare the API's 24-hour, 7-day, and 30-day calculations with the underlying mention records and cache behavior. Determine why the 30-day query yields one result while the shorter windows yield none.
4. Verify what timeframe the product intends the Signals page to display and reconcile the UI label with the query once the data-path cause is understood.
5. Document a root cause and minimal remediation plan, then verify the API and page with fresh production data after an approved fix.

## Related Work and Scope

- BUG-054 previously addressed a disabled RSS ingestion schedule. Confirm the current production schedule rather than assuming that historical fix guarantees ingestion and entity extraction are healthy now.
- TASK-105 covers freshness monitoring of persisted `signal_scores`; this page's trending endpoint computes results on demand from `entity_mentions`, so TASK-105 alone does not establish this endpoint's health.
- BUG-083 documents a disabled market-event detector. The Signals page endpoint investigated here is the separate trending-entity endpoint; do not assume BUG-083 explains this symptom.
- This ticket is investigation-first. Do not change signal scoring, thresholds, or delete/alter production data until the cause and intended behavior are established.

## Acceptance Criteria

- [ ] The production data path from recent articles to primary entity mentions to trending API results is documented with timestamps/counts.
- [ ] The zero-result behavior for 24-hour and 7-day windows, versus one 30-day result, is explained by evidence.
- [ ] The frontend timeframe label and actual request behavior are reconciled with product intent.
- [ ] A root cause and scoped fix plan are documented; any implementation is verified against tests and production-safe checks.
