---
id: BUG-103
type: bug
status: backlog
priority: high
severity: high
created: 2026-05-10
updated: 2026-05-10
---

# Prevent Narrative Write Paths From Creating Invalid Summary Freshness State

## Problem
Production contained narratives in an invalid summary freshness state:

```text
needs_summary_update=false
last_summary_generated_at=null
```

This state is dangerous because the system can treat a narrative as not needing refresh while having no timestamp proving that a trusted summary was ever generated. During the Sprint 019 bootstrap refresh, several selected narratives entered or remained in this state, creating risk that public narrative cards or briefings would show stale, blank, or obviously broken summary content.

A broader production check found 341 narratives matching this invalid state, mostly legacy or older records. A narrower check for recent visible narratives, scoped to `last_updated >= 2026-05-09T00:00:00Z` and `lifecycle_state != archived`, found 2 additional visible recent records after the 3 originally broken bootstrap records were deleted.

## Expected Behavior
Narratives should never be visible in production with:

```text
needs_summary_update=false
last_summary_generated_at=null
```

A narrative should only clear `needs_summary_update` when a summary was successfully generated and `last_summary_generated_at` is written in the same successful update.

For non-refresh write paths, updates should preserve or explicitly recompute summary freshness state. Merge/upsert operations should not silently drop, overwrite, or clear summary freshness fields.

## Actual Behavior
Production had many narratives with `needs_summary_update=false` and `last_summary_generated_at=null`.

During the bootstrap refresh attempt, only 2 of 5 selected narratives refreshed successfully. The other 3 selected narratives were left in or moved into an inconsistent state and were not picked up by the refresh task because their refresh flag was false.

Additional recent visible invalid narratives were found and archived as an emergency mitigation.

## Steps to Reproduce
1. Query production narratives for invalid freshness state:

   ```javascript
   db.narratives.countDocuments({
     needs_summary_update: false,
     last_summary_generated_at: null
   })
   ```

2. Observe broad legacy count:

   ```text
   341
   ```

3. Narrow to recent visible narratives:

   ```javascript
   db.narratives.find(
     {
       lifecycle_state: { $ne: "archived" },
       last_updated: { $gte: ISODate("2026-05-09T00:00:00.000Z") },
       needs_summary_update: false,
       last_summary_generated_at: null
     },
     {
       title: 1,
       lifecycle_state: 1,
       needs_summary_update: 1,
       last_summary_generated_at: 1,
       last_updated: 1,
       article_count: 1,
       status_summary: 1,
       brief_summary: 1
     }
   ).sort({ last_updated: -1 })
   ```

4. Observe 2 recent visible invalid narratives:
   - `69fe50dabd5313e9062754c7` — Solv Protocol Migrates $700M Bitcoin Assets From LayerZero to Chainlink
   - `69fd2d3a03dc7874df10099b` — TrustedVolumes Suffers $6.7M Exploit Amid Scope Disputes

## Environment
- Environment: production
- Browser/Client: MongoDB Atlas shell / production site risk
- User impact: high

## Screenshots/Logs
Emergency production actions performed on 2026-05-10:

### Deleted 3 known broken bootstrap narratives

```javascript
 db.narratives.deleteMany({
   _id: {
     $in: [
       ObjectId("68f32d197082f49df56956c6"),
       ObjectId("695eb4b3ce758d67abd6e8f4"),
       ObjectId("698baa105278ec9e19bf2a19")
     ]
   }
 })
```

Deleted narratives:
- Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
- Senate Banking Committee Advances Crypto Regulation Efforts
- LayerZero Admits Mistakes in $292M Kelp DAO Exploit

### Archived 2 additional recent visible invalid narratives

```javascript
 db.narratives.updateMany(
   {
     lifecycle_state: { $ne: "archived" },
     last_updated: { $gte: ISODate("2026-05-09T00:00:00.000Z") },
     needs_summary_update: false,
     last_summary_generated_at: null
   },
   {
     $set: {
       lifecycle_state: "archived",
       archived_reason: "temporary_hide_invalid_summary_state_before_interview",
       archived_at: new Date()
     }
   }
 )
```

Result:

```javascript
{
  acknowledged: true,
  insertedId: null,
  matchedCount: 2,
  modifiedCount: 2,
  upsertedCount: 0
}
```

### Final recent-visible invalid count

```javascript
 db.narratives.countDocuments({
   lifecycle_state: { $ne: "archived" },
   last_updated: { $gte: ISODate("2026-05-09T00:00:00.000Z") },
   needs_summary_update: false,
   last_summary_generated_at: null
 })
```

Result:

```text
0
```

### Remaining recent visible records returned by broad summary-field check
The broad check still returned SEC and Coinbase, but both had non-null `last_summary_generated_at`, so they were not in the dangerous freshness state:

- `68f03343bc9ab7390ca7af71` — SEC Signals New Rulemaking for Onchain Markets and AI Finance
  - `needs_summary_update=false`
  - `last_summary_generated_at=2026-05-10T22:25:26.991Z`

- `68f03350bc9ab7390ca7af78` — Coinbase Navigates Growth and Infrastructure Challenges
  - `needs_summary_update=false`
  - `last_summary_generated_at=2026-05-10T22:25:33.576Z`

---

## Resolution

**Status:** Open, emergency production mitigation applied
**Fixed:** Not fixed permanently
**Branch:** TBD
**Commit:** TBD

### Root Cause
Permanent root cause is not fully fixed.

Current investigation points to unsafe narrative write paths that can clear, drop, or fail to preserve summary freshness state:

1. `refresh_flagged_narratives` failure paths were already fixed in BUG-102 so refresh failures preserve `needs_summary_update=true`.
2. `narrative_service.py` upsert path may not pass/persist summary freshness state correctly for existing narratives.
3. `_merge_narratives()` may update merged survivor data without preserving or recomputing `needs_summary_update` and `last_summary_generated_at`.
4. There may be another production write path clearing `needs_summary_update=false` without writing `last_summary_generated_at`.

### Changes Made
Emergency mitigation only:

- Deleted 3 known broken bootstrap narratives.
- Archived 2 additional recent visible invalid narratives.
- Verified recent visible invalid state count is now 0 for `last_updated >= 2026-05-09T00:00:00Z`.
- Did not mass-delete or mass-archive all 341 legacy invalid-state records.
- Did not perform permanent code fix before interview prep.

### Testing
Manual production verification:

- Confirmed broad invalid-state count: 341.
- Confirmed recent visible invalid-state count: 2 after deleting the 3 known broken bootstrap records.
- Archived the 2 recent visible invalid records.
- Confirmed recent visible invalid-state count: 0.
- Confirmed the remaining recent records returned by the broader missing-summary-field query were SEC and Coinbase, both with non-null `last_summary_generated_at`.

### Files Changed
None yet. Production data was mutated directly as an emergency mitigation.

## Follow-Up Acceptance Criteria

- [ ] Add invariant: no code path can persist `needs_summary_update=false` unless `last_summary_generated_at` is non-null or written in the same atomic update.
- [ ] Audit all writes to `needs_summary_update`, `last_summary_generated_at`, `status_summary`, `brief_summary`, and `last_updated`.
- [ ] Fix `narrative_service.py` upsert path so summary freshness state is explicitly persisted when intended.
- [ ] Fix `_merge_narratives()` so merging either preserves trusted summary state safely or marks the survivor as needing refresh.
- [ ] Add tests proving merge/upsert cannot create `needs_summary_update=false` + `last_summary_generated_at=null`.
- [ ] Add audit logging when `needs_summary_update` changes.
- [ ] Decide whether to repair, archive, or ignore the 341 legacy invalid-state records.
- [ ] Add a production verification query/runbook step after the permanent fix.
