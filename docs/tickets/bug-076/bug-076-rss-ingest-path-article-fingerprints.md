---
id: BUG-076
type: bug
status: resolved
priority: high
severity: medium
created: 2026-04-14
updated: 2026-04-14
---

# RSS ingest path does not generate article fingerprints

## Problem

`rss_fetcher.py` calls `create_or_update_articles()` (imported from `db/operations/articles.py`) to store incoming RSS articles. This function did not route through `ArticleService.create_article()`, where fingerprint generation lives. As a result, all RSS-sourced articles arrived in the `articles` collection with no `fingerprint` field, and deduplication by fingerprint was broken for this entire ingest path.

BUG-073 fixed the service layer path to generate fingerprints, but the RSS path was a second entry point that was not covered by that fix.

## Expected Behavior

Every article written to the `articles` collection — regardless of ingest path — should have a `fingerprint` field containing an MD5 hash of the normalized title + content. Duplicate articles from different RSS feeds should be caught and deduplicated before insertion.

## Actual Behavior

Articles inserted via `rss_fetcher.py → create_or_update_articles()` had no `fingerprint` field. All 5 active RSS sources were affected. Deduplication did not function for RSS-sourced articles.

## Steps to Reproduce

1. Observe the RSS ingest cycle (runs hourly via Celery Beat).
2. Query for recent articles missing fingerprints:
   ```javascript
   db.articles.countDocuments({
     created_at: { $gte: new Date(Date.now() - 86400000) },
     fingerprint: { $exists: false }
   })
   ```
3. Result: 28 articles in last 24h with no fingerprint field.
4. Source breakdown: cointelegraph 9, bitcoin.com 10, decrypt 5, coindesk 2, thedefiant 2. All 5 RSS sources affected.

## Environment

- Environment: production (Railway)
- Services affected: Celery Worker (RSS ingest task), MongoDB articles collection
- User impact: medium — duplicate articles can appear in feeds and waste LLM enrichment quota on content already processed

---

## Resolution

**Status:** Resolved  
**Fixed in:** commit `28f65db` — `fix(articles): Enable fingerprint generation for all articles via ArticleService`  
**Deployed:** 2026-04-13 at 03:56 UTC  

### Root Cause

`create_or_update_articles()` in `db/operations/articles.py` was a parallel insert path that predated `ArticleService`. When BUG-073 added fingerprint generation to `ArticleService.create_article()`, it covered one entry point but not this one. The RSS ingest task (`fetch_and_process_rss_feeds`) called `create_or_update_articles` directly, bypassing fingerprint generation entirely.

### Fix Applied (Option A)

`create_or_update_articles()` now routes new article inserts through `ArticleService.create_article()`, consolidating both ingest paths. Existing articles (updates) continue to only update metrics and do not trigger fingerprint regeneration.

### Pre-fix Stragglers

9 articles were inserted between midnight and 03:33 UTC on 2026-04-14 — before the fix deployed at 03:56 UTC. These articles have no fingerprint and cannot participate in deduplication until backfilled. A migration script has been written to address this.

---

## Migration: Backfill fingerprints on pre-fix articles

**Script:** `docs/tickets/bug-076/migrate-backfill-fingerprints.md`

### Status: ✅ COMPLETED — 2026-04-14 18:07:45 UTC

Ran migration via:
```bash
poetry run python docs/tickets/bug-076/migrate-backfill-fingerprints.md
```

**Results:**
```
Backfill complete.
  Total processed : 1766
  Fingerprints set: 1762
  Duplicates found: 4  (tagged with duplicate_of, not deleted)
  Errors          : 0
```

**Key Findings:**
- Migration discovered 1,766 articles without fingerprints (much larger scope than the 9 pre-fix stragglers originally estimated)
- Successfully backfilled 1,762 with generated fingerprints
- Identified 4 duplicate articles that existed before the fix — tagged with `duplicate_of: <original_id>` for manual review

**Tagged Duplicates for Review:**
Review with:
```javascript
db.articles.find({ duplicate_of: { $exists: true } }, { title: 1, source: 1, duplicate_of: 1 })
```

These should be manually reviewed and deleted after confirmation that the original articles are correct.

---

## Manual Verification

Run these queries after the migration completes and after at least one full ingest cycle (hourly).

**1. Confirm no articles are still missing fingerprints**
```javascript
db.articles.countDocuments({
  fingerprint: { $exists: false }
})
// Expected: 0
```

**2. Confirm new articles from the last ingest cycle have fingerprints**
```javascript
db.articles.countDocuments({
  created_at: { $gte: new Date(Date.now() - 3600000) },
  fingerprint: { $exists: false }
})
// Expected: 0 — run this after the next hourly ingest cycle completes
```

**3. Spot-check fingerprint format on recently inserted articles**
```javascript
db.articles.find(
  { created_at: { $gte: new Date(Date.now() - 3600000) } },
  { title: 1, source: 1, fingerprint: 1, _id: 0 }
).limit(5)
// Expected: every document has a fingerprint field containing a 32-character hex string
```

**4. Check for any duplicates surfaced by the migration**
```javascript
db.articles.find(
  { duplicate_of: { $exists: true } },
  { title: 1, source: 1, created_at: 1, duplicate_of: 1, _id: 0 }
)
// Expected: 0 results ideally. If any appear, review before deleting.
```

**5. Confirm fingerprint uniqueness (no two articles share a fingerprint)**
```javascript
db.articles.aggregate([
  { $match: { fingerprint: { $exists: true } } },
  { $group: { _id: "$fingerprint", count: { $sum: 1 }, titles: { $push: "$title" } } },
  { $match: { count: { $gt: 1 } } }
])
// Expected: empty result set
```

---

## Files Changed

- `src/crypto_news_aggregator/db/operations/articles.py` — routes new inserts through `ArticleService.create_article()`
- `migrate_backfill_fingerprints.py` — one-time migration script for pre-fix articles (project root)