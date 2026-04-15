---
id: BUG-078
type: bug
status: complete
priority: high
severity: medium
created: 2026-04-14
updated: 2026-04-14
---

# RSS enrichment calls have no operation name, masking $0.14/day in traces

## Problem

The `_tracked` async methods in `AnthropicProvider` (`score_relevance_tracked`, `analyze_sentiment_tracked`, `extract_themes_tracked`) and the `enrich_articles_batch` method all call `self._get_completion_with_usage(prompt)` without passing the `operation` argument. The operation name is correctly received as a parameter and used for budget checks and circuit breakers — but it is dropped at the `_get_completion_with_usage` call site. `_get_completion_with_usage` then calls `gateway.call_sync` with `operation=""`, which falls back to `"provider_fallback"`.

The four sync methods (`analyze_sentiment`, `extract_themes`, `score_relevance`, `generate_insight`) already pass correct operation names and are not part of this bug. The original BUG-078 fix (commit 94dc5fb) patched those sync methods, which were already correct, and missed the actual broken call sites.

**Confirmed in production:** 159 `provider_fallback` calls/day, $0.149/day, all Haiku, all from RSS enrichment.

## Expected Behavior

Every call through `_get_completion_with_usage` carries the operation name that was passed into the calling method. Zero `provider_fallback` entries in `llm_traces` from enrichment operations after one enrichment cycle post-deploy.

## Actual Behavior

All calls through `score_relevance_tracked`, `analyze_sentiment_tracked`, `extract_themes_tracked`, and `enrich_articles_batch` write to `llm_traces` as `provider_fallback` regardless of what operation name was passed in.

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

### Changes Required

**One file, four one-line changes in `src/crypto_news_aggregator/llm/anthropic.py`:**

1. Line 550: `self._get_completion_with_usage(prompt)` → `self._get_completion_with_usage(prompt, operation="article_enrichment_batch")`
2. Line 633: `self._get_completion_with_usage(prompt)` → `self._get_completion_with_usage(prompt, operation=operation)`
3. Line 695: `self._get_completion_with_usage(prompt)` → `self._get_completion_with_usage(prompt, operation=operation)`
4. Line 758: `self._get_completion_with_usage(prompt)` → `self._get_completion_with_usage(prompt, operation=operation)`

No other files need to change. Routing table entries for these operation names were already added by BUG-077.

### Testing

After deploy, wait one enrichment cycle (~1 hour) then verify:

```javascript
// Should return 0 calls from enrichment
db.llm_traces.find({
  operation: "provider_fallback",
  timestamp: { $gte: new Date(Date.now() - 3600000) }
}).count()

// Should show calls under correct operation names
db.llm_traces.aggregate([
  { $match: {
    operation: { $in: ["sentiment_analysis", "theme_extraction", "relevance_scoring", "article_enrichment_batch"] },
    timestamp: { $gte: new Date(Date.now() - 3600000) }
  }},
  { $group: { _id: "$operation", count: { $sum: 1 }, cost: { $sum: "$cost" } }}
])
```

### Files to Change

- `src/crypto_news_aggregator/llm/anthropic.py` — lines 550, 633, 695, 758 only