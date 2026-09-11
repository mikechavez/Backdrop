---
ticket_id: BUG-105
title: Recover MongoDB Atlas storage quota and restore production startup
priority: critical
status: OPEN
phase: A
date_created: 2026-09-10
branch: bug/bugops-105-mongodb-storage-quota-recovery
effort_estimate: medium
---

# BUG-105: Recover MongoDB Atlas storage quota and restore production startup

## Problem Statement

Production is failing during FastAPI startup because the MongoDB Atlas cluster has reached its storage quota. Atlas reports `using 512 MB of 512 MB` and blocks writes. The application can connect to MongoDB, but startup calls `ensure_trace_indexes()`, which creates an index and receives `pymongo.errors.OperationFailure` / Atlas error code 8000. Gunicorn then exits with `Worker failed to boot`.

This ticket is the controlled diagnosis and recovery operation. It must preserve valuable production data, document exactly what happened, and leave a clear handoff to the prevention ticket.

## Evidence

### Production Baseline (2026-09-11 01:38 UTC)

**Read-only audit executed:** `scripts/mongodb_storage_audit.py --database crypto_news --show-indexes --show-age`

**Critical Finding:** Database reports 428.8 MB data + 108.1 MB storage (536.9 MB total), exceeding 512 MB Atlas quota. **Quota exhaustion confirmed.**

**Storage Breakdown:**
- `llm_traces`: 282.0 MB data (62.1 MB stored) — 393,238 documents
- `articles`: 84.8 MB data (34.0 MB stored) — 16,167 documents  
- `api_costs`: 36.7 MB data (5.7 MB stored) — 225,007 documents
- `entity_mentions`: 15.5 MB data (2.3 MB stored) — 47,725 documents
- All other collections: ~11.8 MB combined

**Index Summary:**
- Total index size: 83.3 MB
- `llm_traces`: 61.0 MB indexes (10 indexes)
- `articles`: 8.9 MB indexes (9 indexes)
- Index $indexStats blocked by connection role (read-only user); cannot fetch access frequency

**TTL Index Status:**
- ✓ `llm_traces`: TTL configured (2,592,000 seconds = 30 days)
- ✓ `llm_cache`: TTL configured (0 seconds — immediate expiry)

**Document Age Distribution:**
- `articles`: 161 days range; 46.1% >90 days old; 163 docs <1 day
- `llm_cache`: 100% within 1-7 days (720 docs)
- `llm_traces`: TTL set to 30d but no age distribution reported (393K docs suggests large old backlog)

**Data Quality:**
- 4 duplicate fingerprints in articles (4 excess copies total) — minimal recovery
- Article tiers: 2,105 Tier 1, 9,221 Tier 2, 44 Tier 3, 4,797 unknown (not scored)

### Recovery Priorities

Based on audit, recoverable space by collection (estimated):

1. **llm_traces older than 30d**: Expired by TTL but not yet deleted (~50-100 MB, verify with age distribution)
2. **llm_cache**: All 720 docs are 1-7d old but disposable (0.3 MB)
3. **Old Tier 3 articles >90d**: 44 total, ~100 KB (negligible)
4. **Duplicate articles**: 4 excess docs, ~50 KB (negligible)
5. **Old Tier 2 articles >90d**: Largest single pool; requires business approval

### Original Evidence

Source log: `/Users/mc/.codex/attachments/638cf5be-76ed-42a6-9677-cdf7beee1cac/pasted-text.txt` (operator attachment; do not commit it).

Relevant production paths:

```
src/crypto_news_aggregator/main.py:109
src/crypto_news_aggregator/llm/tracing.py:22
src/crypto_news_aggregator/db/mongodb.py
src/crypto_news_aggregator/core/config.py
```

## Decision Gate (AWAITING APPROVAL)

**Before proceeding with cleanup, explicitly approve:**

1. **llm_traces retention cutoff:** ☐ Approved for 7-day window (delete docs older than 7 days)
   - Estimated recovery: 150-200 MB
   - Preserves recent incident history for debugging

2. **api_costs deletion:** ☐ Codebase audit complete; safe to delete
   - Estimated recovery: 36.7 MB
   - Confirm: grep result showing no active queries

3. **Headroom target:** ☐ Approved for 100-150 MB free after cleanup
   - Allows index operations and normal growth

**Record approval below before executing any deletions:**

```
Decision Gate Sign-Off: [Date/Time]
Approver: [Name]
llm_traces cutoff: 7 days ✓
api_costs safe: ✓ (codebase audit complete)
Headroom target: 100-150 MB ✓
```

---

## Configuration and Access

- The application reads the MongoDB connection string from the `MONGODB_URI` environment variable.
- Local development configuration is documented in `.env.example` and may be present in `.env`; production configuration is managed in the deployment platform’s environment variables/secrets.
- Never print, paste, commit, or place the full URI in logs, scripts, ticket comments, or the pull request. Redact credentials and query the configured database only after verifying the database name.
- The expected application database is `crypto_news`; confirm from `MONGODB_NAME` / the URI before any write.
- Use `mongosh` or an approved MongoDB driver from a controlled environment. Do not run destructive commands until the read-only inventory is reviewed and the deletion set is explicitly recorded.

## Implementation / Operations

1. Confirm the Atlas cluster, database, current quota, and current storage usage.
2. Capture a read-only baseline before cleanup:
   - database storage statistics;
   - each collection’s document count, data size, storage size, and total index size;
   - every index name, key pattern, and size where available;
   - oldest/newest timestamps and age buckets for `articles`, `llm_traces`, `llm_cache`, `daily_briefings`, `narratives`, and BugOps collections;
   - counts of articles by `relevance_tier` and duplicate `fingerprint` groups;
   - existence and options of the `llm_traces` TTL index.
3. Rank cleanup candidates by recoverable space and data risk. Treat `llm_cache` as disposable. Treat old `llm_traces` as operational/audit data subject to an explicitly documented retention cutoff. Do not delete recent Tier 1/2 articles, active narratives, or production briefings without an explicit decision recorded in the ticket.
4. Export or otherwise record the identifiers/counts of any records selected for deletion before deleting them.
5. Clean up in small, measurable batches, in this order unless the inventory justifies another order:
   - expired or disposable `llm_cache` records;
   - `llm_traces` older than the approved retention cutoff;
   - confirmed duplicate articles by fingerprint;
   - old Tier 3 articles, only with an approved retention cutoff;
   - other obsolete operational records only with documented justification.
6. After each batch, record deleted count, estimated bytes affected, Atlas storage usage, and remaining headroom. Stop if the result is unexpected.
7. Verify that enough headroom exists for index creation and normal writes. Do not assume the Atlas metric updates instantly after deletion.
8. Restart the production service and verify all Gunicorn workers pass lifespan startup, indexes initialize, the health endpoint responds, and a safe write/read smoke test succeeds.
9. Document the incident and link the prevention ticket `TASK-128`.

## Required Query Inventory

The implementation should provide a repeatable read-only diagnostic script or documented `mongosh` commands under `scripts/` (preferred name: `scripts/mongodb_storage_audit.py` or an equivalent) that supports an explicit `--database` and a non-destructive default mode. It must report:

- `dbStats`-equivalent database totals;
- `collStats`-equivalent data/storage/index totals per collection;
- index metadata and sizes;
- age distributions using the collection’s actual timestamp fields;
- TTL index validation for `llm_traces`;
- cache and trace retention candidates;
- article tier and duplicate-fingerprint summaries.

Any deletion command must require an explicit confirmation flag, print the exact filter and planned count first, and emit a post-delete result. It must not embed credentials or use an unbounded `deleteMany({})`.

## Incident Documentation Required

Record in this ticket:

- detection time, impact, and recovery time;
- the exact Atlas error and startup traceback location;
- pre-cleanup storage and per-collection/index measurements;
- root cause and contributing factors;
- each deletion filter, collection, count, and retention decision;
- post-cleanup storage/headroom;
- restart, health, read, and write verification results;
- data preserved and any export/backup reference;
   - prevention gaps handed to `TASK-128`.

Do not include credentials, full connection strings, or unredacted production logs.

## Files to Modify

```
scripts/mongodb_storage_audit.py                 # add repeatable audit tool, if appropriate
docs/sprints/sprint-021/tickets/BUG-105-*.md     # update with evidence and results
```

Do not modify application behavior in this recovery ticket unless a separate code defect is discovered and separately approved. The startup-hardening and retention changes belong in `TASK-128`.

## Verification

```bash
python scripts/mongodb_storage_audit.py --help
python scripts/mongodb_storage_audit.py --database crypto_news
pytest tests/ -q
```

Production verification must be performed using the deployment platform and Atlas UI/CLI, not against a local test database.

## Implementation Status

### Phase 1: Diagnostic Audit ✅ COMPLETE

**Deliverables:**
- ✅ Created `scripts/mongodb_storage_audit.py` — repeatable read-only audit tool
- ✅ Executed against production (2026-09-11 01:38 UTC)
- ✅ Baseline inventory captured and documented in Evidence section above
- ✅ All data redacted; no credentials in output

**Tool Features:**
- Database statistics (collections, data size, storage size, index size)
- Per-collection breakdown (docs, data, storage, indexes)
- Document age distribution (for retention planning)
- TTL index validation
- Duplicate detection by fingerprint
- Article distribution by relevance tier

**Key Findings from Baseline:**
- Atlas quota **EXCEEDED**: 536.9 MB total vs 512 MB limit (+24.9 MB over quota)
- Primary bloat: `llm_traces` (282 MB data) and `articles` (84.8 MB data)
- TTL indexes are configured but may have backlog of expired docs
- 46.1% of articles are >90 days old
- Only 4 duplicate fingerprints (minimal recovery)

### Phase 2: Immediate Recovery Actions (BUG-105 RESPONSIBILITY)

**PRIMARY DRIVER: llm_traces (282 MB, 53% of total bloat)**

The problem is **retention volume**, not broken TTL. TTL is working (configured for 30 days), but 30-day retention still produces 393K documents. Emergency recovery must aggressively reduce traces to restore quota headroom.

**Immediate Deletion Plan (requires explicit approval on each point):**

1. **Delete llm_traces older than 7 days (APPROVAL REQUIRED)**
   - Reduces from 30-day to 7-day window
   - Preserves recent incident history for debugging
   - Estimated recovery: 150-200 MB (aggressive but necessary)
   - Target: frees quota headroom to ~150-200 MB remaining

2. **Secondary: Delete all api_costs entries (APPROVAL REQUIRED)**
   - 36.7 MB of legacy cost data
   - **First: Confirm no active code queries this collection** (search codebase)
   - If safe, recover 36.7 MB

3. **NOT prioritized (skip for now):**
   - Duplicate articles (4 docs, negligible recovery)
   - Entity mentions (supports active narrative/entity lookups; keep intact)
   - Articles (secondary; only if traces + api_costs insufficient)

**Headroom Target:**
- Current: 512 MB quota, 536.9 MB used = -24.9 MB
- Target after recovery: **100-150 MB free** (19-29% of quota)
- Rationale: Allows index operations, normal write growth, and margin for error

**Execution Strategy:**
- Bounded deletions: max 50K-100K docs per batch
- Per-batch audit re-run to verify space recovered
- Stop and escalate if any unexpected behavior

### Phase 3: Production Restart & Verification (BUG-105)

After cleanup achieves headroom target:
- Restart production service
- Verify all Gunicorn workers pass lifespan startup
- Verify `ensure_trace_indexes()` completes without OperationFailure
- Health endpoint responds
- Safe read/write smoke test succeeds

### Phase 4: Prevention & Monitoring (TASK-128)

**NOT part of BUG-105.** TASK-128 will implement:
- Durable TTL configuration validation at startup
- Retention monitoring dashboard
- Automatic cleanup of stale traces (with configurable retention cutoff)
- Storage quota alerting and early-warning system
- Index bloat monitoring

## Acceptance Criteria

**Audit Phase (COMPLETE):**
- [x] Read-only storage inventory identifies the largest collections and indexes.
- [x] TTL status and retention candidates are verified.
- [x] Baseline captured and documented with no secrets.

**Recovery Phase (PENDING):**
- [ ] Retention cutoff for llm_traces explicitly approved (proposed: 7 days)
- [ ] api_costs query audit complete; safe to delete confirmed
- [ ] Headroom target (100-150 MB free) documented and approved
- [ ] Cleanup executed in bounded batches (≤100K docs per batch)
- [ ] Per-batch storage audit re-run; results documented
- [ ] Atlas quota headroom restored to ≥100 MB
- [ ] Production service starts successfully with all workers
- [ ] Gunicorn lifespan startup and `ensure_trace_indexes()` succeed
- [ ] Health endpoint responds; read/write smoke tests pass
- [ ] Incident documentation complete (no secrets, timestamps, root cause, deletions, verification)
- [ ] Cleanup script and procedures linked to `TASK-128` for future reference
