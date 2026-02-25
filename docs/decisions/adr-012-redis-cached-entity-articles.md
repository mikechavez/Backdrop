# 012. Redis-Cached, Time-Bounded Entity Articles for Signals

**Date:** 2026-02-25\
**Status:** ✅ IMPLEMENTED\
**Deciders:** Mike Chavez\
**Related Tickets:** BUG-045, FEATURE-049, TASK-015, BUG-051, BUG-052, TASK-016

------------------------------------------------------------------------

## Context

The `/api/v1/signals/{entity}/articles` endpoint is experiencing extreme
latency (up to 43--48 seconds) for high-volume entities such as Bitcoin.
This renders the Signals page effectively unusable, despite successful
pagination improvements in BUG-043.

The current implementation performs expensive MongoDB aggregations
(including `$lookup`) against Atlas M0, which is not optimized for heavy
joins or large working sets. Articles do not require real-time
freshness; showing recent (≤7 days) articles is sufficient for product
needs.

Constraints: - Running on MongoDB Atlas M0 (memory and performance
limitations) - Redis already provisioned in architecture - Signals page
must load quickly (\<5s cold, \<1s warm) - Articles should load
interactively without blocking page render

Success criteria: - Entity article load time \< 1s warm cache - Cold
compute \< 3s worst case - No \>10s responses under normal usage - No
excessive Mongo load from concurrent user expansion

------------------------------------------------------------------------

## Decision

We will redesign the `/signals/{entity}/articles` endpoint to:

1.  Enforce a strict **7-day timeframe filter** on entity mentions and
    articles.
2.  Replace Mongo `$lookup`-based aggregation with a **two-pass query
    strategy**:
    -   Query recent `entity_mentions`
    -   Extract unique article IDs
    -   Fetch corresponding articles separately
3.  Cache the resulting entity articles payload in **Redis with a
    15-minute TTL**.
4.  Add a concurrency guard (semaphore) to prevent Mongo stampedes.
5.  Keep lazy-loading behavior in the frontend.

This approach optimizes for perceived performance and system stability
over strict real-time freshness.

------------------------------------------------------------------------

## Alternatives Considered

### Option 1: Keep current aggregation and rely on Mongo optimization

**Description:** Add indexes and retain `$lookup`-based aggregation.

**Pros:** - Minimal refactor - Query logic stays centralized

**Cons:** - Atlas M0 struggles with joins regardless of indexing -
High-variance latency for high-volume entities - Still user-triggered
heavy queries

**Why not chosen:** Does not sufficiently address 40s+ response times
and risks recurring regressions.

------------------------------------------------------------------------

### Option 2: Precompute and store articles inside Signals payload

**Description:** Re-embed recent articles directly into trending signals
computation.

**Pros:** - Single request - No secondary endpoint

**Cons:** - Reintroduces original BUG-043 latency issue - Forces heavy
enrichment for every list page load - Wastes compute when users don't
expand entities

**Why not chosen:** Violates separation introduced in BUG-043 and harms
first-load performance.

------------------------------------------------------------------------

### Option 3 (Chosen): Time-bounded + Redis-cached per-entity endpoint

**Description:** Limit to last 7 days, compute once, cache for 15
minutes in Redis.

**Pros:** - Massive latency reduction - Stable performance regardless of
entity popularity - Leverages existing Redis infrastructure - Matches
product expectations (Signals = recent activity)

**Cons:** - Slight staleness window (≤15 minutes) - Additional cache
invalidation considerations - Adds endpoint complexity

**Why chosen:** Best balance of performance, simplicity, and alignment
with Signals use-case.

------------------------------------------------------------------------

## Consequences

### Positive

-   Articles load in sub-second time after first request
-   No more 40+ second blocking calls
-   Reduced Mongo load on Atlas M0
-   Predictable performance for large entities (e.g., Bitcoin)

### Negative

-   Articles may be up to 15 minutes stale
-   Redis dependency for endpoint correctness
-   Slight increase in backend logic complexity

### Neutral

-   Time-bounding to 7 days reduces historical visibility in Signals
-   Requires monitoring cache hit rate
-   May require future Redis memory tuning

------------------------------------------------------------------------

## Implementation Notes

-   Key file(s) affected:
    -   `api/v1/endpoints/signals.py`
    -   `services/article_service.py` (if extracted)
    -   `core/cache.py` (Redis integration)
-   Migration required: No
-   Breaking changes: No (response shape unchanged)
-   Documentation updated: Yes (Signals + Performance section)

Technical changes: - Enforce `published_at >= now - 7 days` - Replace
`$lookup` with: -
`entity_mentions.find({entity, created_at >= cutoff}).sort(created_at desc).limit(N)` -
Extract article IDs - `articles.find({_id: {$in: ids}})` - Redis key:
`signals:articles:v1:{entity}:{limit}:7d` - TTL: 900 seconds - Add async
semaphore cap (5--10 concurrent article fetches)

------------------------------------------------------------------------

## Validation

We will consider this decision successful if:

-   Cold entity article request \< 3s
-   Warm (cached) entity article request \< 300ms
-   No article request exceeds 5s under normal load
-   Signals list page remains \< 5s cold
-   Mongo CPU / query time drops measurably
-   Redis cache hit rate ≥ 70% for entity articles

------------------------------------------------------------------------

## References

-   BUG-043 performance analysis
-   MongoDB Atlas M0 aggregation limitations
-   Internal system architecture documentation
-   Redis already provisioned in architecture stack

------------------------------------------------------------------------

## Implementation Status

### Phase 1: Time-Bounded Cutoff ✅ COMPLETE
- **Ticket:** BUG-045
- **PR:** #203
- **Commit:** bf601df
- **What:** Enforced 7-day cutoff at MongoDB `$match` stage (before `$group`)
- **Files:** `services/signal_scores.py` (lines 168-170)
- **Result:** Entity articles <1s warm, <3s cold (Bitcoin/Ethereum)

### Phase 2: Redis Caching ✅ COMPLETE
- **Ticket:** FEATURE-049
- **PR:** #206
- **Commit:** d223b90
- **What:** Added Redis cache layer with 15-minute TTL (900s)
- **Files:** `api/v1/endpoints/signals.py` (lines 619-670)
- **Cache key:** `signals:articles:v1:{entity}:{limit}:7d`
- **Result:** Warm cache hits <200ms

### Phase 3: Cache Warmer ✅ COMPLETE
- **Ticket:** TASK-015
- **PR:** #207
- **What:** Preload high-traffic entity articles at startup
- **Result:** First user never sees cold cache; cache pre-warmed

### Phase 4: UI Cleanup ✅ COMPLETE
- **Ticket:** BUG-051
- **PR:** #208
- **What:** Removed "(X of Y)" count display from Signals header and signal cards
- **Result:** Cleaner UI, faster perceived load time

### Phase 5: Observability & Parameter Validation ✅ COMPLETE
- **Ticket:** TASK-016
- **Branch:** fix/task-016-observability-clamps
- **Commits:** fad129a, a420bdd
- **What:**
  - Fixed duplicate logging (removed redundant `basicConfig()` call)
  - Added comprehensive observability logging with format: `operation: key1=value1, key2=value2`
  - Parameter clamping: limit≤20, days≤7 with clamp logging
  - Verified zero duplicate log messages with tests
- **Files:** `main.py`, `api/v1/endpoints/signals.py`, `tests/test_task_016_observability.py`
- **Result:** Full performance monitoring visibility for ADR-012 goals

### Bonus: UI Polish ✅ COMPLETE
- **Ticket:** BUG-052
- **Commit:** 25f1558
- **What:** Fixed "Recent mentions" two-click expansion issue
- **Result:** Single-click expansion with hover styling

## Performance Outcomes

✅ **Signals page:** <5s cold (from original 52s)
✅ **Entity articles:** <1s warm, <3s cold (from original 40-48s)
✅ **Redis cache hit rate:** Targeting ≥70%
✅ **Zero duplicate log messages:** Verified with tests
✅ **No 10s+ backend calls:** Achieved across all endpoints

## Follow-up

- [x] Implement two-pass query strategy
- [x] Add Redis cache with 15m TTL
- [x] Add parameter clamp validation
- [x] Add comprehensive observability logging
- [x] Fix duplicate logging setup
- [x] Add cache warmer for high-traffic entities
- [x] Add UI polish for signal expansion
- [ ] Monitor performance for 7 days (in progress)
- [ ] Review decision in 30 days
