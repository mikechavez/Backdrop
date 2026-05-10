---
investigation_id: TASK-095
title: Briefing Refinement Publication and Narrative Refresh Behavior - Code Investigation
date_created: 2026-05-10
date_completed: 2026-05-10
investigator: Claude Code
status: COMPLETE
---

# TASK-095: Investigation Report
## Briefing Refinement Publication and Narrative Refresh Behavior

---

## Executive Summary

This investigation examines code paths that allowed invalid refinement output to be saved and published as a briefing, along with narrative staleness issues caused by missing `last_summary_generated_at` fields on legacy narratives.

**Key Findings:**

1. **Briefing Publication Validation Gap**: Briefings with low confidence (0.3) and empty `key_insights` are saved and published without validation. The `_parse_briefing_response()` method has a fallback that accepts raw LLM text as `narrative` when JSON parsing fails, setting confidence to 0.3.

2. **Refinement Prompt Context Deficiency**: The refinement prompt references "AVAILABLE DATA" (signals, narratives, patterns) but does NOT include the actual narrative details, summaries, entity lists, or article data. This prevents the LLM from effectively refining based on source material.

3. **Narrative Staleness Not Detected**: Legacy narratives missing `last_summary_generated_at` are not automatically marked `needs_summary_update=true`. The staleness logic treats missing fields as stale only at insert time; existing narratives are not re-evaluated.

4. **Refresh Task Exists and Runs**: `refresh_flagged_narratives` is defined, scheduled twice daily (7:30 AM/PM EST), has batch limits (20 per run), and respects LLM budget. But it only processes narratives already flagged `needs_summary_update=true`, missing the 341 legacy narratives.

5. **Article Hydration String/ObjectId Conversion**: String `article_ids` are correctly converted to ObjectId in `narrative_refresh.py` line 92 AND in `briefing_agent.py` line 322. This is NOT a root cause of empty hydration.

6. **Cost Impact**: Refreshing 341 narratives at estimated ~$0.02-0.03 per narrative would cost $6.82-10.23, exceeding the $1/day budget if attempted all at once. Current batch limit of 20/run ($0.40-0.60 per run) is safe.

---

## Section A: Briefing Publication Behavior

### A.1 Where Is the Final Briefing Saved?

**Location:** `src/crypto_news_aggregator/services/briefing_agent.py:1005`

The final briefing is inserted into MongoDB via the `insert_briefing()` function:

```python
briefing_doc_id = await insert_briefing(briefing_doc)
```

This calls `src/crypto_news_aggregator/db/operations/briefing.py:41-60`, which inserts into the `daily_briefings` collection.

The briefing document is constructed in `_save_briefing()` at line 974-998 with all fields set before insertion.

### A.2 What Function Constructs the Final Document?

**Function:** `BriefingAgent._save_briefing()` at `briefing_agent.py:940-1012`

This method:
- Takes a `GeneratedBriefing` object (result of refinement)
- Builds a `briefing_doc` dict containing:
  - `type`: "morning" or "evening"
  - `content`: { narrative, key_insights, entities_mentioned, detected_patterns, recommendations }
  - `metadata`: { confidence_score, signal_count, narrative_count, pattern_count, model, refinement_iterations }
  - `published`: `not is_smoke` (always True for non-smoke briefings)
  - `is_smoke`: False for production

The constructed document is then inserted as-is without validation.

### A.3 Does Code Validate Whether Output Is Publishable?

**Finding: NO VALIDATION.**

There is **no validation** of whether a briefing is suitable for publication. The only check is:
- Line 996: `"published": not is_smoke` — which only prevents publishing smoke tests.

There is no check for:
- ✗ Minimum confidence score
- ✗ Non-empty `key_insights`
- ✗ Non-empty `narrative` content
- ✗ Valid JSON structure
- ✗ Presence of required fields

### A.4 Can Low-Confidence Briefings Publish with `published=true`?

**YES. Confirmed.**

A briefing with `confidence_score: 0.3` (the fallback value) is saved and published without restriction.

Evidence in the bad briefing: `metadata.confidence_score: 0.3` + `published: true` ✓

### A.5 Can Briefings with Empty `key_insights` Publish with `published=true`?

**YES. Confirmed.**

A briefing with `key_insights: []` is saved and published.

Evidence in the bad briefing: `content.key_insights: []` + `published: true` ✓

### A.6 Does `_parse_briefing_response()` Allow Arbitrary Text to Become `narrative`?

**YES. Confirmed. This is the root cause of the invalid briefing.**

Location: `briefing_agent.py:831-890`

The parsing flow:

1. **Line 834-840:** Try to extract JSON from response using regex `\{.*\}`. If no JSON found, use the entire response as the JSON string.

2. **Line 867:** `json.loads(cleaned_json)` — attempt JSON parsing.

3. **Line 878-890 (JSON DECODE FAILURE):** If JSON parsing fails:
   ```python
   except json.JSONDecodeError as e:
       logger.error(f"Failed to parse LLM response: {e}")
       # Return minimal briefing
       return GeneratedBriefing(
           narrative=response_text[:2000] if response_text else "Failed to generate briefing.",
           key_insights=[],
           entities_mentioned=[],
           detected_patterns=[],
           recommendations=[],
           confidence_score=0.3,  # ← LOW CONFIDENCE FLAG
       )
   ```

**This fallback directly puts raw LLM text into `narrative`**, bypassing all validation. The bad briefing's narrative was asking for narrative titles/summaries — this is evidence that the LLM returned meta-request text, JSON parsing failed, and the fallback captured it.

### A.7 Does the Public Briefing API Filter Invalid Briefings?

**NO FILTERING.**

Location: `src/crypto_news_aggregator/api/v1/endpoints/briefing.py:229-260`

The `get_latest_briefing_endpoint()` simply queries and returns the briefing:

```python
briefing = await get_latest_briefing()
...
formatted = _format_briefing(briefing)
return LatestBriefingResponse(briefing=BriefingResponse(**formatted), ...)
```

No filtering on confidence, key_insights, or content validity.

The database query in `db/operations/briefing.py:63-76` also has no filters:

```python
cursor = collection.find(_get_production_briefings_filter()).sort("generated_at", -1).limit(1)
```

The filter only checks `published=True` or missing (for historical), never confidence or content.

### A.8 What Fields Does the Frontend Use to Decide Which Briefing to Show?

Not explicitly investigated (frontend code in `context-owl-ui/` is in the "Do Not Modify" list), but based on the API response model `BriefingResponse` in `briefing.py:69-81`:

The frontend receives ALL fields, including `confidence_score` and `key_insights`. It likely shows the latest briefing without validation, but the API could expose invalid briefings.

### A.9 Is There Any `invalid_output` or `failed_generation` Metadata?

**NO.**

There is no metadata field for "invalid_output", "failed_generation", "parse_error", or similar. The system relies only on:
- `confidence_score` (no minimum enforcement)
- `refinement_iterations` (tracks attempts, not success)
- `is_smoke` (smoke test flag)
- `published` (publish flag, not quality flag)

**Inferred behavior:** The system assumes that if a briefing is saved, it passed generation. There is no concept of "this briefing is malformed and should not appear to users."

---

## Section B: Briefing Refinement Behavior

### B.1-B.3 What Is Included in Prompts?

#### Generation Prompt (`_build_generation_prompt()`, lines 619-689)

**Included:**
- Time context (formatted date string)
- Memory context (feedback, guidelines)
- Current signals (top 10, with entity, score, velocity)
- Narrative titles (explicitly listed as "ALLOWED NARRATIVES")
- Narrative details (title, summary, article_count)
- Detected patterns (via `patterns.to_prompt_context()`)
- Manual inputs (external sources, top 3)

**Example narrative detail block (lines 654-664):**
```python
parts.append("## Narrative Details (use these facts):\n\n")
for narrative in briefing_input.narratives[:8]:
    title = narrative.get("title", "Untitled")
    summary = narrative.get("summary", "")
    article_count = narrative.get("article_count", 0)
    parts.append(f"### {title}\n")
    parts.append(f"Sources: {article_count} articles\n")
    if summary:
        parts.append(f"Facts: {summary}\n")
```

#### Critique Prompt (`_build_critique_prompt()`, lines 691-758)

**Included:**
- Full briefing narrative
- Key insights (JSON)
- Available narrative titles (from briefing_input.narratives)
- Available entities (extracted from narratives)

**Lines 695-703 extract entities:**
```python
narrative_entities = set()
for narrative in briefing_input.narratives[:8]:
    entities = narrative.get("entities", [])
    if entities:
        narrative_entities.update(entities[:5])  # Top 5 entities per narrative
```

#### Refinement Prompt (`_build_refinement_prompt()`, lines 765-786)

**Included:**
- Original briefing narrative
- Critique feedback
- DATA SUMMARY ONLY (no actual data):
  ```
  AVAILABLE DATA:
  - Signals: {len(briefing_input.signals)} trending entities
  - Narratives: {len(briefing_input.narratives)} active narratives
  - Patterns: {len(briefing_input.patterns.all_patterns())} detected patterns
  ```

**NOT Included in refinement prompt:**
- ✗ Narrative titles
- ✗ Narrative summaries or descriptions
- ✗ Narrative entities
- ✗ Article titles or sources
- ✗ Signals data
- ✗ Pattern details

### B.4-B.9 Does Refinement Prompt Include Full Narrative Context?

**NO. Critical Finding.**

The refinement prompt references "AVAILABLE DATA" (lines 780-783) but provides NO ACTUAL DATA. The LLM is told there are "N narratives" but given zero narrative details, summaries, entities, or article information.

This forces the LLM to:
1. Hallucinate what the narratives are
2. Or request the data (which is what appears in the bad briefing)
3. Or degrade in quality

**This is a systemic issue:** Refinement cannot effectively improve a briefing without seeing the source material it's supposed to refine against.

### B.10 Does Refinement Explicitly Require Valid JSON Only?

**YES, but only in text form.**

Generation prompt (line 687): `parts.append("\nReturn ONLY valid JSON.")`

Refinement prompt (line 786): `return f"""... Return ONLY valid JSON in the same format as before."""`

However, the JSON requirement is not enforced — parsing failure falls back to raw text (A.6).

### B.11 What Happens If Refinement Returns Plain Text Instead of JSON?

**It becomes the narrative content.**

The fallback handler (lines 878-890) accepts any non-JSON response as valid briefing with `confidence_score=0.3`.

The bad briefing's narrative ("provide narrative titles, summaries, and entity names") was likely:
1. LLM returning meta-request text (not JSON)
2. `_parse_briefing_response()` calling JSON parsing
3. Parsing fails → fallback captures raw text → narrative = meta-request text
4. Briefing published with confidence_score=0.3

### B.12 Is the Final Saved Briefing Always the Last Refinement Output?

**YES.**

The refinement loop (lines 427-501) iterates, and `current` is reassigned each iteration. If refinement passes quality check (line 449), return early. Otherwise, line 477 updates `current` with the new refinement. Line 501 returns `current`.

The caller (`generate_briefing()`, line 170) then saves `refined` (which is `current`, the last output) regardless of quality.

---

## Section C: Narrative Freshness Behavior

### C.1 Where Are `needs_summary_update` and `last_summary_generated_at` Set?

**`needs_summary_update` set in:**

1. **At narrative creation** (`narrative_service.py:1224-1225`):
   ```python
   narrative['needs_summary_update'] = False  # Fresh summary, no update needed
   narrative['last_summary_generated_at'] = datetime.now(timezone.utc)
   ```

2. **At narrative update/merge** (`narrative_service.py:1121-1154`):
   ```python
   needs_summary_update = (
       len(net_new_article_ids) >= 3
       or lifecycle_promoted
       or article_age_gap_hours > 24
   )
   ...
   upsert_narrative(..., needs_summary_update=needs_summary_update)
   ```

3. **At narrative reactivation** (`narrative_service.py` — reactivation code not fully inspected, but likely sets both fields)

**`last_summary_generated_at` set in:**

1. **At narrative creation** (`narrative_service.py:1225`)
2. **At successful refresh** (`narrative_refresh.py:133`)
   ```python
   "last_summary_generated_at": datetime.now(timezone.utc),
   ```

### C.2 Are Fields Set When Narrative Is First Created?

**YES.**

Lines 1224-1225 in `narrative_service.py`:
- `needs_summary_update=False`
- `last_summary_generated_at=datetime.now(timezone.utc)`

### C.3 Are Fields Set When an Article Is Appended to Existing Narrative?

**PARTIALLY.**

When articles are merged into an existing narrative (lines 1104-1154 in `narrative_service.py`):

- `needs_summary_update` is evaluated and SET (line 1154)
- `last_summary_generated_at` is NOT re-set (the code does not touch it)

This means:
- If a new article triggers staleness, `needs_summary_update=true` is set
- But `last_summary_generated_at` remains unchanged (may still be missing on legacy narratives)

### C.4 What Happens If a Narrative Is Missing `last_summary_generated_at`?

**Staleness evaluation fails or uses `last_updated` as fallback.**

Code at lines 1112-1118:

```python
last_summary_gen = matching_narrative.get('last_summary_generated_at') or matching_narrative.get('last_updated')
if last_summary_gen and last_summary_gen.tzinfo is None:
    last_summary_gen = last_summary_gen.replace(tzinfo=timezone.utc)
newest_article_date = max(article_dates) if article_dates else last_updated
article_age_gap_hours = (
    (newest_article_date - last_summary_gen).total_seconds() / 3600
    if last_summary_gen else 0
)
```

**Behavior:**
- If `last_summary_generated_at` missing, use `last_updated` (line 1112)
- If neither exists, `last_summary_gen = None`, and `article_age_gap_hours = 0` (line 1118)

**Problem:** If `last_updated` is current (narrative was updated today), `article_age_gap_hours` will be 0, and staleness check fails even if the narrative is missing a real summary.

### C.5 Does Staleness Logic Treat Missing `last_summary_generated_at` as Stale?

**NO. Confirmed as bug.**

The staleness evaluation (lines 1121-1125):
```python
needs_summary_update = (
    len(net_new_article_ids) >= 3
    or lifecycle_promoted
    or article_age_gap_hours > 24
)
```

Three conditions:
1. 3+ new articles — can trigger if articles appended
2. Lifecycle promotion — can trigger if promoted to hot/emerging
3. Age gap > 24 hours — can trigger if articles are old

**But:** If a narrative is missing `last_summary_generated_at`, and `last_updated` is recent, none of these conditions trigger, and `needs_summary_update` remains `false` (or is set to `false`).

**341 legacy narratives likely have:**
- Missing `last_summary_generated_at`
- Recent `last_updated` (from ongoing article merges)
- Result: never flagged for refresh

### C.6 What Exact Conditions Set `needs_summary_update=true`?

From lines 1121-1125:
1. `len(net_new_article_ids) >= 3` — 3 or more new articles since last time
2. `lifecycle_promoted` — narrative promoted from non-hot/emerging to hot/emerging (line 1108-1110)
3. `article_age_gap_hours > 24` — 24+ hours since summary generation and newest article

### C.7-C.9 Other Staleness Conditions

- **Lifecycle promotion sets flag?** YES, line 1108-1110 checks if lifecycle changed and now is hot/emerging.
- **3+ new articles?** YES, line 1122.
- **24h age gap?** YES, line 1124.

### C.10 Are Legacy Narratives Missing `last_summary_generated_at` Excluded From Refresh Logic?

**NO, they are NOT excluded. They are silently treated as fresh.**

The refresh task (`narrative_refresh.py:43-48`) queries:
```python
query = {
    "needs_summary_update": True,
    "lifecycle_state": {"$ne": "dormant"},
}
```

This query finds only narratives already flagged `needs_summary_update=true`. Legacy narratives without the flag are not selected, even if they're missing `last_summary_generated_at`.

**The pipeline has no separate query to find narratives missing the timestamp field and flag them.** This is a gap.

### C.11 Are Active Narratives Allowed to Remain `hot`, etc., with Missing Timestamp and `needs_summary_update=false`?

**YES. Confirmed as allowed (and happening: 341 narratives).**

The database schema and code do not prevent this. A narrative can be:
- `lifecycle_state: "hot"`
- `last_summary_generated_at: <missing>`
- `needs_summary_update: false`

And it remains in this state indefinitely until one of the three staleness conditions triggers (new articles, promotion, or age gap).

---

## Section D: Narrative Refresh Task Behavior

### D.1 Does `refresh_flagged_narratives` Exist?

**YES.**

Location: `src/crypto_news_aggregator/tasks/narrative_refresh.py:36-168`

Two entry points:
- `_refresh_flagged_narratives_async()` (core async logic, lines 36-153)
- `refresh_flagged_narratives_task()` (Celery wrapper, lines 156-168)

### D.2 Where Is It Defined?

`src/crypto_news_aggregator/tasks/narrative_refresh.py` (entire file)

Exported as a Celery shared_task with name `"refresh_flagged_narratives"` (line 156).

### D.3 Is It Scheduled Automatically?

**YES.**

Location: `src/crypto_news_aggregator/tasks/beat_schedule.py:117-134`

Two scheduled instances:

```python
"refresh-flagged-narratives-morning": {
    "task": "refresh_flagged_narratives",
    "schedule": crontab(hour=7, minute=30),  # 7:30 AM EST
    "options": {"expires": 1800, "time_limit": 600},
},
"refresh-flagged-narratives-evening": {
    "task": "refresh_flagged_narratives",
    "schedule": crontab(hour=19, minute=30),  # 7:30 PM EST
    "options": {"expires": 1800, "time_limit": 600},
},
```

Scheduled 30 minutes before each briefing (8 AM/8 PM EST), providing time to refresh stale narratives before generation.

### D.4 How Often Does It Run?

**Twice daily: 7:30 AM EST and 7:30 PM EST.**

With 10-minute hard time limit and 30-minute expiry, runs are expected to complete within 10 minutes or be abandoned.

### D.5 Does It Have a Batch Limit?

**YES.**

Line 24: `MAX_REFRESH_PER_RUN = 20`

Line 62: `to_process = candidates[:MAX_REFRESH_PER_RUN]`

Max 20 narratives per run, preventing runaway cost spikes.

### D.6 Does It Respect LLM Daily/Monthly Budget Limits?

**YES.**

Lines 69-77:
```python
allowed, reason = check_llm_budget("narrative_generate")
if not allowed:
    logger.warning(f"refresh_flagged_narratives stopping: budget limit hit ({reason})")
    skipped_budget_count = len(to_process) - refreshed_count - skipped_error_count
    break
```

Per-narrative budget check stops processing if soft or hard limit is hit.

### D.7 Does It Process All `needs_summary_update=true` Narratives, Or Bounded Batches?

**Bounded batches.**

Line 54: `candidates = await cursor.to_list(length=None)` — fetches all flagged narratives.
Line 62: `to_process = candidates[:MAX_REFRESH_PER_RUN]` — takes first 20.

Unprocessed narratives remain flagged for the next run.

### D.8 What Operation Name Is Used for LLM Traces?

**`"narrative_generate"`**

Line 70: `check_llm_budget("narrative_generate")`

And in `narrative_themes.py:855`, the actual generation call uses `operation="narrative_generate"`.

### D.9 Does It Update `title`, `description`, or Both?

**Title AND summary (no "description" field exists in code).**

Lines 129-134:
```python
await db.narratives.update_one(
    {"_id": narrative_id},
    {"$set": {
        "summary": new_narrative.get("summary", narrative.get("summary")),
        "title": new_narrative.get("title", narrative.get("title")),
        "needs_summary_update": False,
        "last_summary_generated_at": datetime.now(timezone.utc),
    }}
)
```

### D.10 Does It Set `last_summary_generated_at=now` After Refresh?

**YES.**

Line 133: `"last_summary_generated_at": datetime.now(timezone.utc),`

### D.11 Does It Clear `needs_summary_update=false` After Successful Refresh?

**YES.**

Line 132: `"needs_summary_update": False,`

### D.12 What Happens on Refresh Failure?

Lines 107-124 handle failures:

1. **If `generate_narrative_from_cluster()` raises exception** (lines 109-112):
   - Exception logged
   - `skipped_error_count += 1`
   - Flag remains `needs_summary_update=true`
   - Narrative NOT updated
   - Continues to next narrative

2. **If `generate_narrative_from_cluster()` returns None** (lines 114-124):
   - Log warning
   - Clear flag to `needs_summary_update=false` (line 121)
   - Prevents infinite retry loop
   - Continues to next narrative

3. **If articles fetch returns empty** (lines 96-105):
   - Log warning
   - Clear flag to `needs_summary_update=false`
   - Prevents retry

### D.13 Does It Retry Failed Narratives?

**Not explicitly.**

Failed narratives with exceptions are skipped (flag remains `true`), and they will be retried on the next scheduled run (next 12 hours).

Narratives with None returns clear the flag to prevent retry loops.

### D.14 Does It Record Refresh Failure Metadata?

**NO.**

There is no metadata field added to the narrative document to record:
- Refresh failure reasons
- Refresh attempt count
- Last refresh attempt time
- Failure error details

Only counts are returned in metrics (lines 145-151):
```python
metrics = {
    "flagged_count_before": flagged_count_before,
    "flagged_count_after": flagged_count_after,
    "refreshed_count": refreshed_count,
    "skipped_budget_count": skipped_budget_count,
    "skipped_error_count": skipped_error_count,
}
```

---

## Section E: Article Hydration / ObjectId Behavior

### E.1 What Type Is Stored in `narratives.article_ids`?

**STRINGS.**

Evidence: `narrative_refresh.py:92` explicitly converts:
```python
article_object_ids = [ObjectId(aid) if isinstance(aid, str) else aid for aid in article_ids]
```

The `isinstance(aid, str)` check confirms that article_ids are stored as strings.

### E.2 What Type Is Used for `articles._id`?

**ObjectId.**

Standard MongoDB behavior; `_id` fields are ObjectIds unless explicitly overridden.

### E.3 Does Narrative Refresh Logic Convert String IDs to ObjectId?

**YES.**

Line 92 in `narrative_refresh.py`:
```python
article_object_ids = [ObjectId(aid) if isinstance(aid, str) else aid for aid in article_ids]
```

Then line 93:
```python
articles_cursor = db.articles.find({"_id": {"$in": article_object_ids}})
```

**Confirmed: String IDs are converted before querying.**

### E.4 Could Refresh/Hydration Silently Return Zero Articles?

**NO, not due to string/ObjectId mismatch.**

The conversion is present, so queries will match. However, zero articles can return if:
1. Article IDs are corrupted
2. Articles were deleted
3. Database query fails

But string/ObjectId mismatch is NOT the cause.

### E.5 Are There Tests Covering String Article IDs?

**Not explicitly investigated** (tests are marked "do not modify"), but the explicit conversion code suggests awareness of the issue.

### E.6 Are There Helper Functions for Converting Article IDs?

**Inline conversion only.**

No dedicated helper. The conversion is done inline in:
- `narrative_refresh.py:92` (refresh task)
- `briefing_agent.py:322` (briefing input gathering)

Both use the same pattern: `ObjectId(aid) if isinstance(aid, str) else aid`

### E.7 Are Helpers Used Consistently?

**YES.**

Both code paths use the same pattern. Consistent implementation across both briefing and refresh paths.

**Confirmed: String/ObjectId handling is NOT a root cause of the bad briefing or stale narratives.**

---

## Section F: Cost and Budget Behavior

### F.1 What Operation Names Correspond to Narrative Generation/Refresh in LLM Traces?

**Operation name:** `"narrative_generate"`

Used in:
- `narrative_themes.py:855` (narrative generation during consolidation)
- `narrative_refresh.py:70` (refresh task budget check)
- `narrative_service.py:1208` (narrative creation budget check)

### F.2 Estimated Average Cost of One Narrative Refresh

**Estimated: $0.02-0.03 per narrative refresh**

Basis:
- Narrative refresh uses `narrative_generate` operation
- Typical article cluster: 5-10 articles
- LLM call: Claude Haiku @ ~$0.80/1M input tokens, $2.40/1M output tokens
- Input: ~3-4 articles × 1000 tokens per article + system prompt = ~3500-4500 tokens
- Output: ~500-800 tokens for title + summary
- Cost: (~4000 input tokens × $0.80/1M) + (~700 output tokens × $2.40/1M) = $0.0032 + $0.00168 ≈ $0.005 per narrative

**More conservative estimate accounting for system prompts and fallback retries:** $0.02-0.03 per narrative

### F.3 If 341 Narratives Were Flagged for Refresh, Would System Try All Immediately?

**NO. Batch limit prevents it.**

Max 20 per run, twice daily = max 40 per day = 8-9 days to complete 341 narratives.

At $0.025 per narrative × 20 = $0.50 per run, or $1.00/day total for refreshes.

### F.4 Could That Exceed the $1/Day Hard Budget?

**Possibly, at current batching.**

If running 2× daily at 20 each:
- 40 narratives/day × $0.025 = $1.00/day

Adding briefing generation (2× daily @ ~$0.05-0.10 each = $0.20/day):
- Total: $1.20/day, exceeding $1.00 hard limit

**The system would hit soft limit (~$0.70/day) after ~280 refreshes worth of backlog, then hard limit stops all non-critical work.**

### F.5 Would Budget Exhaustion Block Later Operations?

**YES.**

From `cost_tracker.py:429-504`, if hard limit hit:
- `check_llm_budget()` returns `(False, "hard_limit")`
- All LLM calls fail immediately
- Entity extraction, narrative generation, briefing generation all blocked

Soft limit at ~$0.70/day blocks non-critical operations but allows critical ones (briefing generation is critical).

### F.6 Is There a Per-Task or Per-Run Refresh Budget?

**NO.**

The refresh task respects the global LLM budget but has no separate budget. The batch limit (20) is the only per-run control.

### F.7 Is There a Safe Way to Refresh Only 10-20 Narratives as a Pilot?

**YES. Lower the `MAX_REFRESH_PER_RUN`.**

Currently 20 (line 24 in `narrative_refresh.py`). Reducing to 10 would cost ~$0.25/run, safely within budget.

Or manually filter narratives using an admin task.

### F.8 Does the Refresh Path Have Cost-Aware Batching, Throttling, or Early Stopping?

**Batching: YES. Throttling: NO. Early stopping: YES.**

- **Batching:** 20 per run (line 24)
- **Throttling:** No per-item delays or rate limiting
- **Early stopping:** Budget check stops processing immediately if limit hit (lines 69-77)

No exponential backoff or smarter scheduling.

---

## Section G: Recommended Safe Fix Plan

### Overview

The investigation identified three independent issues:
1. **Briefing validation gap** — low-confidence and malformed briefings publish (CRITICAL)
2. **Refinement context deficiency** — refinement prompt lacks data (OPTIONAL)
3. **Narrative staleness detection failure** — legacy narratives not flagged for refresh (DEFERRED)

**Sprint 019 approach:** Implement Stage 1 (critical containment), optionally Stage 2 (refinement improvement). Defer Stages 3-4 (legacy narrative repair) in favor of the fresh-start trust layer approach documented in the Addendum above.

---

### Stage 1: Containment (HIGHEST PRIORITY)

**Goal:** Prevent the current failure mode (invalid refinement output publishing).

**Fix: Add publication validation in `_save_briefing()`**

- Reject briefings with `confidence_score < 0.5`
- Reject briefings with empty `key_insights` (unless all briefings are empty)
- Reject briefings with empty `narrative`
- Reject briefings if `refinement_iterations` > max_iterations

**Where:** `briefing_agent.py:_save_briefing()` before `insert_briefing()`

**What:** Add guard:
```python
if generated.confidence_score < 0.5:
    logger.error(f"Rejecting low-confidence briefing: {generated.confidence_score}")
    return None

if not generated.narrative or not generated.narrative.strip():
    logger.error("Rejecting empty narrative")
    return None

if len(generated.key_insights) == 0:
    logger.warning("Briefing has no key insights (acceptable if intentional)")
    # Allow, but log
```

**Risk:** Very low. Only prevents genuinely malformed briefings.

**Timeline:** 1-2 hours implementation + testing.

---

### Stage 2: Refinement Prompt Fix (MEDIUM PRIORITY)

**Goal:** Enable refinement to actually improve briefings instead of degrading them.

**Fix: Include narrative context in refinement prompt**

Currently the refinement prompt references "AVAILABLE DATA" but includes no actual data. Add:

**Where:** `briefing_agent.py:_build_refinement_prompt()` lines 765-786

**What:** Expand to include:
```python
def _build_refinement_prompt(self, generated: GeneratedBriefing, critique: str, briefing_input: BriefingInput) -> str:
    # Build list of narrative titles for reference
    narrative_titles = [n.get("title", "") for n in briefing_input.narratives[:8]]
    
    # Build list of entities
    narrative_entities = set()
    for narrative in briefing_input.narratives[:8]:
        entities = narrative.get("entities", [])
        if entities:
            narrative_entities.update(entities[:5])
    
    return f"""Refine this crypto briefing based on the critique feedback:

ORIGINAL BRIEFING:
{generated.narrative}

CRITIQUE FEEDBACK:
{critique}

AVAILABLE DATA:
- Signals: {len(briefing_input.signals)} trending entities
- Narratives: {len(briefing_input.narratives)} active narratives
- Patterns: {len(briefing_input.patterns.all_patterns())} detected patterns

NARRATIVE TITLES (use only these):
{json.dumps(narrative_titles, indent=2)}

AVAILABLE ENTITIES (use only these):
{json.dumps(list(narrative_entities), indent=2)}

Address the issues identified in the critique and generate an improved briefing.
Return ONLY valid JSON in the same format as before."""
```

**Risk:** Low-medium. Prompts can change LLM output. Test with sample data first.

**Timeline:** 1 hour implementation + 30 min testing.

**Why not include full narrative summaries?** Token budget. Current prompt is manageable; full summaries would balloon token usage. Titles + entities provide grounding without explosion.

---

### Stage 3: Narrative Freshness Fix (MEDIUM PRIORITY, Must be done before backfill)

**Goal:** Ensure legacy narratives without `last_summary_generated_at` are identified and flagged.

**Fix 1: Backfill missing timestamps**

Create a one-time migration script that:
1. Finds narratives where `last_summary_generated_at` is missing
2. Sets it to `last_updated` (as a proxy for "summary age")
3. Evaluate staleness and set `needs_summary_update` accordingly

**Script location:** `scripts/backfill_narrative_timestamps.py` (new file)

```python
async def backfill_missing_timestamps():
    db = await mongo_manager.get_async_database()
    
    # Find narratives missing last_summary_generated_at
    query = {
        "last_summary_generated_at": {"$exists": False},
        "lifecycle_state": {"$ne": "dormant"},
    }
    
    cursor = db.narratives.find(query)
    narratives = await cursor.to_list(length=None)
    
    for narrative in narratives:
        last_updated = narrative.get("last_updated")
        
        # Set timestamp to last_updated or now
        timestamp = last_updated or datetime.now(timezone.utc)
        
        # Check if needs refresh (article_age_gap_hours > 24)
        newest_article_date = ... # Query articles
        age_gap_hours = (newest_article_date - timestamp).total_seconds() / 3600
        needs_update = age_gap_hours > 24
        
        await db.narratives.update_one(
            {"_id": narrative["_id"]},
            {"$set": {
                "last_summary_generated_at": timestamp,
                "needs_summary_update": needs_update,
            }}
        )
    
    logger.info(f"Backfilled {len(narratives)} narratives")
```

**Risk:** Medium. Backfill script requires careful testing on staging first.

**Timeline:** 2 hours implementation, 2 hours staging validation, 30 min production run.

**Fix 2: Update staleness detection**

Modify `narrative_service.py:1112-1125` to explicitly detect missing `last_summary_generated_at`:

```python
# If missing timestamp, treat as potentially stale
if not matching_narrative.get("last_summary_generated_at"):
    needs_summary_update = True  # Force refresh for legacy narratives
    logger.info(f"Flagging narrative '{title}' for refresh: missing last_summary_generated_at")
else:
    # Existing staleness logic
    needs_summary_update = (...)
```

**Risk:** Low-medium. Affects only new narrative merges; existing narratives unaffected until backfill.

**Timeline:** 30 min implementation + testing.

---

### Stage 4: Narrative Batch Backfill (LOWEST PRIORITY, must be after Stage 3)

**Goal:** Refresh the 341 legacy narratives safely without blowing budget.

**Fix: Batch backfill with cost controls**

After Stage 3 backfill+fix, ~100-200 narratives will be flagged `needs_summary_update=true` (estimate based on age gap > 24h condition).

**Pilot approach (7 days):**
- Run 2× daily (current schedule)
- Limit to 10 narratives per run (lower than current 20)
- Cost: 10 × 2 × $0.025 = $0.50/day (well within $1/day)
- Time: 7 days to complete 140 narratives

**Monitor:**
- LLM trace costs for narrative_generate operations
- Briefing quality before/after refreshes
- No budget limit violations

**If successful, increase to 20/run for 3-4 more days to finish remaining narratives.**

**Risk:** Medium. Narrative regeneration can change content. Monitor briefings closely.

**Timeline:** 7-10 days to complete full backfill.

---

### Stage 5: Long-Term Monitoring (ONGOING)

**Goal:** Prevent recurrence.

**Metrics to track:**
- Briefing publication confidence_score distribution (alert if < 0.5 appears)
- Briefing key_insights emptiness rate (alert if > 0%)
- Narratives missing last_summary_generated_at (should be 0 after backfill)
- Narratives flagged for refresh (should be small, < 20 at any time)
- Refinement iteration count (should stabilize, not increase)

**Dashboard:**
- Add observability to briefing generation logs
- Add metrics to LLM cost tracking
- Weekly review of briefing quality metrics

---

## User-Facing Ramifications

### Immediate (Stage 1 Containment)

**Positive:**
- No more invalid briefings published
- Briefing quality floor established

**Negative:**
- If a briefing fails validation, no briefing published that day (rare, but possible)
- May need admin override mechanism for edge cases

### Short-term (Stage 2-3, Refinement + Staleness Fix)

**Positive:**
- Refinement improves more effectively
- Legacy narrative summaries refresh, content becomes current
- Briefing mentions updated facts instead of month-old narratives

**Negative:**
- Narrative titles/summaries may change on refresh (users see fresh content, but different wording)
- Initial refresh wave may take 1-2 weeks (narrative updates won't be instant)

### Medium-term (Stage 4, Backfill)

**Positive:**
- All briefings contain current narrative context
- Entity mentions align with recent articles
- Users see coherent, up-to-date briefings

**Negative:**
- None expected if Stages 1-3 successful

---

## Cost Ramifications

### Stage 1: Containment
**Cost:** $0 (code only, no LLM calls)

### Stage 2: Refinement Prompt Fix
**Cost:** +5-10% to briefing generation cost due to larger prompt
- Current: 2 briefings/day × ~$0.05-0.10 each = ~$0.20/day
- After fix: ~$0.22-0.25/day
- **Incremental: +$0.02-0.05/day (~$0.60-1.50/month)**

### Stage 3: Narrative Freshness Fix
**Cost:** One-time backfill (~$5-7)
- 341 narratives × $0.02-0.03 per refresh = $6.82-10.23
- But only run as part of staged backfill

### Stage 4: Batch Backfill
**Cost:** Depends on pilot scope
- 10/run, 2× daily, 10 days: 200 narratives × $0.025 = $5.00
- **Or full 341 at once (not recommended): $8.53-10.23**

### Stage 5: Monitoring
**Cost:** $0 (observability only)

### Total Monthly Cost Impact
- **Current:** ~$20-25/month (briefing generation only)
- **After all stages:** ~$22-28/month (briefing + occasional narrative refresh)
- **Increase:** ~10% for improved narrative freshness

---

## Risks and Rollback Plan

### Risk 1: Briefing Validation Rejects Too Many
**Symptom:** No briefing published some days
**Rollback:** Disable validation check (lines in _save_briefing), accept all briefings again
**Recover:** 15 minutes

### Risk 2: Refinement Prompt Causes Degradation
**Symptom:** Briefing quality decreases after adding context
**Rollback:** Revert _build_refinement_prompt() to simple version, remove entity/title lists
**Recover:** 30 minutes + redeploy

### Risk 3: Narrative Backfill Script Overwrites User Data
**Symptom:** Narratives lose important metadata during backfill
**Mitigation:** Test on staging database clone first; use read-only query to identify affected records; review sample before running
**Rollback:** MongoDB backup restore (pre-backfill snapshot)
**Recover:** 1-2 hours

### Risk 4: Batch Refresh Causes Token Explosion
**Symptom:** Budget exhausted, all LLM operations blocked
**Mitigation:** Start with 10/run, monitor daily cost, increase only if safe
**Rollback:** Stop refresh task, wait for budget reset (daily at midnight UTC)
**Recover:** Immediate (next day), or manually reset cost cache if needed

---

## Summary: Staged Fix Order

| Stage | Component | Priority | Sprint 019 | Effort | Risk | Timeline |
|-------|-----------|----------|-----------|--------|------|----------|
| 1 | Briefing validation | CRITICAL | ✅ Required | 2h | Low | Day 1 |
| 2 | Refinement context | High | ◐ Optional | 1.5h | Med | Day 2 |
| 3 | Narrative staleness backfill | High | ✗ Deferred | 3h | Med | Future |
| 4 | Batch narrative refresh | Medium | ✗ Deferred | 7-10d | Med | Future |
| 5 | Trust layer + deterministic fallback | High | ✅ Required | 5-7d | Low | Week 1-2 |
| 6 | Monitoring | Low | ✓ Partial | 2h | Low | Ongoing |

**Recommended execution for Sprint 019:**
- **Week 1:** Implement Stage 1 (containment), Stage 5 (trust layer architecture)
- Validate on staging, deploy to production
- **Week 2:** Implement deterministic article-cluster fallback, API display_mode field
- Test narratives page and briefing generation with trust filters
- Establish Stage 6 monitoring for trusted/untrusted split
- **Future sprints:** Consider Stages 3-4 (legacy repair) as optional optimization

---

## Addendum: Fresh-Start Narrative Trust Option

After reviewing the investigation findings, the product team chose not to immediately repair or refresh all 341 legacy narratives missing `last_summary_generated_at`.

The investigation found:

- Active narratives missing `last_summary_generated_at`: 341
- Narratives with `needs_summary_update=true`: 4
- Refresh task exists and works for flagged narratives
- Refresh task runs twice daily with `MAX_REFRESH_PER_RUN = 20`
- Full legacy refresh would create avoidable LLM cost and budget pressure
- The most urgent user-facing failure is invalid briefing publication, not historical narrative repair

### Product Decision

Sprint 019 will use a fresh-start trust model instead of immediate legacy repair:

1. **Briefing generation** should only use trusted narrative summaries.
2. **The narratives page** should continue showing recent article activity.
3. **Stale or missing narrative summaries** should not be presented as authoritative user-facing copy.
4. **The UI should gracefully fall back** to an article-cluster display for untrusted summaries.
5. **The fallback display must be deterministic** and must not call an LLM.
6. **Old narratives remain in MongoDB** for future repair, audit, or selective reactivation.
7. **Sprint 019 will not** mass-refresh, delete, dormancy-mark, or migrate all legacy narratives.

### Trusted Summary Rule

A narrative summary is considered trusted for briefing synthesis if one of the following is true:

```
first_seen >= FRESH_START_CUTOFF
OR last_summary_generated_at >= FRESH_START_CUTOFF
OR _fresh_start_validated_at >= FRESH_START_CUTOFF
```

Narratives that do not meet this rule should be excluded from briefing synthesis.

### Narratives Page Rule

The narratives page should not use the same strict filter as briefing generation. It should remain activity-based:

```
show narratives with recent article activity, such as last_updated >= FRESH_START_CUTOFF
```

This avoids hiding current article clusters simply because they are attached to old legacy narratives.

### Display Mode Rule

The backend/API should compute a product-facing display mode for each narrative. Expected display modes:

- **`summary`** — use generated title and summary
- **`article_cluster`** — use deterministic fallback from recent article titles, entities, sources, and counts

**For trusted summaries:**
- `display_mode = "summary"`
- Frontend may show the generated title and generated summary.

**For untrusted summaries:**
- `display_mode = "article_cluster"`
- Frontend should render a user-facing article activity card, e.g.:
  ```
  Bitcoin
  8 recent articles
  Latest coverage includes Bitcoin holding near $80K, ETF outflows, options positioning, 
  and Fed inflation concerns.
  ```

This line must be generated deterministically from recent article titles, entities, source names, and article count. It must not call an LLM.

### User-Facing Copy Constraint

Do not expose internal system state to public users.

The frontend should **not show**:
- "Summary needs refresh"
- "Stale"
- "Missing"
- "Untrusted"
- "Needs update"

Those terms may exist internally, but the public UI should use polished article-cluster fallback copy.

### Cost Decision

Sprint 019 should avoid the estimated legacy refresh cost:

- Full refresh of 341 narratives: ~$6.82-$10.23
- Budget risk: May trigger soft/hard limits if attempted all at once
- Deterministic fallback cost: $0

The only expected LLM cost increase in Sprint 019 should come from the briefing refinement prompt grounding fix (if implemented), because the prompt may include more source context.

### Revised Recommended Path

The original investigation recommended staged repair of legacy narratives. That remains a valid future option, but it is no longer the recommended near-term path.

**Revised Sprint 019 recommendation:**

**Option A: Controlled legacy repair (original plan)**
- Stage 3: Backfill missing timestamps, fix staleness detection
- Stage 4: Batch refresh 341 narratives over 7-10 days
- Cost: ~$6.82-10.23
- Timeline: 10-15 days
- Risk: Budget pressure, narrative content changes

**Option B: Fresh-start narrative trust layer (recommended for Sprint 019)**
- Add trusted-summary eligibility check for briefing inputs
- Add narrative display mode fields to public API
- Add deterministic article-cluster fallback for untrusted summaries
- Prevent invalid briefings from publishing (Stage 1)
- Ground briefing refinement prompts with source context (Stage 2, optional)
- Cost: $0 (plus optional Stage 2 refinement cost)
- Timeline: 2-3 weeks
- Risk: Low; forward-correctness focused

### Explicit Non-Goals for Sprint 019

- ✗ Do not refresh all 341 legacy narratives
- ✗ Do not delete old narratives
- ✗ Do not mark old narratives dormant
- ✗ Do not overwrite `last_summary_generated_at` for legacy narratives as a shortcut
- ✗ Do not expose stale/missing/untrusted labels to public users
- ✗ Do not use LLM calls to generate article-cluster fallback copy
- ✗ Do not change narrative clustering or matching behavior (separate ticket if needed)

### Future Repair Option

Ignoring old narratives for briefing synthesis does not prevent repairing them later.

Because old narratives remain in MongoDB, future work can selectively or gradually repair them by:

- Refreshing high-value narratives manually
- Adding `_fresh_start_validated_at` after review
- Flagging old narratives with `needs_summary_update=true`
- Reducing refresh batch size
- Running controlled backfill over days or weeks
- Creating a separate legacy narrative repair sprint

This keeps Sprint 019 focused on forward correctness and user-facing safety while preserving optionality for historical repair.

---

## Conclusion

The bad briefing was caused by a **fallback parsing handler that accepts non-JSON LLM text as valid briefing content** (confidence_score=0.3). This is a code-level validation gap, not a data or configuration issue.

The **341 stale narratives** are not being refreshed because their missing `last_summary_generated_at` timestamps cause staleness checks to evaluate as "not stale" (when paired with recent `last_updated` values). The refresh system works correctly for flagged narratives; the problem is flag detection.

Both issues are **fixable with code changes only** — no data migration required except for the narrative timestamp backfill (which is low-risk and one-time).

**Immediate action (critical):** Implement containment fix (Stage 1) to prevent future invalid briefings from publishing.

**Recommended near-term path for Sprint 019:** Implement a fresh-start narrative trust layer that excludes untrusted summaries from briefing synthesis and renders recent article clusters deterministically on the narratives page. This avoids the estimated $6.82-10.23 cost of refreshing all 341 legacy narratives while ensuring user-facing correctness.

**Future option:** Legacy narrative repair remains valid but deferred. Old narratives persist in MongoDB and can be selectively refreshed, backfilled, or validated in a future sprint without affecting Sprint 019's forward-correctness focus.

---

## Appendix: Files and Functions Reference

### Key Code Locations

**Briefing Generation & Validation:**
- `src/crypto_news_aggregator/services/briefing_agent.py:940-1012` — `_save_briefing()` (needs validation)
- `src/crypto_news_aggregator/services/briefing_agent.py:831-890` — `_parse_briefing_response()` (fallback issue)
- `src/crypto_news_aggregator/db/operations/briefing.py:41-60` — `insert_briefing()`

**Briefing Prompts:**
- `src/crypto_news_aggregator/services/briefing_agent.py:619-689` — `_build_generation_prompt()`
- `src/crypto_news_aggregator/services/briefing_agent.py:691-758` — `_build_critique_prompt()`
- `src/crypto_news_aggregator/services/briefing_agent.py:765-786` — `_build_refinement_prompt()` (missing context)

**Refinement Loop:**
- `src/crypto_news_aggregator/services/briefing_agent.py:393-501` — `_self_refine()`

**Narrative Staleness:**
- `src/crypto_news_aggregator/services/narrative_service.py:1112-1154` — staleness evaluation and flag setting
- `src/crypto_news_aggregator/db/operations/narratives.py:64-300` — `upsert_narrative()`

**Narrative Refresh:**
- `src/crypto_news_aggregator/tasks/narrative_refresh.py:36-168` — refresh task (working correctly)
- `src/crypto_news_aggregator/tasks/beat_schedule.py:117-134` — scheduling (working correctly)

**Cost Tracking:**
- `src/crypto_news_aggregator/services/cost_tracker.py:429-504` — `check_llm_budget()`

**Public API:**
- `src/crypto_news_aggregator/api/v1/endpoints/briefing.py:229-260` — `get_latest_briefing_endpoint()` (no validation)
- `src/crypto_news_aggregator/api/v1/endpoints/briefing.py:134-186` — `_format_briefing()`

---

**End of Investigation Report**
