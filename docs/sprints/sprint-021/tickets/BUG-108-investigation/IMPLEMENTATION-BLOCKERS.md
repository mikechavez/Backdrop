# Implementation Blockers & Operator Decisions Required

## Status of Review Findings

✅ **Finding 1: MongoDB client lifecycle synchronization** — FIXED
- Assign _async_client and _client_loop atomically after ping
- ArticleService.close() no longer closes shared mongo_manager client  
- Tests verify synchronization and error cleanup
- Commit: dc115f8

✅ **Finding 2: Duplicate error handling** — IMPROVED
- Check error.details['index'] instead of string matching
- Distinguish URL duplicates from other unique constraints
- No raw exception text in error logs
- Fallback to structured error message parsing

✅ **Finding 3: Enrichment query test** — FIXED
- Test now uses AST inspection of production code
- Verifies actual query has: created_at, sort(-1), limit()
- No hardcoded duplicate example dictionary

## Remaining Work: Durable Enrichment State Machine

The state machine is **mandatory** per BUG-108 Definition of Done (section 2). 

### What's Designed

Complete design document created: `ENRICHMENT-STATE-MACHINE-DESIGN.md`

Covers:
- Article state schema (pending → claimed → completed|skipped|failed_retryable|failed_terminal)
- Atomic claim with lease tokens (prevents concurrent processing)
- Idempotent mention writes (upsert strategy)
- Exponential backoff retry policy (5, 10, 20 min)
- Fairness mechanism (rotational oldest-first recovery)
- Legacy migration (bounded, observable initialization)
- Testing strategy (9 test categories)

### What Needs Operator Decision

Before implementation can proceed, operator must choose:

#### 1. Lease Duration
How long until a claimed article's lease expires and becomes reclaimable by another worker?

**Default suggestion**: 30 minutes
**Rationale**: 
- Should be longer than max extraction time (usually < 10 min per article batch)
- Prevents false lease recovery if worker is just slow
- Still recovers stale work within reasonable time

**Decision needed**: Approve 30 min, or choose different value

#### 2. Max Retry Attempts
How many times should a failing article be retried before giving up?

**Default suggestion**: 3 attempts total
**Rationale**:
- Temporary failures (network timeout, LLM overload) often succeed on retry
- 3 attempts = original + 2 retries; avoids infinite loops on broken articles
- Balances resilience vs. speed

**Decision needed**: Approve 3, or choose different value

#### 3. Retry Backoff
Initial backoff time before first retry?

**Default suggestion**: 5 minutes (exponential: 5, 10, 20)
**Rationale**:
- 5 min waits for transient failures to clear (network glitches, service recovery)
- Exponential growth prevents hammering on permanent failures
- Capped at lease duration (30 min) to avoid infinite waits

**Decision needed**: Approve 5 min, or choose different value

#### 4. Article Selection Strategy (Fairness)
How to ensure older articles don't starve while prioritizing fresh ones?

**Default suggestion**: Rotational (every 3rd run prioritize oldest)
**Rationale**:
- Every run: newest-first (prioritizes fresh articles)
- Every 3rd run: oldest-first (ensures older articles progress)
- Prevents indefinite starvation of backlog
- Remains responsive to new articles

**Alternative**: Always oldest-first
- Guarantees fairness
- Slower on fresh articles

**Decision needed**: Approve rotational, or choose alternative

#### 5. Age Cutoff Confirmation
**Default**: ENRICHMENT_AGE_CUTOFF_DAYS = 30 (already in settings)
**Effect**: Articles older than 30 days will NOT be automatically enriched

**Decision needed**: Confirm 30 days is acceptable, or choose different value

## Implementation Roadmap (Post-Decision)

Once operator approves the 5 decisions above:

1. **Add enrichment_state field to Article model** (5 min)
   - Pydantic model with state enum

2. **Add configuration values** (5 min)
   - ENRICHMENT_LEASE_DURATION_MINUTES
   - ENRICHMENT_MAX_RETRY_ATTEMPTS
   - ENRICHMENT_RETRY_BACKOFF_MINUTES
   - Fairness strategy option

3. **Implement enrichment operations** (2-3 hours)
   - Claim: atomic compare-and-set
   - Complete: idempotent mention writes
   - Fail: retry backoff calculation
   - Migrate legacy articles

4. **Update rss_fetcher.py** (1-2 hours)
   - Query builder with state machine logic
   - Claim loop for each article
   - Success/failure/retry paths
   - Fairness strategy implementation

5. **Write comprehensive tests** (2-3 hours)
   - 9 test categories per design
   - Concurrency tests (two workers)
   - Idempotency verification
   - Retry boundary tests
   - Fairness verification

6. **Local testing** (1 hour)
   - All new tests pass
   - Backward compatibility verified
   - No regressions on existing suite

7. **Staging validation** (requires operator approval for staging writes)
   - Deploy to staging
   - Ingest test articles
   - Verify state transitions
   - Verify signal generation end-to-end

**Total estimated effort**: 6-8 hours implementation + testing (pending approval)

## What Cannot Proceed Without These Decisions

- ✅ Code review findings (client lifecycle, error handling, tests) — complete
- ✅ UI-API timeframe alignment — complete
- ✅ Duplicate URL error narrowing — complete
- ❌ State machine implementation — blocked on operator decisions
- ❌ Staging validation — blocked on state machine
- ❌ Production deployment — blocked on staging validation + operator approval

## How to Proceed

1. Operator reviews ENRICHMENT-STATE-MACHINE-DESIGN.md
2. Operator makes decisions on the 5 items above
3. Operator approves the design and decisions
4. Implementation proceeds (6-8 hours)
5. Local tests verify all functionality
6. Staging validation confirms end-to-end flow
7. Production deployment approved by operator

**Do not proceed with implementation until operator approves all 5 decisions.**
