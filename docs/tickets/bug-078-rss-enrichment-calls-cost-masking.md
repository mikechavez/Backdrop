---
id: BUG-078
type: bug
status: complete
priority: high
severity: medium
created: 2026-04-14
updated: 2026-04-15
---

# RSS enrichment calls have no operation name, masking $0.14/day in traces

## Problem

The `_tracked` async methods in `AnthropicProvider` (`score_relevance_tracked`, `analyze_sentiment_tracked`, `extract_themes_tracked`) and `enrich_articles_batch` all call `self._get_completion_with_usage(prompt)` without passing the `operation` argument. The operation name is correctly received as a parameter and used for budget checks and circuit breakers — but it is dropped at the `_get_completion_with_usage` call site. `_get_completion_with_usage` calls `gateway.call_sync` with `operation=""`, which falls back to `"provider_fallback"`.

The four sync methods (`analyze_sentiment`, `extract_themes`, `score_relevance`, `generate_insight`) already pass correct operation names and are not part of this bug.

**Confirmed in production:** 159 `provider_fallback` calls/day, $0.149/day, all Haiku, all from RSS enrichment.

## Expected Behavior

Every call through `_get_completion_with_usage` carries the operation name passed into the calling method. Zero `provider_fallback` entries in `llm_traces` from enrichment operations after one enrichment cycle post-deploy.

## Actual Behavior

All calls through `score_relevance_tracked`, `analyze_sentiment_tracked`, `extract_themes_tracked`, and `enrich_articles_batch` write to `llm_traces` as `provider_fallback` regardless of what operation name was passed in.

---

## Fix History

### First fix — INCORRECT (commit 94dc5fb, 2026-04-14 18:45 UTC)
Patched the four sync methods (`analyze_sentiment`, `extract_themes`, `generate_insight`, `score_relevance`) to pass operation names to `_get_completion()`. These methods were already correct. Fix had zero effect in production — `provider_fallback` volume unchanged after deploy.

### Second fix — CORRECT (commit 6448289, 2026-04-14 19:15 UTC)
Identified true broken call sites during Session 30 post-deploy validation. Root cause: async `_tracked` methods and `enrich_articles_batch` were dropping the `operation` parameter at the `_get_completion_with_usage()` call site.

---

## Code Location

**File:** `src/crypto_news_aggregator/llm/anthropic.py`

Four call sites, all the same pattern — operation is in scope but not passed through:

**Line 550 — `enrich_articles_batch`:**
```python
# operation name for this method: "article_enrichment_batch" (used on line 509 for budget check)
response_text, usage = self._get_completion_with_usage(prompt)
# fix:
response_text, usage = self._get_completion_with_usage(prompt, operation="article_enrichment_batch")
```

**Line 633 — `score_relevance_tracked`:**
```python
# operation is a parameter defaulting to "relevance_scoring"
response_text, usage = self._get_completion_with_usage(prompt)
# fix:
response_text, usage = self._get_completion_with_usage(prompt, operation=operation)
```

**Line 695 — `analyze_sentiment_tracked`:**
```python
# operation is a parameter defaulting to "sentiment_analysis"
response_text, usage = self._get_completion_with_usage(prompt)
# fix:
response_text, usage = self._get_completion_with_usage(prompt, operation=operation)
```

**Line 758 — `extract_themes_tracked`:**
```python
# operation is a parameter defaulting to "theme_extraction"
response_text, usage = self._get_completion_with_usage(prompt)
# fix:
response_text, usage = self._get_completion_with_usage(prompt, operation=operation)
```

---

## Resolution

**Status:** ✅ COMPLETE + VALIDATED
**Fixed:** 2026-04-14 19:15 UTC
**Validated:** 2026-04-15 (Session 30)
**Commit:** `6448289`

### Files Changed

- `src/crypto_news_aggregator/llm/anthropic.py` — lines 550, 633, 695, 758 only

### Production Validation

- Last `provider_fallback` trace after deploy: `2026-04-15T01:40:22 UTC` — 15 minutes **before** deploy at 01:55 UTC ✅
- `article_enrichment_batch` appeared in operation breakdown post-deploy ✅
- No new `provider_fallback` entries generated after deploy ✅

```javascript
// Confirmed post-deploy operation breakdown (partial day, 2026-04-15):
// { _id: 'article_enrichment_batch', cost: 0.006821, calls: 8 }  ← new, correctly labeled
// provider_fallback calls all pre-date the 01:55 UTC deploy
```

### Follow-up

`article_enrichment_batch` is not yet in `_OPERATION_MODEL_ROUTING` in `gateway.py`. Will log a routing warning on each call. No cost impact (Haiku is used regardless). Add in next routing table pass alongside BUG-077 cleanup.