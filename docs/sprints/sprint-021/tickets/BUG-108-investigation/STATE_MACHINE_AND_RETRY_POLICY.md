# BUG-108: State Transitions, Retry Policy, and Interrupt Safety

**Problem with previous design:** Two unstated guarantees that don't hold.

1. **"No article selected twice"** — False if process crashes before writing `enrichment_attempted_at`. Article is re-selected after restart.
2. **"Permanently mark failed articles"** — Dangerous for transient failures (LLM rate limit, DB timeout, network glitch).

This document defines correct state transitions, explicit retry policy, and interrupt-safe design.

---

## State Machine: Article Enrichment Lifecycle

Each article progresses through explicit states. A new field `enrichment_state` tracks this:

```
enrichment_state: {
  status: "pending" | "in_progress" | "completed" | "failed",
  last_attempt: <timestamp> | null,
  attempt_count: <int>,
  error: <string> | null,
  completed_at: <timestamp> | null
}
```

### State Definitions

| State | Meaning | Next State | Retry? |
|-------|---------|-----------|--------|
| **pending** | Never attempted | in_progress | Yes, on startup |
| **in_progress** | Processing now (or crashed mid-processing) | completed, failed | Depends on age |
| **completed** | Article fully processed (tier 1 enriched, tier 2/3 classified, or explicitly skipped) | Never | No |
| **failed** | Transient error (rate limit, DB timeout, etc.) | in_progress | Yes, up to max_attempts |

### State Transitions with Safety

**Startup query:** Fetch articles eligible for processing:
```javascript
enrichment_state: { $in: [
  { status: "pending" },
  // in_progress older than 60 seconds (crashed/hung process)
  { status: "in_progress", last_attempt: { $lt: <60s ago> } },
  // failed with attempt_count < max_attempts and backoff satisfied
  { status: "failed", attempt_count: { $lt: 3 }, last_attempt: { $lt: <backoff time> } }
]}
```

**Before processing:** Atomically set `status: in_progress` and `last_attempt: now`:
```python
result = await collection.find_one_and_update(
    {"_id": article_id, "enrichment_state.status": "pending"},
    {"$set": {
        "enrichment_state.status": "in_progress",
        "enrichment_state.last_attempt": datetime.now(timezone.utc),
        "enrichment_state.attempt_count": {"$inc": 1}
    }},
    return_document=ReturnDocument.AFTER
)
if result is None:
    # Article was already claimed by another process or moved to completed
    skip_this_article()
```

**After successful processing:** Set `status: completed`:
```python
await collection.update_one(
    {"_id": article_id},
    {"$set": {
        "enrichment_state.status": "completed",
        "enrichment_state.completed_at": datetime.now(timezone.utc),
        "relevance_score": ...,
        "relevance_tier": ...,
        # ... other enrichment fields ...
    }}
)
```

**After transient error:** Increment attempt count, set `status: failed`:
```python
await collection.update_one(
    {"_id": article_id},
    {"$set": {
        "enrichment_state.status": "failed",
        "enrichment_state.error": str(exception),
        "enrichment_state.last_attempt": datetime.now(timezone.utc),
        # attempt_count already incremented
    }}
)
```

**After max retries exceeded:** Set `status: completed` with error marker (prevents infinite retry):
```python
if enrichment_state["attempt_count"] >= MAX_RETRY_ATTEMPTS:
    await collection.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "completed",
            "enrichment_state.error": "max_retries_exceeded",
            "enrichment_state.completed_at": datetime.now(timezone.utc),
            # No enrichment fields set; article permanently skipped
        }}
    )
```

---

## Retry Policy: Bounded Attempts with Backoff

### Configuration

```python
MAX_RETRY_ATTEMPTS = 3           # Try failed article up to 3 times
RETRY_BACKOFF_MINUTES = [0, 5, 30]  # Backoff: immediate, 5min, 30min
STALE_IN_PROGRESS_SECONDS = 60   # Assume hung if in_progress > 60s
```

### Backoff Schedule

| Attempt | Delay | Total Retries | Reason |
|---------|-------|----------------|--------|
| 1 | Immediate | 1st try on startup | Transient error (rate limit hit, recovers quickly) |
| 2 | 5 min | Try again after provider recovers | Persistent rate limit or DB contention |
| 3 | 30 min | Try once more after cooldown | Network glitch or provider incident |
| 4+ | STOP | Max retries reached | Permanent failure; mark as completed with error |

### Backoff Calculation

```python
async def is_article_eligible_for_retry(article):
    state = article.get("enrichment_state", {})
    
    if state.get("status") != "failed":
        return False
    
    attempt_count = state.get("attempt_count", 0)
    if attempt_count >= MAX_RETRY_ATTEMPTS:
        return False  # Max retries exceeded
    
    last_attempt = state.get("last_attempt")
    if not last_attempt:
        return True  # Never attempted yet (shouldn't happen in failed state)
    
    backoff_index = attempt_count - 1  # 0-indexed
    if backoff_index >= len(RETRY_BACKOFF_MINUTES):
        return False  # Out of backoff schedule
    
    backoff_minutes = RETRY_BACKOFF_MINUTES[backoff_index]
    required_wait = timedelta(minutes=backoff_minutes)
    time_since_attempt = datetime.now(timezone.utc) - last_attempt
    
    return time_since_attempt >= required_wait
```

### Retry Query

```python
def get_retry_eligible_articles(db):
    now = datetime.now(timezone.utc)
    sixty_seconds_ago = now - timedelta(seconds=60)
    
    # Articles stuck in_progress for >60s (crashed process)
    hung_articles = {
        "enrichment_state.status": "in_progress",
        "enrichment_state.last_attempt": {"$lt": sixty_seconds_ago}
    }
    
    # Articles failed and ready for retry (backoff satisfied)
    # For simplicity: 0min, 5min, 30min backoff
    five_min_ago = now - timedelta(minutes=5)
    thirty_min_ago = now - timedelta(minutes=30)
    
    retry_1_ready = {
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": {"$eq": 1},
        # Ready immediately (no wait for first retry)
    }
    
    retry_2_ready = {
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": {"$eq": 2},
        "enrichment_state.last_attempt": {"$lt": five_min_ago}
    }
    
    retry_3_ready = {
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": {"$eq": 3},
        "enrichment_state.last_attempt": {"$lt": thirty_min_ago}
    }
    
    return {
        "$or": [
            hung_articles,
            retry_1_ready,
            retry_2_ready,
            retry_3_ready,
        ]
    }
```

---

## Interrupt Safety: Mid-Batch Crash Scenarios

### Scenario 1: Crash Before Setting `in_progress`

**Process:** Start enrichment cycle → Load 500 articles → Crash before any state update

**Result:** 
- ❌ Articles still have `status: pending`
- ✅ Next restart: Same articles are re-loaded (legitimate retry)
- ✅ Safety: No data loss, just re-processing (acceptable for transient crash)

**Mitigation:** Keep cycles short (<10 min) so restart happens relatively quickly.

### Scenario 2: Crash After Setting `in_progress`, Before `completed`

**Process:** Article loaded → State set to `in_progress` → Tier classified → **Crash before `completed` is written**

**Result:**
- ❌ Article stuck with `status: in_progress`, `last_attempt: T`
- ✅ After 60s: Eligible for retry (detected as hung)
- ✅ Next cycle: Article re-processed
- **Trade-off:** Short delay (60s) before re-attempt, but guarantees no orphaned articles

### Scenario 3: Batch Partial Success

**Process:** Process 500 articles → Articles 1-250 marked `completed` → Articles 251-500 marked `in_progress` → **Crash**

**Result:**
- ✅ Articles 1-250: Completed (won't be re-selected)
- ❌ Articles 251-500: In `in_progress` state
- ✅ After 60s: Detected as hung, re-eligible for processing
- ✅ Next cycle: Only articles 251-500 re-processed (progress is preserved)

**Guarantee:** At least 250 articles made progress; none re-processed unnecessarily.

### Scenario 4: Intentional Restart (Deployment)

**Process:** Running → Container stops → New version starts

**Result:**
- Articles in `in_progress`: Detected as hung (process crashed), re-attempted after 60s
- Articles in `completed`: Already completed, skipped
- Articles in `failed`: Retried based on backoff schedule
- Articles in `pending`: Processed normally

**No duplicate work:** Only articles that failed to reach `completed` are re-attempted.

---

## Test Cases: Local Unit Tests (No Staging Required)

### Test 1: Happy Path - Tier 1 Article Processes Successfully

```python
async def test_tier_1_successful_completion():
    """Article processes to completed state without re-selection."""
    
    article_id = ObjectId()
    
    # Initial state
    article = {
        "_id": article_id,
        "title": "Tier 1 Article",
        "enrichment_state": {"status": "pending"}
    }
    
    # Before processing: Query finds article
    eligible = await db.articles.find_one({
        "_id": article_id,
        "enrichment_state.status": "pending"
    })
    assert eligible is not None
    
    # Set in_progress atomically
    result = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "pending"},
        {"$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": datetime.now(timezone.utc),
        }}
    )
    assert result is not None  # Atomic update succeeded
    
    # Simulate processing
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "completed",
            "enrichment_state.completed_at": datetime.now(timezone.utc),
            "relevance_score": 0.8,
            "relevance_tier": 1,
        }}
    )
    
    # After processing: Article NOT re-selected
    eligible_again = await db.articles.find_one({
        "_id": article_id,
        "enrichment_state.status": "pending"
    })
    assert eligible_again is None  # ✅ Correctly excluded
    
    print("✅ Test 1 passed: Tier 1 article completed and not re-selected")
```

### Test 2: Tier 2/3 Article Skipped But Marked Completed

```python
async def test_tier_2_3_marked_completed():
    """Tier 2/3 article is classified then marked completed (not re-selected)."""
    
    article_id = ObjectId()
    
    # Set in_progress
    await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "pending"},
        {"$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": datetime.now(timezone.utc),
        }}
    )
    
    # Simulate: Classify as tier 2, then mark completed (enrichment skipped)
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "completed",  # ← KEY: Still marked completed
            "enrichment_state.completed_at": datetime.now(timezone.utc),
            "relevance_tier": 2,  # Only tier is set
            # Note: relevance_score, sentiment_score NOT set
        }}
    )
    
    # Article NOT re-selected in future cycles (despite missing fields)
    eligible_again = await db.articles.find_one({
        "_id": article_id,
        "enrichment_state.status": {"$in": ["pending", "failed"]}
    })
    assert eligible_again is None  # ✅ Correctly excluded
    
    print("✅ Test 2 passed: Tier 2/3 article marked completed, not re-selected")
```

### Test 3: Crash Mid-Batch - In_progress Article Detected as Hung

```python
async def test_hung_in_progress_detected():
    """Article stuck in in_progress state is detected as hung after 60s."""
    
    article_id = ObjectId()
    
    # Article was in-progress but crashed before completion
    past_time = datetime.now(timezone.utc) - timedelta(seconds=65)  # >60s ago
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": past_time,
            "enrichment_state.attempt_count": 1
        }}
    )
    
    # Next cycle: Query for eligible articles includes hung ones
    stale_threshold = datetime.now(timezone.utc) - timedelta(seconds=60)
    hung_articles = await db.articles.find({
        "enrichment_state.status": "in_progress",
        "enrichment_state.last_attempt": {"$lt": stale_threshold}
    }).to_list(10)
    
    found = any(doc["_id"] == article_id for doc in hung_articles)
    assert found  # ✅ Hung article detected and eligible for re-attempt
    
    print("✅ Test 3 passed: Hung article detected after 60s stale threshold")
```

### Test 4: Transient Failure with Backoff

```python
async def test_failure_retry_with_backoff():
    """Article fails, is retried with backoff schedule."""
    
    article_id = ObjectId()
    
    # Attempt 1: Failed
    time_attempt_1 = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.error": "rate_limit_exceeded",
            "enrichment_state.last_attempt": time_attempt_1,
            "enrichment_state.attempt_count": 1
        }}
    )
    
    # Immediately after failure: Not yet eligible for retry 2 (backoff not satisfied)
    time_now_2min_later = datetime.now(timezone.utc)
    retry_2_ready = await db.articles.find({
        "_id": article_id,
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 1,
        # No backoff check; ready immediately for first retry
    }).to_list(1)
    assert len(retry_2_ready) > 0  # ✅ Eligible for immediate retry
    
    # Simulate: Retry attempt 2 fails
    time_attempt_2 = datetime.now(timezone.utc)
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.error": "rate_limit_exceeded",
            "enrichment_state.last_attempt": time_attempt_2,
            "enrichment_state.attempt_count": 2
        }}
    )
    
    # After attempt 2: Not eligible for retry 3 (needs 5min backoff)
    now = datetime.now(timezone.utc)
    five_min_ago = now - timedelta(minutes=5)
    retry_3_too_soon = await db.articles.find({
        "_id": article_id,
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 2,
        "enrichment_state.last_attempt": {"$lt": five_min_ago}  # Needs to be older
    }).to_list(1)
    assert len(retry_3_too_soon) == 0  # ✅ Backoff prevents immediate retry
    
    # Simulate waiting 5+ minutes
    time_attempt_2_old = now - timedelta(minutes=6)
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {"enrichment_state.last_attempt": time_attempt_2_old}}
    )
    
    # Now eligible for retry 3
    retry_3_ready = await db.articles.find({
        "_id": article_id,
        "enrichment_state.status": "failed",
        "enrichment_state.attempt_count": 2,
        "enrichment_state.last_attempt": {"$lt": five_min_ago}
    }).to_list(1)
    assert len(retry_3_ready) > 0  # ✅ After backoff, eligible for retry
    
    print("✅ Test 4 passed: Failures retry with backoff schedule")
```

### Test 5: Max Retries Exceeded - Marked Completed Permanently

```python
async def test_max_retries_exceeded():
    """Article that fails 3 times is marked completed with error (no more retries)."""
    
    article_id = ObjectId()
    
    # After 3 failed attempts
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "failed",
            "enrichment_state.attempt_count": 3,
            "enrichment_state.error": "rate_limit_exceeded"
        }}
    )
    
    # Mark as completed (max retries exceeded)
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {
            "enrichment_state.status": "completed",
            "enrichment_state.error": "max_retries_exceeded",
            "enrichment_state.completed_at": datetime.now(timezone.utc)
        }}
    )
    
    # Article NOT eligible for any more processing
    eligible_for_retry = await db.articles.find({
        "_id": article_id,
        "enrichment_state.status": {"$in": ["pending", "failed"]}
    }).to_list(1)
    assert len(eligible_for_retry) == 0  # ✅ Permanently completed with error
    
    print("✅ Test 5 passed: Max retries exceeded, article marked completed")
```

### Test 6: Atomic Claim Prevents Double-Processing

```python
async def test_atomic_claim_prevents_double_processing():
    """Two concurrent processes cannot both claim the same article."""
    
    article_id = ObjectId()
    
    # Process 1: Atomically claim article
    result_1 = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "pending"},
        {"$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": datetime.now(timezone.utc),
        }}
    )
    assert result_1 is not None  # ✅ Process 1 claimed it
    
    # Process 2: Try to claim same article
    result_2 = await db.articles.find_one_and_update(
        {"_id": article_id, "enrichment_state.status": "pending"},  # ← No longer pending
        {"$set": {
            "enrichment_state.status": "in_progress",
            "enrichment_state.last_attempt": datetime.now(timezone.utc),
        }}
    )
    assert result_2 is None  # ✅ Process 2 failed (article no longer pending)
    
    print("✅ Test 6 passed: Atomic claim prevents double-processing")
```

---

## Backlog Cutoff Decision

The state machine above handles **retry and interrupt safety**, but doesn't solve the original unbounded backlog problem.

**Remaining question for your decision:** On startup, how far back should we look for unenriched articles?

### Option A: No Age Cutoff (Process All Historical Articles)

```python
enrichment_query = {
    "enrichment_state.status": {"$in": ["pending", "in_progress", "failed"]}
}
```

**Pros:**
- No articles left behind
- Eventually processes everything

**Cons:**
- First cycle could load 13,496+ articles (memory pressure)
- Takes ~27 cycles (~13.5 hours) to clear backlog
- Could delay fresh articles if backlog is large

### Option B: Age Cutoff (Fresh Articles Only)

```python
min_created_at = datetime.now(timezone.utc) - timedelta(days=30)

enrichment_query = {
    "created_at": {"$gte": min_created_at},
    "enrichment_state.status": {"$in": ["pending", "in_progress", "failed"]}
}
```

**Pros:**
- Bounded backlog: At most ~30 days of unenriched articles
- Memory safe: Protects against old backlog spike
- Fresh articles processed quickly (higher value)

**Cons:**
- Articles older than 30 days not enriched
- Signals page may show no results for old content (acceptable if fresh content exists)

### Option C: Progressive Backfill (Hybrid)

```python
# Cycle 1: Process all fresh articles (last 30 days)
# Cycles 2+: Once fresh backlog cleared, process older articles in bounded batches

if fresh_backlog_count < 100:  # Fresh queue empty
    # Switch to historical articles
    min_created_at = datetime.now(timezone.utc) - timedelta(days=90)
else:
    # Prioritize fresh articles
    min_created_at = datetime.now(timezone.utc) - timedelta(days=30)
```

**Pros:**
- Prioritizes fresh (high-value) articles
- Eventually processes historical articles
- Bounded at any point in time

**Cons:**
- More complex logic
- Still doesn't guarantee processing of very old articles

---

## Proposed Configuration (For Your Decision)

```python
# State machine constants
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_MINUTES = [0, 5, 30]  # Immediate, 5min, 30min
STALE_IN_PROGRESS_SECONDS = 60

# Backlog cutoff (choose one option above)
ENRICHMENT_BACKLOG_AGE_DAYS = 30  # Option B: Fresh articles only
# ENRICHMENT_BACKLOG_AGE_DAYS = None  # Option A: All historical articles
# Hybrid logic (Option C) if needed
```

---

## Summary of Guarantees (Actual, Not Overstated)

### What IS Guaranteed

✅ **No article processed while another process is already processing it** (atomic claim via `find_one_and_update`)

✅ **Articles in `completed` state are never re-selected** (query explicitly excludes them)

✅ **Crash interruptions are detected and recovered** (hung `in_progress` articles re-attempted after 60s)

✅ **Transient failures don't cause infinite retry** (bounded to 3 attempts with backoff)

✅ **Progress is preserved across restarts** (only articles that reached `completed` are skipped)

### What IS NOT Guaranteed

❌ **"No article selected twice"** — If process crashes BEFORE writing `completed`, article is re-selected on restart (legitimate retry)

❌ **"Immediate progress"** — Failed articles only retry after backoff (5-30 min delays)

❌ **"All historical articles processed"** — With age cutoff, old articles (>30d) are skipped

### What Depends on Operator Decision

❓ **Backlog age cutoff** — How far back to look for unprocessed articles? (30d, unlimited, or progressive?)

❓ **Backlog cutoff is a separate safety decision** — State machine handles retry safety; age cutoff is orthogonal.

---

## Next Step for Operator

1. **Confirm root cause:** Run MongoDB queries to verify 13,496+ backlog exists
2. **Decide backlog cutoff:** Option A (unlimited), Option B (30d fresh only), or Option C (hybrid)
3. **Decide on restart evidence:** Review Railway logs to confirm restart pattern is the actual cause
4. **Authorize design:** Once root cause confirmed and cutoff decided, fix can proceed

