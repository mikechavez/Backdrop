# Data Model & MongoDB Collections

## Overview

The system persists briefings and detected patterns in MongoDB. This document describes the key collections, document schemas, and how data flows from generation through storage. Understanding the data model enables debugging production issues and verifying briefing generation completeness.

**Anchor:** `#data-model-mongodb`

## Architecture

### Key Collections

- **daily_briefings**: Generated briefings with content, metadata, and smoke test markers
- **briefing_patterns**: Market patterns detected during briefing generation
- **narratives**: Active story threads connecting related articles and entities
- **articles**: Ingested news articles enriched with sentiment and entity extraction

### Data Flow

1. **Briefing Generation** → Collects signals, narratives, and patterns
2. **LLM Processing** → Claude generates narrative, insights, recommendations
3. **Database Save** → Inserts briefing_doc to `daily_briefings` collection
4. **Pattern Storage** → Inserts pattern documents to `briefing_patterns` collection
5. **Read Access** → API returns latest briefing or historical archive

## Implementation Details

### daily_briefings Collection Schema

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:836-894`

Each briefing document contains:

```javascript
{
  "_id": ObjectId("..."),              // MongoDB ID
  "type": "morning" | "afternoon" | "evening",  // Briefing type
  "title": "string or null",           // Title (null for non-smoke, "SMOKE TEST - ..." for tests)
  "generated_at": ISODate("2026-02-10T13:00:00Z"),  // Generation time
  "version": "2.0",                    // Agent-generated version
  "content": {
    "narrative": "string",             // Main briefing text (Claude generated)
    "key_insights": ["string", ...],   // Top 3-5 insights
    "entities_mentioned": ["string", ...],  // Companies, people, projects
    "detected_patterns": ["string", ...],   // Market patterns found
    "recommendations": [               // Reading recommendations
      {
        "title": "string",             // Narrative or entity name
        "narrative_id": "ObjectId or null"  // Link to narratives collection (added by FEATURE-035)
      }
    ]
  },
  "metadata": {
    "confidence_score": 0.92,          // LLM confidence (0-1)
    "signal_count": 20,                // Number of signals used
    "narrative_count": 15,             // Number of narratives used
    "pattern_count": 8,                // Number of patterns detected
    "manual_input_count": 2,           // Manual inputs from memory
    "model": "claude-haiku-4-5-20251001",  // LLM model used (Haiku primary; Sonnet if fallback triggered)
    "refinement_iterations": 2         // Self-refine iterations
  },
  "is_smoke": false,                   // Smoke test marker (FEATURE-037)
  "published": true,                   // Production briefing marker
  "task_id": "uuid or null",           // Celery task ID for correlation (BUG-022)
  "created_at": ISODate("2026-02-10T13:00:15Z")  // Record insertion time
}
```

**Key fields:**
- `task_id` (line 887): Correlates briefing to Celery task for debugging task execution
- `is_smoke` (line 885): Marks test briefings; production API filters these out
- `published` (line 886): Controls whether briefing appears in feed (not is_smoke)
- `version: "2.0"` (line 868): Distinguishes agent-generated from legacy template briefings

**Size:** Typical briefing: 8-15 KB (narrative ~3-5KB, metadata ~200 bytes, recommendations ~500 bytes)

### Briefing Storage & Retrieval

**File:** `src/crypto_news_aggregator/db/operations/briefing.py`

**Insert operation** (line 41-60):
- Adds `generated_at` timestamp if missing
- Adds `created_at` timestamp (server time at insertion)
- Calls MongoDB `insert_one()` and returns inserted_id

**Read operation** (line 63-78):
- Queries production briefings only: `published=true` OR field missing (backward compat)
- Excludes smoke tests: `is_smoke != true`
- Returns most recent by `generated_at` (descending sort)

**Filter definition** (line 20-34):
```javascript
{
  "$or": [
    {"published": true},               // New briefings
    {"published": {"$exists": false}}  // Historical briefings
  ],
  "is_smoke": {"$ne": true}            // Exclude smoke tests
}
```

This backward-compatible filter handles briefings created before `published` field was added.

### briefing_patterns Collection Schema

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:896-908`

Each pattern document:

```javascript
{
  "_id": ObjectId("..."),
  "briefing_id": "string (ObjectId from daily_briefings._id)",
  "pattern_type": "momentum" | "correlation" | "divergence" | ...",
  "description": "string",            // Pattern explanation
  "entities": ["string", ...],        // Related entities
  "confidence": 0.87,                 // Confidence score (0-1)
  "details": {                        // Pattern-specific data
    "strength": "high" | "medium" | "low",
    "affected_assets": ["BTC", "ETH"],
    "timeframe": "1h" | "4h" | "1d"
  }
}
```

**Indexing:** Patterns are indexed by `briefing_id` for fast lookups when reading a specific briefing.

### Infrastructure Collections

These collections are written and read by the LLM gateway layer, not the business-logic layer. They are separate from briefings/narratives/articles/patterns.

#### llm_traces Collection

**File:** `src/crypto_news_aggregator/llm/gateway.py:325,360`, `src/crypto_news_aggregator/llm/tracing.py:14`

Single source of truth for LLM cost enforcement and spend visibility. Written by `gateway.py` after every LLM call, regardless of operation type.

```javascript
{
  "_id": ObjectId("..."),
  "operation": "briefing_generate",       // Caller-supplied operation name (required)
  "model": "claude-haiku-4-5-20251001",   // Actual model used
  "input_tokens": 1200,
  "output_tokens": 800,
  "cost": 0.00031,                        // Field name is "cost" — NOT "cost_usd"
  "timestamp": ISODate("..."),            // Query field — NOT "created_at"
  "cached": false                         // True if response served from llm_cache
}
```

**Indexes:**
```javascript
db.llm_traces.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 })  // TTL 30 days
db.llm_traces.createIndex({ operation: 1 })
db.llm_traces.createIndex({ operation: 1, timestamp: -1 })
```

**Critical field notes:**
- Always query using `timestamp`, not `created_at` — the latter does not exist on this collection
- Cost field is `cost`, not `cost_usd` — aggregations must use `"$cost"`
- `operation` is required; traces with `operation: "provider_fallback"` indicate a call site that did not pass an operation name (should be zero in steady state post-BUG-078)

**Budget enforcement:** `get_daily_cost()` and `get_monthly_cost()` aggregate exclusively from this collection (BUG-079). Monthly hard limit: $30 (`ANTHROPIC_MONTHLY_API_LIMIT`). Daily hard limit: $1.00.

#### llm_cache Collection

**File:** `src/crypto_news_aggregator/llm/cache.py:26`, `src/crypto_news_aggregator/llm/gateway.py:40,95,106,133,173,215`

Prompt-response cache managed by `LLMCache`. Reduces redundant API calls for identical or near-identical prompts.

```javascript
{
  "_id": ObjectId("..."),
  "cache_key": "sha256_hash_of_prompt",
  "response": "...",        // Cached LLM response text
  "model": "claude-haiku-4-5-20251001",
  "created_at": ISODate("...")
}
```

Cache hit rate can be checked via `db.llm_cache` query. Wired since BUG-072 (Sprint 14); hit rate not yet measured (see TASK-070).

#### llm_usage Collection (Legacy)

Still exists and receives some writes, but is **not** the source of truth for budget enforcement. Admin dashboard endpoints (`/admin/cost/projection`, `/admin/cost/monthly`) still read from `api_costs` and `llm_usage`. Do not rely on this collection for spend accuracy — use `llm_traces`.

### Related Collections (Reference)

**narratives** collection (used for recommendations):
- Each narrative has `_id: ObjectId`, `title: string`, and `description: string`
- Includes `fingerprint` field (SHA1 hash of nucleus_entity + top_actors) for matching and deduplication
- `needs_summary_update: bool` — set `true` by merge path when summary is stale (3+ new articles, lifecycle promotion, or >24h age gap); consumed by `refresh_flagged_narratives` task (FEATURE-012, BUG-088)
- `last_summary_generated_at: ISODate` — stamped at narrative creation; used by merge path to detect summary staleness
- `dormant_since: ISODate` — set when narrative is auto-dormanted by zombie cleanup (TASK-073)
- `_disabled_by: string` — set to `"TASK-073-zombie-cleanup"` or `"TASK-073-auto-cleanup"` when auto-dormanted; used for audit trail
- **Reference:** `src/crypto_news_aggregator/services/briefing_agent.py:859-862` (matching recommendations to narrative IDs)

**articles** collection (sources for briefings):
- Each article has `title`, `content`, `source`, `published_at`, sentiment, entities
- Briefings cite articles indirectly through narratives and patterns

### Query Performance Trade-offs

**Context:** October 2025 signals performance optimization revealed that batch queries don't always outperform parallel indexed queries.

**Batch Query Approach (Using $in operator):**
- Single query with `{entity: {$in: [...]}}` on large collection
- Requires MongoDB to sort/filter entire collection during scan
- Performance: 18-33 seconds (slow due to collection scan overhead)
- Advantage: Simple logic, fewer network round-trips
- Disadvantage: Scans large collection regardless of existing indexes

**Parallel Indexed Query Approach:**
- Run 50 parallel indexed queries with `{entity: exact_value}` using compound index
- Each query uses existing `entity_mentions(entity, timestamp)` compound index
- Performance: ~6 seconds cold, <0.1s cached (40% faster + better caching)
- Advantage: Leverages existing indexes, allows concurrent execution, excellent cache locality
- Disadvantage: More network round-trips

**Key Learning:** Don't assume batch queries are faster. For indexed queries, parallel execution with proper indexes (6s) beats batch queries that scan large collections (18-33s). Indexes matter more than query count.

**Reference:** SIGNALS_PERFORMANCE_FINAL_SUMMARY.md, Performance section (lines 28-57)

### Narrative Matching & Fingerprint Backfill Sequence

The narrative matching system deduplicates detected clusters by comparing fingerprints to existing narratives. This required a one-time backfill because legacy narratives (created before fingerprinting was implemented) lacked the `fingerprint` field.

**Oct 2025 Matching Deployment Sequence:**
1. **Oct 15**: Test detected 0% match rate (39 clusters, zero matches) — fingerprints missing on existing narratives
2. **Oct 15-16 overnight**: NARRATIVE_FINGERPRINT_BACKFILL.py runs — computes SHA1 fingerprints for all existing narratives using nucleus_entity + top_actors (idempotent: skips if fingerprint exists)
3. **Oct 16**: Test re-run shows 89.1% match rate (46 clusters, 41 matches at 0.800 similarity) — fingerprints now present
4. **Oct 16 (same day)**: Threshold fix applied: changed similarity check from `> 0.6` to `>= 0.6` to include boundary matches

**Combined Effect:**
- Fingerprints alone: 62.5% match rate (many still rejected at boundary)
- Fingerprints + threshold fix: 89.1% match rate (proper deduplication)

**Idempotency:** Fingerprint backfill skips narratives with existing fingerprint field, so it's safe to re-run if needed.

**Reference:** NARRATIVE_FINGERPRINT_BACKFILL.md, NARRATIVE_MATCHING_TEST_RESULTS.md (Oct 15, 0% rate), NARRATIVE_MATCHING_FIX_VERIFICATION.md (Oct 16, 89.1% rate)

## Operational Checks

### Health Verification

**Check 1: Briefing collection exists and is accessible**
```javascript
db.daily_briefings.stats()
// Should return collection stats; if error, MongoDB connection or permissions issue
```
*File reference:* `src/crypto_news_aggregator/db/operations/briefing.py:41-60` (insert_briefing)

**Check 2: Latest briefing exists**
```javascript
db.daily_briefings.findOne(
  {
    "$or": [{"published": true}, {"published": {"$exists": false}}],
    "is_smoke": {"$ne": true}
  },
  {_id: 1, generated_at: 1, type: 1}
).sort({generated_at: -1})
// Should return a document; if null, no production briefing exists
```
*File reference:* `src/crypto_news_aggregator/db/operations/briefing.py:20-34` (filter) and line 73-75 (query)

**Check 3: Briefing has required fields**
```javascript
// Full query to verify structure
db.daily_briefings.findOne({_id: ObjectId("...")})
// Must have: type, generated_at, version, content.narrative, metadata, published, is_smoke
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:864-888` (document structure)

**Check 4: Task ID correlation is working**
```javascript
// Find briefing by task_id
db.daily_briefings.findOne({task_id: "a1b2c3d4-..."})
// Should find the briefing; if null, task_id wasn't passed to save function
```
*File reference:* `src/crypto_news_aggregator/tasks/briefing_tasks.py:98-102` (passes task_id) and `briefing_agent.py:887` (stores task_id)

**Check 5: Patterns are saved for briefing**
```javascript
// Count patterns for a briefing
db.briefing_patterns.countDocuments({briefing_id: ObjectId("...")})
// Should be > 0 if patterns were detected; 0 means pattern save failed or no patterns detected
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:896-908` (pattern save)

### Database Size & Growth

**Monitoring:**
- Each briefing: 8-15 KB
- Each pattern: 200-500 bytes
- Daily growth: ~100-150 KB (3 briefings × 15KB + patterns × 100 per briefing)
- Estimated annual: ~50 GB (may vary with article/narrative growth)

**Cleanup:** Weekly task removes briefings older than 30 days
- **File:** `src/crypto_news_aggregator/tasks/beat_schedule.py:89-102` (cleanup schedule)
- **Time:** Every Sunday at 3:00 AM EST

### Smoke Test vs. Production Data

Smoke tests are marked but retained for testing:

```javascript
// Production briefing
{"is_smoke": false, "published": true, "title": null}

// Smoke test briefing
{"is_smoke": true, "published": false, "title": "🔬 SMOKE TEST - Morning Briefing"}
```

**Filtering:**
- Public API queries: Filters to `published=true AND is_smoke!=true`
- Admin queries: Can include smoke tests
- Testing: Smoke tests verify pipeline without polluting production feed

*File reference:* `src/crypto_news_aggregator/db/operations/briefing.py:20-34` (filter)

## Debugging

**Issue:** Briefing was generated but not saved to MongoDB
- **Root cause:** Insert operation failed (connection, permissions, schema validation)
- **Verification:** Check worker logs for exception in `_save_briefing()` (line 836-894)
- **Fix:** Check MongoDB connectivity and user permissions; review exception details
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:890` (insert_briefing call)

**Issue:** Query returns old briefing instead of latest
- **Root cause:** `published` or `is_smoke` fields have wrong values
- **Verification:** Query without filters: `db.daily_briefings.findOne({}, {generated_at:1, published:1, is_smoke:1}).sort({generated_at:-1})`
- **Fix:** Manually update `published: true` and `is_smoke: false` for mismarked briefings
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:885-886` (field assignment)

**Issue:** Patterns saved but not returned in briefing API response
- **Root cause:** Patterns stored but briefing document not updated with pattern count/list
- **Verification:** Check briefing metadata.pattern_count vs. actual count in briefing_patterns
- **Fix:** Verify pattern save completed before API returns briefing
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:896-908` (pattern save)

**Issue:** Memory leak or slowdown accessing briefing collection
- **Root cause:** Missing index on frequently queried fields (`generated_at`, `is_smoke`, `published`)
- **Verification:** `db.daily_briefings.getIndexes()` should show index on `generated_at` or `published`
- **Fix:** Create index: `db.daily_briefings.createIndex({"published": 1, "is_smoke": 1, "generated_at": -1})`

## Relevant Files

### Core Logic
- `src/crypto_news_aggregator/services/briefing_agent.py:836-894` - Briefing document construction
- `src/crypto_news_aggregator/db/operations/briefing.py` - Collection operations (insert, read)
- `src/crypto_news_aggregator/services/briefing_agent.py:896-908` - Pattern storage

### API Endpoints
- `src/crypto_news_aggregator/api/briefing.py` - Public briefing API routes (uses read operations)
- `src/crypto_news_aggregator/api/admin.py` - Admin endpoints for manual triggers

### Configuration
- `src/crypto_news_aggregator/core/config.py` - MongoDB URI and credentials
- `.env` - MONGODB_URI connection string

### Related Systems
- **Scheduling (20-scheduling.md)** - How briefings are triggered for persistence
- **LLM Integration (60-llm.md)** - How content is generated before storage

---
*Last updated: 2026-04-25* | *Generated from: 03-mongo-collections.txt, 05-briefing-save.txt* | *Anchor: data-model-mongodb*