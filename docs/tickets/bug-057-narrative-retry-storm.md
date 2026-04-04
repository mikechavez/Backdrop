---
id: BUG-057
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-02
updated: 2026-04-03
depends_on: BUG-056
---

# Narrative Enrichment Retry Storm Burns Budget on Deterministic Validation Failures

## Problem

`discover_narrative_from_article()` in `narrative_themes.py` retries up to 4 times when LLM output fails validation. But validation failures (hallucinated entities, missing salience scores, empty actors) are deterministic -- retrying the same prompt on the same article produces the same structurally non-compliant output. Each retry is a billed Haiku API call. When `backfill_narratives_for_recent_articles()` processes a backlog of 100+ articles, the retry multiplier turns a $0.10 operation into a $0.40+ operation per article, and the total backlog burn exceeds the entire daily budget in under an hour.

This is the root cause of why BUG-054's pipeline restart burned through all credits. BUG-056 (spend cap) stops the bleeding; this ticket fixes the disease.

## Expected Behavior

- Validation failures on LLM output are not retried (zero retries for deterministic failures)
- Articles that fail validation get a degraded stub result so the pipeline keeps moving
- A per-article LLM call cap prevents any single article from generating more than 2 API calls
- Transient errors (429 rate limits, 529 overload, timeouts) are still retried with backoff
- Recoverable validation issues (missing salience, empty actors) are auto-fixed, not rejected
- Downstream consumers filter or downweight degraded results

## Actual Behavior

- `discover_narrative_from_article()` (narrative_themes.py:597) has `max_retries=4`
- When `validate_narrative_json()` (line 798) returns `is_valid=False`, the function continues the retry loop (line 833-836), making another full LLM call
- When `validate_entity_in_text()` (line 806) returns `False` (hallucinated entity), the function continues the retry loop (line 817-820), making another full LLM call
- Each retry calls `llm_client._get_completion(prompt)` (line 784) with the identical prompt
- Sentry errors observed:
  - "actors must be non-empty list" (validate_narrative_json line 94)
  - "nucleus_entity 'crypto regulatory framework' missing salience score" (line 135)
  - "entity validation failed" / "hallucination detected" (line 812-813)
  - "Max retries exhausted for article {id}" (lines 822, 838)
- All 4 retries produce the same failure because the LLM gives structurally similar output for the same input

## Steps to Reproduce

1. Pipeline processes article where Haiku's output fails validation (e.g., produces generic "crypto industry" as nucleus_entity which isn't in the article text)
2. `discover_narrative_from_article()` retries 4 times, each time calling `_get_completion()`
3. All 4 attempts fail validation identically
4. Multiply by 100+ articles in backlog = 400+ wasted API calls

## Environment

- Environment: production (Railway)
- User impact: high (budget burned, pipeline stalled)

## Screenshots/Logs

Sentry 2026-04-02 6:29 PM - 8:29 PM (before credits ran out):
```
Max retries exhausted for article 69cebfdcaa731a71682e7db7, entity validation failed
validation failed: actors must be non-empty list
nucleus_entity 'crypto regulatory framework' missing salience score
nucleus_entity 'regulatory agencies' missing salience score
The LLM hallucinated an entity ('crypto industry') not present in the text
```

---

## Validation Rule Tiering

Before implementing, classify each validation rule by how it should handle failure:

### Tier 1: Must Keep (hallucination / corruption guard)

These are non-negotiable. If they fail, degrade immediately:

- `validate_entity_in_text()` -- hallucination detection (nucleus_entity not in article text)
- Basic JSON structure validity -- unparseable or wrong types

### Tier 2: Auto-Fix (model intent is clear, output is incomplete)

The model produced something usable but structurally incomplete. Repair, don't reject:

- **Nucleus missing salience score** (line 133-135): If nucleus_entity is in actors but not in actor_salience, assign salience 5
- **Minor schema inconsistencies**: Missing optional fields get defaults

### Tier 3: Should Not Block (overly strict for what Haiku reliably produces)

These rules reject output that is still usable. Backfill instead of failing:

- **Empty actors list** (line 93-94): If actors is empty but nucleus_entity exists, set `actors = [nucleus_entity]`
- Any rule where the fix is deterministic and the model clearly attempted the right structure

This tiering directly reduces the degraded rate without additional LLM calls.

---

## Implementation Plan

### Overview

Three changes in one file (`narrative_themes.py`), plus validation auto-fixes. Estimated time: 1-1.5 hours.

### Change 1: Zero Retries on Validation Failures

**File:** `src/crypto_news_aggregator/services/narrative_themes.py`

**Modify `discover_narrative_from_article()`** (line 597). Replace the retry-on-validation-failure logic with immediate fallback.

Current code (lines 797-839):
```python
                # VALIDATE JSON structure before returning
                is_valid, error = validate_narrative_json(narrative_data)

                if is_valid:
                    # ...validation passed path...
                    nucleus_entity = narrative_data.get('nucleus_entity', '')
                    if not validate_entity_in_text(...):
                        # If this is not the last retry, continue to retry
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying entity validation...")
                            await asyncio.sleep(1)
                            continue
                        else:
                            logger.error(f"Max retries exhausted...")
                            return None
                else:
                    # If this is not the last retry, continue to retry
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying with stricter prompt...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error(f"Max retries exhausted...")
                        return None
```

**Replace with:**

```python
                # VALIDATE JSON structure before returning
                is_valid, error = validate_narrative_json(narrative_data)

                if is_valid:
                    logger.debug(f"Validation passed for article {article_id}")

                    # Validate nucleus_entity appears in article text
                    nucleus_entity = narrative_data.get('nucleus_entity', '')
                    if not validate_entity_in_text(
                        nucleus_entity=nucleus_entity,
                        article_title=title,
                        article_text=summary
                    ):
                        logger.warning(
                            f"Entity validation failed for article {article_id}: "
                            f"'{nucleus_entity}' not found in text (hallucination). "
                            f"Returning degraded result (no retry)."
                        )
                        # FAIL CHEAP: Return degraded result instead of retrying
                        return _build_degraded_narrative(
                            article_id, title, summary, content_hash,
                            reason=f"hallucinated nucleus_entity: {nucleus_entity}"
                        )

                    # Add content hash to narrative data for caching
                    narrative_data['narrative_hash'] = content_hash
                    return narrative_data

                else:
                    # Validation failed (missing fields, bad types, etc.)
                    # Do NOT retry -- this is a deterministic failure
                    logger.warning(
                        f"Validation failed for article {article_id}: {error}. "
                        f"Returning degraded result (no retry)."
                    )
                    return _build_degraded_narrative(
                        article_id, title, summary, content_hash,
                        reason=f"validation: {error}"
                    )
```

**Also update the function signature** (line 597-599). Remove `max_retries` parameter since we no longer retry on validation failures. Keep retries only for transient errors:

```python
async def discover_narrative_from_article(
    article: Dict,
    max_retries: int = 2  # Reduced: only retries transient errors (429, 529, timeout)
) -> Optional[Dict[str, Any]]:
```

**Update the transient error handling** (lines 852-893). Keep the existing rate limit and overload retry logic as-is -- those are the only legitimate retry cases.

### Change 2: Add Fail-Cheap Fallback Function

**File:** `src/crypto_news_aggregator/services/narrative_themes.py`

**Add this function** before `discover_narrative_from_article()` (around line 595):

```python
def _build_degraded_narrative(
    article_id: str,
    title: str,
    summary: str,
    content_hash: str,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Build a minimal degraded narrative result when LLM output fails validation.

    This keeps the pipeline moving without additional LLM calls.
    Degraded narratives can be identified by status="degraded" and
    optionally backfilled later with a prompt/schema fix.

    Args:
        article_id: Article ID for logging
        title: Article title (used as fallback nucleus entity)
        summary: Article summary
        content_hash: Content hash for caching
        reason: Why the result is degraded

    Returns:
        Dict with minimal narrative structure
    """
    # Extract a simple nucleus entity from the title
    # Use the first capitalized multi-word phrase or first 3 words
    fallback_nucleus = title.split(":")[0].strip()[:50] if title else "Unknown"

    logger.info(
        f"Building degraded narrative for article {article_id[:8]}... "
        f"(reason: {reason})"
    )

    return {
        "actors": [fallback_nucleus],
        "actor_salience": {fallback_nucleus: 3},
        "nucleus_entity": fallback_nucleus,
        "narrative_focus": "unclassified",
        "actions": [],
        "tensions": [],
        "implications": "",
        "narrative_summary": summary[:200] if summary else title,
        "narrative_hash": content_hash,
        "status": "degraded",
        "degraded_reason": reason,
    }
```

### Change 3: Per-Article LLM Call Cap

**File:** `src/crypto_news_aggregator/services/narrative_themes.py`

**Add a call counter** inside `discover_narrative_from_article()` to cap total LLM calls per article at 2 (1 primary + 1 transient retry). This is belt-and-suspenders on top of the zero-retry-on-validation change.

At the top of the retry loop (line 649), add:

```python
    llm_calls_made = 0
    MAX_LLM_CALLS_PER_ARTICLE = 2

    for attempt in range(max_retries):
```

Before the `llm_client._get_completion(prompt)` call (line 784), add:

```python
            # Per-article LLM call cap
            if llm_calls_made >= MAX_LLM_CALLS_PER_ARTICLE:
                logger.warning(
                    f"Per-article LLM call cap ({MAX_LLM_CALLS_PER_ARTICLE}) reached "
                    f"for article {article_id[:8]}... Returning degraded result."
                )
                return _build_degraded_narrative(
                    article_id, title, summary, content_hash,
                    reason=f"per-article call cap ({MAX_LLM_CALLS_PER_ARTICLE})"
                )

            llm_calls_made += 1
```

### Change 4: Validation Auto-Fixes (Tier 2 + Tier 3)

**File:** `src/crypto_news_aggregator/services/narrative_themes.py`

These changes reduce the degraded rate on day one by repairing recoverable output instead of rejecting it.

**4a. Auto-fix nucleus salience (Tier 2)** -- Replace lines 133-135 in `validate_narrative_json()`:

```python
    # Ensure nucleus has salience score
    if data['nucleus_entity'] not in data.get('actor_salience', {}):
        return False, f"nucleus_entity '{data['nucleus_entity']}' missing salience score"
```

With:
```python
    # Auto-fix: Ensure nucleus has salience score (default to 5 if missing)
    if data['nucleus_entity'] not in data.get('actor_salience', {}):
        logger.debug(
            f"Auto-fixing: adding salience 5 for nucleus_entity '{data['nucleus_entity']}'"
        )
        data['actor_salience'][data['nucleus_entity']] = 5
```

**4b. Auto-fix empty actors (Tier 3)** -- Replace lines 93-94 in `validate_narrative_json()`:

```python
    if not isinstance(data.get('actors'), list) or len(data['actors']) == 0:
        return False, "actors must be non-empty list"
```

With:
```python
    if not isinstance(data.get('actors'), list):
        return False, "actors must be a list"
    if len(data['actors']) == 0:
        # Auto-fix: backfill actors from nucleus_entity if available
        nucleus = data.get('nucleus_entity', '')
        if nucleus:
            logger.debug(f"Auto-fixing: backfilling empty actors with nucleus_entity '{nucleus}'")
            data['actors'] = [nucleus]
        else:
            return False, "actors empty and no nucleus_entity to backfill"
```

### Change 5: Downstream Degraded Filtering

**File:** Grep all consumers of narrative data and add filtering.

Before shipping, verify every downstream consumer of narrative results handles `status="degraded"`. At minimum:

- **Narrative clustering/grouping**: Exclude degraded narratives from cluster formation
- **Briefing generation**: Exclude or downweight degraded narratives in briefing input
- **Any ranking/scoring logic**: Filter `status != "degraded"` or apply heavy downweight

The specific files depend on grep results, but the pattern is:

```python
# Wherever narratives are queried for downstream use:
narratives = collection.find({"status": {"$ne": "degraded"}})
# OR if degraded should be included but flagged:
narratives = collection.find({})
for n in narratives:
    if n.get("status") == "degraded":
        n["weight"] = 0.1  # downweight, don't exclude
```

This prevents degraded stubs from polluting briefing quality or clustering.

### Change 6: Degraded Rate Tracking

**File:** `src/crypto_news_aggregator/services/narrative_themes.py`

Add a log line at the end of `backfill_narratives_for_recent_articles()` that reports degraded rate per batch:

```python
    total = len(results)
    degraded = sum(1 for r in results if r and r.get("status") == "degraded")
    succeeded = sum(1 for r in results if r and r.get("status") != "degraded")
    failed = sum(1 for r in results if r is None)

    logger.info(
        f"Narrative backfill complete: {total} articles, "
        f"{succeeded} succeeded, {degraded} degraded ({degraded/total*100:.0f}%), "
        f"{failed} failed"
    )
```

This is the signal that tells you whether the degraded rate is an acceptable edge case (<10%) or a systemic prompt problem (>25%) that needs the prompt audit ticket.

---

## Known Tradeoffs

Documenting explicitly so future-you doesn't re-litigate these:

1. **Some recoverable failures will not be retried.** LLM output has slight randomness -- a small % of validation failures might succeed on retry. We're accepting this loss. If degraded rate is high (>25%), the fix is prompt improvement, not retry logic. A prompt-variant retry strategy is a valid Phase 2 option but only justified by data.

2. **Degraded outputs reduce downstream data quality.** Degraded narratives have synthetic actors and "unclassified" focus. Downstream filtering (Change 5) mitigates this, but any new consumer must also respect the `status` field. This is a maintenance burden.

3. **Fallback entity extraction is heuristic.** `title.split(":")[0]` will sometimes produce useless entities ("Breaking News", "Analysis"). This is acceptable for a degraded stub -- the point is pipeline continuity, not semantic accuracy. If degraded stubs need to be useful (not just present), upgrade to capitalized-token extraction.

4. **No learning loop from degraded results yet.** Failure reasons are logged and stored in `degraded_reason`, but not systematically analyzed. The degraded rate metric (Change 6) is the first step. A dedicated prompt audit ticket is the second.

5. **Combined with BUG-056, the system may produce more output at lower quality.** BUG-057 reduces per-article cost; BUG-056 caps total spend. Together, the pipeline processes more articles within budget but some are degraded. This is the correct tradeoff for a $10/month budget: availability over perfection.

---

## Testing Plan

1. **Unit test for `_build_degraded_narrative()`:**
   - Call with sample inputs, verify output has all required keys
   - Verify `status="degraded"` and `degraded_reason` is set
   - Verify `narrative_hash` is populated (enables cache skip on re-run)

2. **Unit test for zero-retry behavior:**
   - Mock `_get_completion()` to return JSON that fails `validate_narrative_json()`
   - Call `discover_narrative_from_article()`
   - Assert `_get_completion()` was called exactly ONCE (no retries)
   - Assert return value has `status="degraded"`

3. **Unit test for entity hallucination handling:**
   - Mock `_get_completion()` to return valid JSON with nucleus_entity not in text
   - Assert `_get_completion()` was called exactly ONCE
   - Assert return value has `degraded_reason` containing "hallucinated"

4. **Unit test for per-article call cap:**
   - Mock `_get_completion()` to raise rate limit errors
   - Assert `_get_completion()` called at most `MAX_LLM_CALLS_PER_ARTICLE` times
   - Assert degraded result returned

5. **Unit test for transient retry (still works):**
   - Mock `_get_completion()` to raise 429 on first call, succeed on second
   - Assert function returns valid result (retry worked)
   - Assert `_get_completion()` called exactly 2 times

6. **Unit test for Tier 2/3 auto-fixes:**
   - Test nucleus salience auto-fix: input with nucleus not in actor_salience, verify salience added (not rejected)
   - Test empty actors backfill: input with empty actors but valid nucleus_entity, verify actors populated (not rejected)
   - Test empty actors with no nucleus: verify still fails validation

7. **Integration test:**
   - Run `backfill_narratives_for_recent_articles()` on 10 articles with mixed outcomes
   - Verify total LLM calls <= 20 (2 per article max)
   - Verify degraded articles have `status="degraded"` in MongoDB
   - Verify degraded rate log line emitted

## Acceptance Criteria

- [ ] Validation failures (bad JSON structure, hallucinated entities) are NOT retried
- [ ] Degraded fallback returned for validation failures (status="degraded")
- [ ] Per-article LLM call cap of 2
- [ ] Transient errors (429, 529) still retried with backoff
- [ ] `validate_narrative_json()` auto-fixes nucleus salience instead of failing (Tier 2)
- [ ] `validate_narrative_json()` auto-fixes empty actors from nucleus_entity (Tier 3)
- [ ] Downstream narrative consumers filter or downweight degraded results
- [ ] Degraded rate logged per backfill batch (% degraded)
- [ ] All existing tests pass
- [ ] New unit tests for zero-retry, degraded fallback, call cap, auto-fixes

## Files Changed

- `src/crypto_news_aggregator/services/narrative_themes.py`
  - Add `_build_degraded_narrative()` function (~30 lines)
  - Modify `discover_narrative_from_article()`: remove retry on validation failure, add call cap
  - Modify `validate_narrative_json()`: auto-fix nucleus salience (Tier 2), auto-fix empty actors (Tier 3)
  - Add degraded rate logging to `backfill_narratives_for_recent_articles()`
- Downstream narrative consumers (files TBD via grep)
  - Add `status != "degraded"` filter or downweight logic

---

## Follow-Up Ticket (Next Sprint)

**Prompt Audit** -- Reduce first-call failure rate. This is the highest-leverage follow-up. Use degraded rate data and `degraded_reason` clustering from this ticket to identify which prompt/schema changes would have the most impact. Targets:
- Haiku producing generic entities ("crypto industry") instead of specific named entities
- Schema complexity vs what Haiku reliably outputs
- Whether examples in the prompt would reduce hallucination rate

This is not a "nice to have" -- if degraded rate exceeds 25%, prompt improvement is the only real fix.

---

## Resolution

**Status:** Open
**Fixed:**
**Branch:**
**Commit:**

### Root Cause

The system treats LLM outputs as retryable: if the output is wrong, retry. But LLM validation failures are deterministic for a given input -- the same prompt on the same article produces structurally similar non-compliant output. Retrying is just burning money. The system had no concept of "degraded but usable" output, so every failure was either retried (expensive) or dropped (lost data). The validation layer also rejected recoverable defects (missing salience, empty actors) that could be auto-fixed without an LLM call. Combined with a post-outage article backlog from BUG-054, this created a retry storm that exhausted the monthly API budget in ~2 hours.

### Changes Made
<!-- Fill after fix -->

### Testing
<!-- Fill after fix -->