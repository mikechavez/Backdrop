---
id: BUG-088
type: bug
status: backlog
priority: critical
severity: high
created: 2026-04-16
updated: 2026-04-16
---

# Merge path does not flag narratives for summary refresh

## Problem
When `detect_narratives` in `src/crypto_news_aggregator/services/narrative_service.py` identifies that a cluster of new articles belongs to an existing narrative, it merges them via `upsert_narrative` (lines 1104-1124). The upsert updates `article_ids`, `article_count`, `last_updated`, and lifecycle fields, but does not touch `summary` and does not set `needs_summary_update: True`. The old summary persists forever.

This is the root cause of stale briefings. The April 15/16 evening briefing referenced Bitcoin at $68K from a summary written weeks ago, while the underlying narrative (`68f32d197082f49df56956c6`) had 8 fresh April articles attached reflecting current price action well above $74K.

The design intended for the merge path to flag the narrative for later refresh. The creation path at line 1193 explicitly writes `needs_summary_update: False` with the comment "Fresh summary, no update needed", implying the merge path should write `True`. That code was never written. The test at `tests/services/test_narrative_detection_matching.py:116-117` asserts the expected behavior (`assert update_data['needs_summary_update'] is True`) but passes against mocks that don't reflect production code, so the gap went undetected.

## Expected Behavior
When new articles are merged into an existing narrative and the merge meets a staleness threshold, the narrative should be flagged `needs_summary_update: True` so the refresh consumer (FEATURE-012) can regenerate the summary on its next run.

## Actual Behavior
Merge path calls `upsert_narrative` without passing any summary-related field. `needs_summary_update` is never written on the merge path. Summaries stay stale until the narrative is deleted and recreated.

## Steps to Reproduce
1. Identify an existing narrative with a summary >7 days old (e.g., `68f32d197082f49df56956c6`).
2. Wait for a clustering cycle to merge new articles into it (or trigger `detect_narratives` manually).
3. Query: `db.narratives.findOne({_id: ObjectId("68f32d197082f49df56956c6")})`.
4. Observe: `article_ids` and `article_count` grew, `last_updated` is fresh, but `summary` is unchanged and `needs_summary_update` is absent or `False`.

## Environment
- Environment: production
- User impact: high (directly causes stale briefings — the primary product output)

## Screenshots/Logs
Codebase grep evidence (session 34):
- Writers of `needs_summary_update: True`: 1 (`scripts/add_articles_to_dormant_narratives.py:85` — one-shot script, not production code)
- Writers of `needs_summary_update: False`: 1 (`narrative_service.py:1193` — creation path only)
- Readers of `needs_summary_update`: 0
- All 85 currently-flagged narratives in production were written by the one-shot script

---

## Resolution

**Status:** Completed
**Fixed:** 2026-04-18
**Branch:** feat/task-073-auto-dormant-narratives
**Commit:** (pending)

### Root Cause
Half-shipped design. Creation path writes `needs_summary_update: False`. The merge path was supposed to write `True` when articles are merged into an existing narrative, but that code was never written. The reader/consumer was also never built (tracked separately as FEATURE-012).

### Changes Made

**1. `src/crypto_news_aggregator/services/narrative_service.py` — merge path (around line 1104)**

Before the `upsert_narrative` call in the merge branch, evaluate whether the summary should be flagged for refresh. Flag as stale if ANY of:
- 3 or more net-new article_ids merged: `len(new_article_ids - existing_article_ids) >= 3`
- `lifecycle_state` transitioned into `hot` or `emerging` (i.e., `previous_state != lifecycle_state and lifecycle_state in ('hot', 'emerging')`)
- Most recent article in the merged set is >24h newer than `matching_narrative.get('last_summary_generated_at', matching_narrative.get('last_updated'))`

Add the computed flag to the `upsert_narrative` call via a new `needs_summary_update` kwarg. Example insertion point (replace the existing `try:` block starting at line 1104):

```python
# Evaluate summary staleness before upsert
net_new_article_ids = new_article_ids - existing_article_ids
previous_lifecycle = previous_state
lifecycle_promoted = (
    previous_lifecycle != lifecycle_state
    and lifecycle_state in ('hot', 'emerging')
)
last_summary_gen = matching_narrative.get('last_summary_generated_at') or matching_narrative.get('last_updated')
if last_summary_gen and last_summary_gen.tzinfo is None:
    last_summary_gen = last_summary_gen.replace(tzinfo=timezone.utc)
newest_article_date = max(article_dates) if article_dates else last_updated
article_age_gap_hours = (
    (newest_article_date - last_summary_gen).total_seconds() / 3600
    if last_summary_gen else 0
)

needs_summary_update = (
    len(net_new_article_ids) >= 3
    or lifecycle_promoted
    or article_age_gap_hours > 24
)

if needs_summary_update:
    logger.info(
        f"Flagging narrative '{title}' for summary refresh: "
        f"net_new={len(net_new_article_ids)}, lifecycle_promoted={lifecycle_promoted}, "
        f"article_age_gap_hours={article_age_gap_hours:.1f}"
    )

try:
    narrative_id = await upsert_narrative(
        theme=theme,
        title=title,
        summary=summary,
        entities=matching_narrative.get('entities', []),
        article_ids=combined_article_ids,
        article_count=updated_article_count,
        mention_velocity=round(mention_velocity, 2),
        lifecycle=matching_narrative.get('lifecycle', 'unknown'),
        momentum=matching_narrative.get('momentum', 'unknown'),
        recency_score=matching_narrative.get('recency_score', 0.0),
        entity_relationships=matching_narrative.get('entity_relationships', []),
        first_seen=first_seen,
        lifecycle_state=lifecycle_state,
        lifecycle_history=lifecycle_history,
        reawakening_count=resurrection_fields.get('reawakening_count') if resurrection_fields else None,
        reawakened_from=resurrection_fields.get('reawakened_from') if resurrection_fields else None,
        resurrection_velocity=resurrection_fields.get('resurrection_velocity') if resurrection_fields else None,
        dormant_since=dormant_since,
        needs_summary_update=needs_summary_update,  # NEW
    )
```

**2. `src/crypto_news_aggregator/services/narrative_service.py` — creation path (line 1193)**

Stamp `last_summary_generated_at` when summary is freshly generated so the merge-path staleness check has an accurate baseline:

```python
# Line 1193, replace:
narrative['needs_summary_update'] = False  # Fresh summary, no update needed
# With:
narrative['needs_summary_update'] = False  # Fresh summary, no update needed
narrative['last_summary_generated_at'] = datetime.now(timezone.utc)
```

**3. `src/crypto_news_aggregator/db/operations/narratives.py` — widen `upsert_narrative` signature**

File not in review scope — implementer must apply. Add `needs_summary_update: Optional[bool] = None` parameter. When `None`, do not include the field in the `$set` document (preserves existing behavior for any call sites that don't pass it). When a bool, include in `$set`.

```python
# In upsert_narrative signature, add:
needs_summary_update: Optional[bool] = None,

# In the $set document assembly, add:
if needs_summary_update is not None:
    update_doc['$set']['needs_summary_update'] = needs_summary_update
```

**4. `tests/services/test_narrative_detection_matching.py`**

The existing test at lines 116-117 asserts the right thing against mocks that don't reflect production. Keep the assertion shape but add a separate test that exercises the staleness threshold logic with realistic merge inputs. Suggested additions:

- `test_merge_flags_summary_update_when_three_new_articles`: merge cluster with 3 net-new articles into existing narrative, assert `update_data['needs_summary_update'] is True`
- `test_merge_does_not_flag_when_below_threshold`: merge cluster with 1 net-new article, recent summary, no lifecycle change, assert `update_data['needs_summary_update'] is False`
- `test_merge_flags_on_lifecycle_promotion`: merge where `lifecycle_state` transitions `cooling → hot`, assert flagged
- `test_creation_path_stamps_last_summary_generated_at`: new narrative inserts include `last_summary_generated_at`

### Testing
- Unit tests above pass against updated merge path
- Manual test on staging: identify a stale narrative, add articles via a test ingestion, trigger `detect_narratives`, verify `needs_summary_update: True` and `article_count` both updated in one write
- Verify creation path unchanged: new narratives still insert with `needs_summary_update: False` and now also `last_summary_generated_at`

### Files Changed
- `src/crypto_news_aggregator/services/narrative_service.py`
- `src/crypto_news_aggregator/db/operations/narratives.py`
- `tests/services/test_narrative_detection_matching.py`

### Notes
- This ticket only makes the flag writable. Without FEATURE-012 (the consumer), the flag accumulates but nothing drains it. Ship BUG-088 and FEATURE-012 in the same deploy, or ship FEATURE-012 first.
- Decision: deferred refresh (flag + consumer) chosen over inline regen. Inline would add LLM cost to every clustering cycle and would deadlock the merge path on budget limits. Deferred is cheaper and degrades gracefully.
- The `last_summary_generated_at` field is new. Existing narratives won't have it; the staleness check falls back to `last_updated`. That's acceptable — those narratives will get flagged on their next meaningful merge, which is the correct behavior.