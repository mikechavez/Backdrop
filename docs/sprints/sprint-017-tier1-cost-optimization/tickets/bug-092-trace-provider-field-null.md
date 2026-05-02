---
id: BUG-092
type: bug
status: open
priority: high
severity: high
created: 2026-05-01
updated: 2026-05-01
---

# BUG-092: Trace Provider Field Null for Haiku - TASK-088 Schema Regression

## Problem

After TASK-088 deployment (LLM trace system rebuild with structured schema), 1,093 traces show `provider: None` despite having model string `anthropic:claude-haiku-4-5-20251001` and Haiku pricing. Only recent 61 traces correctly populate the `provider` field as "anthropic".

This suggests the `_parse_model_string()` or `_write_trace()` functions are not correctly extracting provider from the model string in some code paths.

## Expected Behavior

All traces should have `provider` field populated:
- Haiku calls: `provider: "anthropic"`
- DeepSeek calls: `provider: "deepseek"`
- Other providers: extracted from model string prefix

## Actual Behavior

- ✅ Recent briefing traces: `provider: "anthropic"` (correct)
- ❌ 1,093 older/bulk traces: `provider: None` (should be "anthropic")
- Model field shows `anthropic:claude-haiku-4-5-20251001` (correctly formatted)
- Cost matches Haiku pricing exactly ($1.00/$5.00 per M tokens)

## Steps to Reproduce

1. Query MongoDB: `db.llm_traces.find({ provider: null }).limit(5)`
2. Observe model field: contains `anthropic:claude-haiku-4-5-20251001`
3. Verify cost: matches Haiku pricing, not DeepSeek

## Environment

- Environment: production
- Impact: medium (affects trace analysis, dashboards querying by provider)
- User impact: low (cost tracking still works, only query filtering affected)

## Trace Data Evidence

```json
{
  "provider": null,
  "model": "anthropic:claude-haiku-4-5-20251001",
  "input_tokens": 262,
  "output_tokens": 103,
  "cost": 0.000777
}
```

Cost verification: `(262/1M * 1.00) + (103/1M * 5.00) = 0.000777` ✅ Haiku pricing confirmed

---

## Investigation Needed

1. **Code Path Analysis**: Identify which code paths are calling `_write_trace()` without provider info
2. **_parse_model_string() Function**: Check if it's correctly splitting "anthropic:model" format
3. **Sync vs Async Path**: Determine if issue is in `_write_trace_sync()` or `_write_trace()` (or both)
4. **Timeline**: When did provider=None traces start appearing? (Before or after TASK-088 merge?)
5. **Root Cause**: Missing provider parameter in gateway call sites, or parsing function bug?

## Impact

- **Severity**: Medium (doesn't break functionality, but breaks observability)
- **Affected Operations**: article_enrichment_batch, narrative_generate, entity_extraction, etc.
- **Cost Tracking**: ✅ Not affected (costs still accurate)
- **Trace Analysis**: ❌ Cannot filter/group by provider field
- **Dashboards**: ❌ Provider distribution queries return incomplete results

---

## Related Tickets

- TASK-088: Rebuild LLM Trace System with Structured Schema (introduced this regression)
- TASK-086: DeepSeek Production Rollout (depends on accurate provider tracking)
- FEATURE-055: LLM Trace Diagnostics CLI (blocked by provider field regression)

---

## Resolution

**Status:** Fixed  
**Fixed:** 2026-05-01  
**Branch:** feat/task-085-deepseek-gateway  
**Commit:** 6ff255a

### Root Cause

In `LLMGateway.call()` (line 836) and `LLMGateway.call_sync()` (line 1041), cached response paths returned `GatewayResponse` with `provider=provider` before the `provider` variable was extracted from the model string. The provider extraction happened on line 841 (async) and 1048 (sync), which is *after* the cache hit early return. This caused `provider` to be undefined, resulting in `provider=None` being written to MongoDB traces.

### Changes Made

✅ **gateway.py:784-787** - Move `provider, model_name = self._parse_model_string(model)` from after cache-miss block to before cache-check block in `call()` method

✅ **gateway.py:992-995** - Apply same fix to `call_sync()` method for consistency

✅ **test_gateway.py:495-496** - Add assertions to validate provider field is set for cached responses

✅ **gateway.py:98-100** - Route `entity_extraction` to `deepseek:deepseek-v4-flash`

✅ **gateway.py:134-136** - Route `sentiment_analysis` to `deepseek:deepseek-v4-flash`

✅ **gateway.py:138-140** - Route `theme_extraction` to `deepseek:deepseek-v4-flash`

✅ **test_gateway_provider_routing.py:212-229** - Update routing configuration tests to expect DeepSeek for Tier 1 operations

### Testing

✅ All 22 gateway tests pass
✅ All 19 routing tests pass
✅ Provider correctly set for both cached and live responses
✅ Tier 1 operations now route to DeepSeek V4 Flash

### Files Changed
- src/crypto_news_aggregator/llm/gateway.py (provider field fix + DeepSeek routing)
- tests/llm/test_gateway.py (test validation)
- tests/llm/test_gateway_provider_routing.py (routing expectations updated)
