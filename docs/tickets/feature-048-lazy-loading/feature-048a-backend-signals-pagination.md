---
id: FEATURE-048a
type: feature
status: open
priority: high
complexity: medium
created: 2026-02-24
updated: 2026-02-24
parent: FEATURE-048
---

# Backend Signals Pagination

## Problem/Opportunity
The `/api/v1/signals/trending` endpoint returns all signals in a single payload. Even after BUG-040 reduced load time from 45s to ~10s, users wait for the full response before seeing any content. Adding server-side pagination enables the frontend to request smaller slices and render progressively.

## Proposed Solution
Add offset-based pagination to the trending signals endpoint. Compute and cache the full enriched signal set (up to 100), then return paginated slices from cache. This keeps subsequent page requests fast (cache hit) while reducing initial payload size.

Corresponds to **Implementation Spec Part 1** (sections 1A–1D).

## User Story
As a Backdrop user, I want the signals API to support pagination so the frontend can load signals incrementally instead of waiting for the entire dataset.

## Acceptance Criteria
- [ ] `GET /api/v1/signals/trending` accepts `offset` param (default 0) and `limit` defaults to 15 (was 50)
- [ ] Response includes `total_count`, `offset`, `limit`, `has_more` fields
- [ ] Cache key excludes offset/limit (bumped to v3) so all pages share one cache entry
- [ ] Cache hit path returns paginated slice with correct metadata
- [ ] Full signal set (up to 100) is computed, enriched, and cached; pagination applied after
- [ ] `GET /api/v1/signals/trending` returns 15 items, `has_more: true`, `offset: 0`
- [ ] `GET /api/v1/signals/trending?offset=15` returns next 15, `offset: 15`
- [ ] `GET /api/v1/signals/trending?offset=45` returns remainder, `has_more: false`
- [ ] Second request within 60s returns `cached: true`
- [ ] Existing filters (min_score, entity_type, timeframe) still work

## Dependencies
- None (can be implemented independently)

## Open Questions
- None — spec is fully defined

## Implementation Notes
**File:** `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

Key changes:
1. **1A** — Add `offset` param to function signature, change `limit` default 50→15
2. **1B** — Always compute full set (`max_compute=100`), paginate after
3. **1C** — Cache key `signals:trending:v3:...` excludes offset/limit; cache hit returns slice
4. **1D** — Enrich all signals, cache full enriched list, return `page_signals[offset:offset+limit]` with pagination metadata

See `FEATURE-048-implementation-spec.md` Part 1 for exact code changes.

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: