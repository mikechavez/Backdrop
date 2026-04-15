---
id: BUG-078
type: bug
status: backlog
priority: high
severity: medium
created: 2026-04-14
updated: 2026-04-14
---

# RSS enrichment calls have no operation name, masking $0.26/day in traces

## Problem

`AnthropicProvider`'s four sync methods (`analyze_sentiment`, `extract_themes`, `score_relevance`, `generate_insight`) call `self._get_completion(prompt)` without passing an `operation` argument. `_get_completion` defaults to `"provider_fallback"` when `operation` is empty or omitted. These calls are recorded in `llm_traces` as `provider_fallback`.

Separately, the `_tracked` async variants of the same methods write to `api_costs` manually using meaningful names (`article_enrichment_batch`). The same underlying call now has two records in two collections with two different operation names that cannot be correlated.

`rss_fetcher.py` calls these sync methods hourly to enrich incoming articles. Volume is approximately 261 calls/day, costing approximately $0.26/day. This spend is effectively invisible in any per-operation cost breakdown.

`twitter_service.py` also calls the unlabeled sync methods (`score_relevance`, `analyze_sentiment`) but Twitter ingestion is not currently active, so it is not a live cost concern. The fix should cover it anyway.

## Expected Behavior

Every call to `_get_completion` carries a meaningful operation name. All four sync methods pass their respective operation names explicitly. `llm_traces` and `api_costs` entries for the same call share the same operation name and can be correlated. No entries in `llm_traces` use `provider_fallback` as an operation name for enrichment calls.

## Actual Behavior

Approximately 261 `provider_fallback` entries appear in `llm_traces` per day from the RSS enrichment path. Cost attribution in any operation-level breakdown is incorrect. Budget enforcement cannot distinguish these calls from other unlabeled calls.

## Steps to Reproduce

1. Query `llm_traces` for `provider_fallback` entries over the past 24 hours:
   ```javascript
   db.llm_traces.aggregate([
     { $match: {
       operation: "provider_fallback",
       timestamp: { $gte: new Date(Date.now() - 86400000) }
     }},
     { $group: { _id: null, count: { $sum: 1 }, cost: { $sum: "$cost" } }}
   ])
   // Returns ~261 calls, ~$0.26
   ```
2. Note that no matching entries exist in `api_costs` under `provider_fallback` — those writes used `article_enrichment_batch` instead.

## Environment

- Environment: production (Railway)
- Services affected: Celery Worker (hourly enrichment via rss_fetcher.py), AnthropicProvider sync methods
- User impact: medium — cost attribution is wrong, makes it impossible to correctly analyze per-operation spend

---

## Code Location

**The four sync methods in anthropic.py — all call `_get_completion` without `operation`:**

```python
# src/crypto_news_aggregator/llm/anthropic.py

@track_usage
def analyze_sentiment(self, text: str) -> float:   # line 117
    prompt = f"Analyze the sentiment of this crypto text..."
    response = self._get_completion(prompt)          # no operation= passed
    ...

@track_usage
def extract_themes(self, texts: List[str]) -> List[str]:  # line 135
    prompt = f"Extract the key crypto themes..."
    response = self._get_completion(prompt)               # no operation= passed
    ...

@track_usage
def generate_insight(self, data: Dict[str, Any]) -> str:  # line 148
    ...
    return self._get_completion(prompt)                   # no operation= passed

@track_usage
def score_relevance(self, text: str) -> float:  # line 155
    ...
    response = self._get_completion(prompt)     # no operation= passed
```

**`_get_completion` fallback behavior:**

```python
def _get_completion(self, prompt: str, operation: str = "") -> str:  # line 33
    ...
    response = gateway.call_sync(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        operation=operation if operation else "provider_fallback",  # line 66
        max_tokens=2048,
    )
```

---

## Resolution

**Status:** ✅ COMPLETE
**Fixed:** 2026-04-14 18:45:00 UTC
**Branch:** `fix/bug-078-rss-enrichment-operation-names`
**Commit:** `94dc5fb`

### Root Cause

The four sync methods were written before the operation name convention was established. `_get_completion`'s default of `"provider_fallback"` was meant as a fallback for truly unknown callers, not as the permanent label for 261 calls/day of enrichment work.

### Changes Required

**Step 1: Pass explicit operation names from the four sync methods in `anthropic.py`:**

```python
def analyze_sentiment(self, text: str) -> float:
    response = self._get_completion(prompt, operation="sentiment_analysis")

def extract_themes(self, texts: List[str]) -> List[str]:
    response = self._get_completion(prompt, operation="theme_extraction")

def generate_insight(self, data: Dict[str, Any]) -> str:
    return self._get_completion(prompt, operation="insight_generation")

def score_relevance(self, text: str) -> float:
    response = self._get_completion(prompt, operation="relevance_scoring")
```

**Step 2: Add all four operation names to `_OPERATION_MODEL_ROUTING` in `gateway.py`:**

```python
_OPERATION_MODEL_ROUTING = {
    # existing entries ...
    "sentiment_analysis": "claude-haiku-4-5-20251001",
    "theme_extraction": "claude-haiku-4-5-20251001",
    "relevance_scoring": "claude-haiku-4-5-20251001",
    "insight_generation": "claude-haiku-4-5-20251001",
}
```

Note: this overlaps with BUG-077 which also adds these entries. If BUG-077 lands first, skip the routing dict changes here.

**Step 3 (optional but recommended): Add a warning in `_get_completion` when `operation` is empty:**

```python
def _get_completion(self, prompt: str, operation: str = "") -> str:
    if not operation:
        logger.warning(
            "_get_completion called without operation name. "
            "Traces will be recorded as 'provider_fallback'. "
            "Pass an explicit operation name to all callers."
        )
    ...
```

This makes future callers that omit `operation` immediately visible in logs without breaking anything.

### Testing

1. After deploy, run one hourly enrichment cycle and check `llm_traces`:
   ```javascript
   db.llm_traces.find({
     operation: "provider_fallback",
     timestamp: { $gte: new Date(Date.now() - 3600000) }
   }).count()
   // Expected: 0 from enrichment operations
   ```
2. Verify the four operation names now appear with expected volumes:
   ```javascript
   db.llm_traces.aggregate([
     { $match: {
       operation: { $in: ["sentiment_analysis", "theme_extraction", "relevance_scoring", "insight_generation"] },
       timestamp: { $gte: new Date(Date.now() - 86400000) }
     }},
     { $group: { _id: "$operation", count: { $sum: 1 }, cost: { $sum: "$cost" } }}
   ])
   ```

### Files to Change

- `src/crypto_news_aggregator/llm/anthropic.py` — four sync methods (lines 117, 135, 148, 155)
- `src/crypto_news_aggregator/llm/gateway.py` — `_OPERATION_MODEL_ROUTING` dict (if BUG-077 not yet merged)