# Durable Enrichment State Machine Design

## Overview

The enrichment pipeline must be durable, resumable, idempotent, and fair. Articles flow through these states:

```
pending → claimed → enriched → completed
  ↓                            
  skipped (tier 2/3)
  ↓
  failed_retryable → (retry after backoff) → pending OR failed_terminal
  ↓
  failed_terminal (max retries exceeded)
```

## Article Enrichment State Field

Add to `article` document in MongoDB:

```python
{
  "_id": ObjectId,
  "url": "...",
  # ... existing fields ...
  
  # NEW: Enrichment state machine
  "enrichment_state": {
    "status": "pending|claimed|completed|skipped|failed_retryable|failed_terminal",
    "lease_token": "uuid-123...",  # When claimed, token + expiry prevents concurrent processing
    "lease_expires_at": ISODate(...),  # UTC timestamp
    "retry_count": 3,  # Total attempts so far
    "next_retry_at": ISODate(...),  # When this article becomes claimable again (backoff)
    "failure_reason": "Entity extraction timeout",  # On failure, why
    "updated_at": ISODate(...)  # Last state change
  }
}
```

## Configuration (core/config.py)

Defaults per ticket requirements:

```python
ENRICHMENT_AGE_CUTOFF_DAYS: int = 30  # Don't enrich articles older than 30 days
ENRICHMENT_MAX_ARTICLES_PER_RUN: int = 5000  # Max articles to process per run
ENRICHMENT_LEASE_DURATION_MINUTES: int = 30  # Lease expires after 30 min of inactivity
ENRICHMENT_MAX_RETRY_ATTEMPTS: int = 3  # Max retries per article
ENRICHMENT_RETRY_BACKOFF_MINUTES: int = 5  # Exponential: 5, 10, 20 (capped at lease duration)
ENRICHMENT_BATCH_SIZE: int = 10  # Articles per LLM call
```

## Query & Selection Strategy

### Selection: Bounded, Fair, Newest-First Within Window

```python
# Query builder:
query = {
  "enrichment_state": None,  # Not yet enriched
  "$or": [
    {"created_at": {"$gte": cutoff_date}},  # Only recent articles (30-day window)
  ]
}
# PLUS one of:
# A) Oldest-first recovery (fairness): .sort("created_at", 1).limit(max_batch_articles)
# B) Newest-first in current run: .sort("created_at", -1).limit(max_batch_articles)

# Suggested: Use smallest(created_at) WHERE status IN [pending, failed_retryable AND next_retry_at <= now]
# This prevents tier 2/3 starvation while prioritizing fresh articles
```

### Claim: Atomic Compare-and-Set with Lease

```python
# When claiming an article for processing:
result = collection.update_one(
  {
    "_id": article_id,
    "enrichment_state.status": {"$in": ["pending", "failed_retryable"]},  # Pre-condition
    "enrichment_state.lease_expires_at": {"$lt": now} OR field doesn't exist  # Not leased
  },
  {
    "$set": {
      "enrichment_state.status": "claimed",
      "enrichment_state.lease_token": uuid4(),
      "enrichment_state.lease_expires_at": now + 30 min,
      "enrichment_state.updated_at": now
    }
  }
)
# Only succeeds if no concurrent claim holds the lease
# If update fails, article is being processed elsewhere; skip
```

### Completion: Idempotent Mention Writes

```python
# After entity extraction succeeds:

# 1. Write mentions (idempotent):
#    Upsert: match on (article_id, entity, source)
#    Insert if not exists, update if exists (no duplicate)
for mention in extracted_mentions:
  mentions_coll.update_one(
    {
      "article_id": str(article_id),
      "entity": mention['entity'],
      "source": article['source']
    },
    {
      "$set": {
        "entity_type": mention['type'],
        "is_primary": mention['is_primary'],
        "created_at": now  # or first created time
      },
      "$inc": {"mention_count": 1}  # Track repeats
    },
    upsert=True
  )

# 2. Update article state (only after all writes succeed):
collection.update_one(
  {"_id": article_id},
  {
    "$set": {
      "enrichment_state.status": "completed",
      "enrichment_state.lease_token": None,
      "enrichment_state.lease_expires_at": None,
      "enrichment_state.updated_at": now,
      "relevance_tier": tier_1  # Mark as enriched
    }
  }
)
```

### Failure & Retry: Exponential Backoff, Max Attempts

```python
# On extraction failure (e.g., LLM timeout):

max_retries = settings.ENRICHMENT_MAX_RETRY_ATTEMPTS  # 3
backoff_base = settings.ENRICHMENT_RETRY_BACKOFF_MINUTES  # 5 min

# Decide next state:
if retry_count < max_retries:
  # Retryable: schedule next attempt with exponential backoff
  backoff_minutes = backoff_base * (2 ** retry_count)  # 5, 10, 20
  next_retry_at = now + timedelta(minutes=min(backoff_minutes, 60))
  
  collection.update_one(
    {"_id": article_id},
    {
      "$set": {
        "enrichment_state.status": "failed_retryable",
        "enrichment_state.next_retry_at": next_retry_at,
        "enrichment_state.failure_reason": str(error)[:200],  # Truncate
        "enrichment_state.updated_at": now
      },
      "$inc": {"enrichment_state.retry_count": 1}
    }
  )
else:
  # Terminal failure: max retries exceeded
  collection.update_one(
    {"_id": article_id},
    {
      "$set": {
        "enrichment_state.status": "failed_terminal",
        "enrichment_state.failure_reason": f"Max retries ({max_retries}) exceeded: {str(error)[:200]}",
        "enrichment_state.updated_at": now
      },
      "$inc": {"enrichment_state.retry_count": 1}
    }
  )
```

### Fairness & Starvation Prevention

**Problem**: Tier 2/3 articles (marked "skipped") shouldn't be permanently ignored if newer articles keep arriving.

**Solution**: Rotating selection strategy
```python
if run_number % 3 == 0:  # Every 3rd run, prioritize oldest
  query.sort("created_at", 1)  # Oldest first
else:
  query.sort("created_at", -1)  # Newest first (default)
```

## Legacy Article Migration

For articles already stored that never had enrichment state:

```python
# Step 1: Dry-run (read-only count)
def count_legacy_articles():
  count = collection.count_documents({
    "enrichment_state": None,  # Not yet initialized
    "created_at": {"$gte": cutoff_date}
  })
  return count

# Step 2: Initialize with bounds and logging
def migrate_legacy_articles(batch_size=100):
  """Initialize enrichment_state for articles without it. Bounded, observable."""
  cutoff = datetime.utcnow() - timedelta(days=ENRICHMENT_AGE_CUTOFF_DAYS)
  
  migrated = 0
  while True:
    articles = collection.find(
      {
        "enrichment_state": None,
        "created_at": {"$gte": cutoff}
      }
    ).limit(batch_size)
    
    articles_batch = list(articles)
    if not articles_batch:
      break
    
    for article in articles_batch:
      # Decide initial status based on existing enrichment signals
      if (article.get("relevance_tier") or 
          article.get("relevance_score") or 
          article.get("sentiment")):
        # Already enriched; mark completed to skip
        initial_status = "completed"
      else:
        # Pending enrichment
        initial_status = "pending"
      
      collection.update_one(
        {"_id": article["_id"]},
        {
          "$set": {
            "enrichment_state": {
              "status": initial_status,
              "lease_token": None,
              "lease_expires_at": None,
              "retry_count": 0,
              "next_retry_at": None,
              "failure_reason": None,
              "updated_at": datetime.utcnow()
            }
          }
        }
      )
      migrated += 1
    
    logger.info(f"Migrated {migrated} legacy articles so far...")
  
  logger.info(f"Legacy migration complete: {migrated} articles initialized")
  return migrated

# Step 3: Call once at startup, if migration needed
async def on_startup():
  dry_count = count_legacy_articles()
  if dry_count > 0:
    logger.warning(f"Found {dry_count} articles without enrichment state.")
    logger.info("Running bounded legacy migration (first 100 per run)...")
    # Only migrate first batch; let subsequent runs handle the rest
    await migrate_legacy_articles(batch_size=100)
```

## Testing Strategy

1. **State transitions**: pending → claimed → completed ✓
2. **Concurrency**: Two workers cannot claim same article
3. **Idempotency**: Retry after partial mention write doesn't duplicate
4. **Retry backoff**: Correct exponential timing
5. **Max attempts**: Exactly N retries before terminal
6. **Fairness**: Oldest articles not starved over time
7. **Lease recovery**: Stale lease takeover works
8. **Interruption**: Partial claim cleanup on shutdown
9. **Idempotent mentions**: Upsert strategy verified

## Decision Points (Operator Approval)

1. **ENRICHMENT_LEASE_DURATION_MINUTES**: How long until a claimed article is stale?
   - Suggested: 30 min (time.sleep between claim and completion)
   - Trade-off: Longer = fewer false recoveries; shorter = faster recovery

2. **ENRICHMENT_MAX_RETRY_ATTEMPTS**: How many retries per article?
   - Suggested: 3 (fail-fast on broken articles)
   - Trade-off: More attempts = better resilience; fewer = faster iteration

3. **ENRICHMENT_RETRY_BACKOFF_MINUTES**: Initial backoff in minutes?
   - Suggested: 5 min (5, 10, 20 exponential growth)
   - Trade-off: Shorter = faster recovery from transient errors; longer = less thrashing

4. **Fairness strategy**: Oldest-first recovery, or rotational?
   - Suggested: Rotational (every 3rd run prioritize oldest)
   - Trade-off: Rotational = simple & fair; oldest-first = guarantees no starvation but slower on new articles

## Backwards Compatibility

Articles created before this change will have `enrichment_state: null` in MongoDB. On first enrichment run after deployment, the migration initializes them with appropriate state based on existing enrichment fields.
