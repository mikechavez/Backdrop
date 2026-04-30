---
id: TASK-085-IMPL
type: implementation
status: complete
date: 2026-04-30
---

# TASK-085: DeepSeek Provider-Aware Gateway Implementation

## Summary

Implemented provider-aware model routing in `LLMGateway` to support DeepSeek integration alongside Anthropic. The gateway now:

1. **Parses provider-aware model strings** (`anthropic:model` or `deepseek:model`)
2. **Routes to the correct provider API** (Anthropic or DeepSeek)
3. **Handles provider-specific requests** (headers, payloads, responses)
4. **Tracks costs correctly** for each provider
5. **Maintains centralized rollback** (change one line in routing to switch providers)

No standalone `DeepSeekProvider` class. All calls go through `LLMGateway` for consistency, tracing, budget enforcement, and cache support.

---

## Changes

### 1. Gateway Provider-Aware Routing (`src/crypto_news_aggregator/llm/gateway.py`)

#### New Methods

**`_parse_model_string(model_str: str) -> tuple[str, str]`**
- Parses `"anthropic:model-name"` or `"deepseek:model-name"` format
- Defaults legacy `"model-name"` strings to `"anthropic"`
- Returns `(provider, model_name)`

**`_get_provider_url(provider: str) -> str`**
- Returns provider-specific API endpoint
- Anthropic: Respects Helicone proxy config
- DeepSeek: `https://api.deepseek.com/chat/completions`

**`_build_provider_headers(provider: str, model_name: str) -> dict`**
- Anthropic: `x-api-key`, `anthropic-version: 2023-06-01`
- DeepSeek: `Authorization: Bearer {DEEPSEEK_API_KEY}`

**`_build_provider_payload(messages, provider, model_name, max_tokens, temp, system) -> dict`**
- Anthropic: Includes `system` prompt, no `stream` field
- DeepSeek: OpenAI-compatible format, `stream: false`, `thinking: {type: disabled}`

**`_parse_provider_response(data: dict, provider: str) -> tuple[str, int, int]`**
- Anthropic: Extract from `data["content"][0]["text"]`, `data["usage"]["input_tokens"]`
- DeepSeek: Extract from `data["choices"][0]["message"]["content"]`, `data["usage"]["prompt_tokens"]`

#### Updated Methods

- `call()` and `call_sync()`: Parse model string, call provider-specific helpers
- Backward compatibility: Legacy methods delegate to provider-aware versions

### 2. Configuration (`src/crypto_news_aggregator/core/config.py`)

Added:
- `DEEPSEEK_API_KEY`: Environment variable for DeepSeek API authentication
- `DEEPSEEK_DEFAULT_MODEL`: Defaults to `"deepseek-chat"` (alias for v4-flash)

### 3. Cost Tracking (`src/crypto_news_aggregator/services/cost_tracker.py`)

Added DeepSeek pricing to `PRICING` dict:
- `deepseek-v4-flash`: $0.14/M input, $0.28/M output
- `deepseek-chat`: Alias for v4-flash
- Also updated Anthropic models to current pricing (Opus 4.7/4.6 now $5/$25)

### 4. Operation Routing (`src/crypto_news_aggregator/llm/gateway.py`)

Added `article_enrichment_batch` to `_OPERATION_ROUTING` (currently routes to Anthropic by default):

```python
"article_enrichment_batch": RoutingStrategy(
    "article_enrichment_batch",
    primary="anthropic:claude-haiku-4-5-20251001"
),
```

To switch to DeepSeek:
```python
primary="deepseek:deepseek-v4-flash"
```

### 5. Rate Limiting & Circuit Breaking

**`src/crypto_news_aggregator/services/rate_limiter.py`**
- Added `"article_enrichment_batch": 10000` to `DEFAULT_LIMITS`

**`src/crypto_news_aggregator/services/circuit_breaker.py`**
- Added `"article_enrichment_batch"` to `self.systems` list

### 6. Tests (`tests/llm/test_gateway_provider_routing.py`)

19 unit tests covering:
- Model string parsing (Anthropic, DeepSeek, legacy format)
- Provider URL resolution
- Header generation (API key vs Bearer token)
- Payload building (system prompts, stream settings, thinking mode)
- Response parsing (different field names per provider)
- Operation routing configuration

**All tests pass (19/19).**

---

## How to Switch Providers

### To route entity_extraction to DeepSeek:

**In `gateway.py` line 98-100:**
```python
"entity_extraction": RoutingStrategy(
    "entity_extraction",
    primary="deepseek:deepseek-v4-flash"  # ← change this line
),
```

**That's it.** All calls to entity_extraction now go through DeepSeek API.

### To rollback:
```python
primary="anthropic:claude-haiku-4-5-20251001"
```

---

## How It Works

### Request Flow

1. Caller invokes `gateway.call_sync(..., model="deepseek:deepseek-v4-flash", operation="entity_extraction")`
2. Gateway parses: `provider="deepseek"`, `model_name="deepseek-v4-flash"`
3. Gateway checks budget via `check_llm_budget("entity_extraction")`
4. Gateway builds DeepSeek-specific request:
   - URL: `https://api.deepseek.com/chat/completions`
   - Headers: `Authorization: Bearer {DEEPSEEK_API_KEY}`
   - Payload: OpenAI-compatible format with `stream=false`, `thinking={type: disabled}`
5. Gateway POSTs, receives response
6. Gateway parses DeepSeek response fields (prompt_tokens, completion_tokens, message.content)
7. Gateway calls `CostTracker.track_call()` with `model="deepseek-v4-flash"`
8. CostTracker calculates cost: `(input_tokens * 0.14 + output_tokens * 0.28) / 1_000_000`
9. Gateway writes trace to `llm_traces` with cost, operation, model, token counts
10. Caller receives `GatewayResponse` with all metadata

### Centralized Properties

✅ **Same gateway, same budget checks**: DeepSeek calls respect spend caps  
✅ **Same tracing**: `llm_traces` includes provider, tokens, cost  
✅ **Same cache**: DeepSeek responses are cached with same logic  
✅ **Same rate limits**: `article_enrichment_batch` cap applies to both providers  
✅ **Same circuit breaker**: Failures tracked and auto-recovery via half-open state  
✅ **One-line rollback**: Switch provider by changing routing strategy  

---

## Validation Path (TASK-086)

Once this is merged, TASK-086 will:

1. Create test harness that routes specific operations to DeepSeek
2. Run 5 golden articles through entity_extraction, sentiment_analysis, theme_extraction
3. Compare outputs with Haiku baseline
4. Verify cost calculations (spot-check llm_traces)
5. Validate token counts against DeepSeek dashboard
6. Document agreement rates and cost savings

---

## Notes

- **No standalone `DeepSeekProvider` class**: All routing is centralized in gateway
- **Backward compatible**: Legacy code that doesn't specify provider defaults to Anthropic
- **Production-ready**: Uses same error handling, retries, and tracing as Anthropic
- **Cost tracking is real**: Uses direct API pricing, not OpenRouter markup pricing
- **Cache support**: DeepSeek responses are cached and cost-free on hit

---

## Files Modified

- `src/crypto_news_aggregator/llm/gateway.py` (provider-aware routing, 200+ lines added)
- `src/crypto_news_aggregator/core/config.py` (DEEPSEEK_API_KEY, DEEPSEEK_DEFAULT_MODEL)
- `src/crypto_news_aggregator/services/cost_tracker.py` (DeepSeek pricing)
- `src/crypto_news_aggregator/services/rate_limiter.py` (article_enrichment_batch limit)
- `src/crypto_news_aggregator/services/circuit_breaker.py` (article_enrichment_batch tracking)
- `tests/llm/test_gateway_provider_routing.py` (NEW, 19 unit tests)

---

## Effort

- **Implementation**: ~2 hours (provider-aware gateway refactor)
- **Testing**: ~30 min (19 unit tests, all pass)
- **Documentation**: ~30 min (this file + code comments)
- **Total**: ~3 hours

---

## Next Steps

→ TASK-086: Production validation (5 articles per operation, cost/agreement verification)
