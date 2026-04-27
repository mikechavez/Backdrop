---
id: BUG-086
type: bug
status: backlog
priority: medium
severity: medium
created: 2026-04-16
updated: 2026-04-16
---

# Signals page shows stale mentions, duplicate entities, and misleading "surging" labels

## Problem
The `/signals` page displays three distinct issues, each with a different root cause in the signals code path:

1. **"Last 24 hours" header mismatch.** The frontend renders a header suggesting signals reflect the last 24 hours, but the endpoint at `src/crypto_news_aggregator/api/v1/endpoints/signals.py:258` explicitly overrides the default by calling `compute_trending_signals(timeframe="7d", ...)`. The data shown is a 7-day trend, not 24 hours. `compute_trending_signals` itself defaults to `"24h"` (signal_service.py:668) — the endpoint is forcing a mismatch.

2. **Duplicate entity rendering.** `compute_trending_signals` aggregates `entity_mentions` by raw `$entity` field (signal_service.py:724) with no normalization step. "Stablecoin" and "stablecoins", "Exchange" and "exchanges" group as distinct entities and render as separate rows. A `normalize_entity_name` function already exists and is imported at line 22, but it's only applied inside per-entity scoring (line 464) — never in the trending aggregation pipeline.

3. **Misleading "surging" / "emerging" labels.** The `is_emerging` flag at `signal_service.py:830` is defined as `narr_info.get("count", 0) == 0` — "this entity has no associated narrative." That's a "not yet clustered" signal, not a freshness signal. An entity whose mentions are all weeks old but which happens to have no narrative still gets labeled `is_emerging: true`. Clarity Act and Bithumb fall into this bucket.

## Expected Behavior
- Signals page header timeframe matches the backend computation window.
- Duplicate entities ("Stablecoin" / "stablecoins") consolidate into a single row under their canonical form.
- `is_emerging` only fires when an entity has (a) no narrative AND (b) meaningful activity in the most recent 48 hours.

## Actual Behavior
- Frontend header says "24 hours", backend computes 7d.
- `Stablecoin` and `stablecoins` render as separate rows with separate scores.
- `is_emerging` fires on any entity without a narrative regardless of how recent its mentions are.

## Steps to Reproduce
1. Load `/signals` page in production.
2. Check header text vs. dates on rendered mentions — dates extend beyond 24h.
3. Look for case/plural duplicates in the list (Stablecoin/stablecoins, Exchange/exchanges).
4. Find an entity labeled `is_emerging: true` and query its most recent mention timestamp. If >48h old, the label is misleading.

## Environment
- Environment: production
- User impact: medium (visible UI inconsistency, erodes trust in signal accuracy, but does not block briefings or downstream systems)

## Screenshots/Logs
Code locations for the three issues:
- Timeframe override: `src/crypto_news_aggregator/api/v1/endpoints/signals.py:258`
- Entity dedup gap: `src/crypto_news_aggregator/services/signal_service.py:724` (group by raw `$entity`)
- `is_emerging` logic: `src/crypto_news_aggregator/services/signal_service.py:830`

---

## Resolution

**Status:** Open
**Fixed:** YYYY-MM-DD
**Branch:**
**Commit:**

### Root Cause
Three independent gaps:
1. The endpoint at `signals.py:258` was written to explicitly pass `timeframe="7d"` at some earlier point, and the frontend header was never updated (or was written to the spec and the backend drifted). `compute_trending_signals` default is correctly `"24h"`.
2. `compute_trending_signals` was optimized for speed (single aggregation pipeline, Atlas M0 compatibility). Normalization was skipped in that path — it exists, it's imported, but the trending path doesn't apply it.
3. `is_emerging` was implemented as a narrative-membership check, which is orthogonal to recency. The name suggests freshness but the logic checks a static property.

### Changes Made

**1. `src/crypto_news_aggregator/api/v1/endpoints/signals.py` — fix timeframe override (line 258)**

Remove the explicit override so the endpoint uses `compute_trending_signals`' default of `"24h"`:

```python
# Line 258-262, replace:
trending = await compute_trending_signals(
    timeframe="7d",
    limit=20,
    min_score=0.0,
)
# With:
trending = await compute_trending_signals(
    timeframe="24h",
    limit=20,
    min_score=0.0,
)
```

Also bump the cache key to prevent serving 7d data from a cache hit after deploy:

```python
# Line 237, replace:
cache_key = "signals:top20:v2"
# With:
cache_key = "signals:top20:v3"
```

**2. `src/crypto_news_aggregator/services/signal_service.py` — apply `normalize_entity_name` in `compute_trending_signals`**

The aggregation pipeline groups by raw `$entity`. Mongo can't call a Python function mid-pipeline, so normalization happens in Python on the aggregation output, before scoring. Merge duplicates by summing counts and taking the max latest_mention / min first_seen.

Insert this block after `results.sort(...)` on line 760 runs. Wait — clearer to do it BEFORE sort, so sort happens on deduped data. Insert immediately after line 757 (`if not results: return []`) and before the sort at line 760:

```python
# Normalize entity names and merge duplicates before sorting
# e.g., "Stablecoin" and "stablecoins" -> single canonical entry
normalized_results = {}
for doc in results:
    canonical = normalize_entity_name(doc["_id"])
    if canonical in normalized_results:
        existing = normalized_results[canonical]
        existing["total_mentions"] += doc["total_mentions"]
        existing["current_mentions"] += doc["current_mentions"]
        existing["previous_mentions"] += doc["previous_mentions"]
        if doc.get("latest_mention") and (
            not existing.get("latest_mention")
            or doc["latest_mention"] > existing["latest_mention"]
        ):
            existing["latest_mention"] = doc["latest_mention"]
        if doc.get("first_seen") and (
            not existing.get("first_seen")
            or doc["first_seen"] < existing["first_seen"]
        ):
            existing["first_seen"] = doc["first_seen"]
    else:
        normalized_doc = dict(doc)
        normalized_doc["_id"] = canonical
        normalized_results[canonical] = normalized_doc

results = list(normalized_results.values())
```

The existing sort on line 760 then operates on the deduped list.

The `source_map` lookup at lines 764-776 now queries on raw entity names but the top_entities list is canonical. Fix by fetching all source data for entities in the timeframe and collapsing in Python:

```python
# Lines 764-776, replace:
top_entities = [doc["_id"] for doc in results]
source_pipeline = [
    {
        "$match": {
            "entity": {"$in": top_entities},
            "is_primary": True,
            "created_at": {"$gte": previous_period_start},
        }
    },
    {"$group": {"_id": "$entity", "sources": {"$addToSet": "$source"}}},
]
source_results = await db.entity_mentions.aggregate(source_pipeline).to_list(length=len(top_entities))
source_map = {doc["_id"]: len(doc["sources"]) for doc in source_results}

# With:
top_entities_canonical = set(doc["_id"] for doc in results)
# Aggregate sources by raw entity, then collapse to canonical
source_pipeline = [
    {
        "$match": {
            "is_primary": True,
            "created_at": {"$gte": previous_period_start},
        }
    },
    {"$group": {"_id": "$entity", "sources": {"$addToSet": "$source"}}},
]
source_results = await db.entity_mentions.aggregate(source_pipeline).to_list(length=None)
source_sets = {}  # canonical -> set of sources
for doc in source_results:
    canonical = normalize_entity_name(doc["_id"])
    if canonical not in top_entities_canonical:
        continue
    if canonical in source_sets:
        source_sets[canonical].update(doc["sources"])
    else:
        source_sets[canonical] = set(doc["sources"])
source_map = {k: len(v) for k, v in source_sets.items()}
```

Same pattern for `narrative_counts` at lines 782-788. Narratives may store entities in non-canonical forms too:

```python
# Lines 779-788, replace:
entities = [doc["_id"] for doc in results]
narrative_counts = await db.narratives.aggregate([
    {"$match": {"entities": {"$in": entities}}},
    {"$unwind": "$entities"},
    {"$group": {"_id": "$entities", "count": {"$sum": 1}, "narrative_ids": {"$push": {"$toString": "$_id"}}}}
]).to_list(length=None)

narrative_map = {doc["_id"]: doc for doc in narrative_counts}

# With:
entities_canonical = set(doc["_id"] for doc in results)
# Fetch all narrative-entity pairs, collapse to canonical forms in Python
narrative_counts = await db.narratives.aggregate([
    {"$unwind": "$entities"},
    {"$group": {"_id": "$entities", "count": {"$sum": 1}, "narrative_ids": {"$push": {"$toString": "$_id"}}}}
]).to_list(length=None)

narrative_map = {}
for doc in narrative_counts:
    canonical = normalize_entity_name(doc["_id"])
    if canonical not in entities_canonical:
        continue
    if canonical in narrative_map:
        narrative_map[canonical]["count"] += doc["count"]
        narrative_map[canonical]["narrative_ids"].extend(doc["narrative_ids"])
    else:
        narrative_map[canonical] = {
            "count": doc["count"],
            "narrative_ids": list(doc["narrative_ids"]),
        }
# Dedupe narrative_ids (an entity may have been under multiple raw forms in same narrative)
for canonical, info in narrative_map.items():
    info["narrative_ids"] = list(set(info["narrative_ids"]))
```

**3. `src/crypto_news_aggregator/services/signal_service.py` — tighten `is_emerging` (line 820-832)**

Require recent activity in addition to narrative-absence. Define "recent" as: at least one mention in the last 48 hours. The `latest_mention` field is already in the aggregated results (line 745), so this is a free check. `now` is already in scope (defined at line 704).

```python
# Lines 820-832, replace:
signals.append({
    "entity": entity,
    "entity_type": doc.get("entity_type", "unknown"),
    "score": round(score, 2),
    "velocity": round(velocity, 2),
    "mentions": current,
    "source_count": source_count,
    "recency_factor": 0.0,  # Simplified - not computing full recency
    "sentiment": {"avg": 0.0, "min": 0.0, "max": 0.0, "divergence": 0.0},
    "narrative_ids": narr_info.get("narrative_ids", [])[:5],  # Limit to 5
    "is_emerging": narr_info.get("count", 0) == 0,
    "first_seen": doc.get("first_seen"),  # For alert detection
})

# With:
latest_mention = doc.get("latest_mention")
# Guard against naive datetimes slipping through from older data
if latest_mention is not None and latest_mention.tzinfo is None:
    latest_mention = latest_mention.replace(tzinfo=timezone.utc)

has_recent_activity = (
    latest_mention is not None
    and (now - latest_mention) <= timedelta(hours=48)
)
is_emerging = (
    narr_info.get("count", 0) == 0
    and has_recent_activity
)

signals.append({
    "entity": entity,
    "entity_type": doc.get("entity_type", "unknown"),
    "score": round(score, 2),
    "velocity": round(velocity, 2),
    "mentions": current,
    "source_count": source_count,
    "recency_factor": 0.0,
    "sentiment": {"avg": 0.0, "min": 0.0, "max": 0.0, "divergence": 0.0},
    "narrative_ids": narr_info.get("narrative_ids", [])[:5],
    "is_emerging": is_emerging,
    "first_seen": doc.get("first_seen"),
})
```

### Testing

**Unit tests (add to `tests/services/test_signal_service.py`):**

- `test_compute_trending_signals_merges_case_variants`: seed `entity_mentions` with mentions for "Stablecoin" and "stablecoins" across the same 24h window, call `compute_trending_signals(timeframe="24h")`, assert exactly one signal returned with entity equal to the canonical form and mentions count equal to the sum
- `test_compute_trending_signals_merges_plurals`: same shape for "Exchange" and "exchanges"
- `test_is_emerging_false_when_mentions_stale`: seed an entity with all mentions >72h old and no narrative, assert `is_emerging is False` in the returned signal
- `test_is_emerging_true_when_no_narrative_and_recent_activity`: entity with mentions in last 24h and no narrative, assert `is_emerging is True`
- `test_is_emerging_false_when_narrative_exists`: entity with recent mentions AND a narrative containing it, assert `is_emerging is False`

**Integration test on staging:**
- Verify `/signals` response has no case/plural duplicates
- Query each returned signal's `latest_mention` against `is_emerging` — no entity with `is_emerging: true` should have `latest_mention` older than 48h
- Verify frontend network request shows 24h timeframe data (date range of rendered mentions)

### Files Changed
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py`
- `src/crypto_news_aggregator/services/signal_service.py`
- `tests/services/test_signal_service.py`

### Notes
- Independent of BUG-088 / FEATURE-012 / FEATURE-013 / BUG-087. Ships in parallel.
- The narrative_counts aggregation change removes the `$match: {"entities": {"$in": entities}}` pre-filter. On Atlas M0 this may be slower since it scans all narratives instead of only relevant ones. If profiling after deploy shows a regression, re-introduce a broadened pre-filter that includes both canonical and non-canonical variants of each entity (generate with `normalize_entity_name` + known plural/singular pairs), then filter in Python.
- `is_emerging` behavior shifts semantically — fewer entities will wear the badge. That's the intended effect. Worth flagging in any deploy announcement.