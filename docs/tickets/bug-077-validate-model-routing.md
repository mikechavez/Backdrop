---
id: BUG-077
type: bug
status: backlog
priority: high
severity: high
created: 2026-04-14
updated: 2026-04-14
---

# `_validate_model_routing` warns but does not enforce model selection

## Problem

`_validate_model_routing()` in `gateway.py` detects when a caller passes a model that doesn't match the expected model for an operation, logs a warning, and then allows the wrong model to proceed. The method signature is `-> None`; both `call()` and `call_sync()` invoke it but do not use its return value. Any caller — production code, test scripts, or misconfigured tooling — can route Opus calls through the gateway unchecked. At $0.039 per test session and a 25× cost multiplier over Haiku ($0.038760 vs $0.001500 per call), a single misconfigured operation running at production volume would consume the daily budget in minutes.

Additionally, four operation names used by the RSS enrichment sync path (`sentiment_analysis`, `theme_extraction`, `relevance_scoring`, `insight_generation`) and `provider_fallback` are absent from `_OPERATION_MODEL_ROUTING`, so calls using those names are not validated at all.

## Expected Behavior

When a caller passes a model that does not match the expected model for an operation, the gateway silently overrides the model to the correct one and logs a warning. The wrong model is never sent to the Anthropic API. Any operation name registered in `_OPERATION_MODEL_ROUTING` is enforced; unregistered operations pass through unchanged.

## Actual Behavior

The gateway logs a warning but proceeds with whatever model was passed. One `claude-opus-4-6` call appeared in `llm_traces` on operation `narrative_generate` on 2026-04-14, traced to `test_update_diagnostic.py`. The enforcement gap means this would also happen for any future misconfigured production path.

## Steps to Reproduce

1. Call `gateway.call()` or `gateway.call_sync()` with `operation="narrative_generate"` and `model="claude-opus-4-6"`.
2. Observe: warning is logged, but the Opus call proceeds and appears in `llm_traces`.
3. Verify in traces:
   ```javascript
   db.llm_traces.find({ model: "claude-opus-4-6" }).sort({ timestamp: -1 }).limit(5)
   ```

## Environment

- Environment: production (Railway) + Claude Code test sessions
- Services affected: LLMGateway (both async `call()` and sync `call_sync()` paths)
- User impact: high — incorrect model routing causes cost spikes up to 25× per call

---

## Code Location

**Current implementation — `gateway.py`:**

```python
# src/crypto_news_aggregator/llm/gateway.py

_OPERATION_MODEL_ROUTING = {
    "narrative_generate": "claude-haiku-4-5-20251001",
    "entity_extraction": "claude-haiku-4-5-20251001",
    "narrative_theme_extract": "claude-haiku-4-5-20251001",
    "actor_tension_extract": "claude-haiku-4-5-20251001",
    "cluster_narrative_gen": "claude-haiku-4-5-20251001",
    "narrative_polish": "claude-haiku-4-5-20251001",
    "briefing_generate": "claude-haiku-4-5-20251001",
    "briefing_refine": "claude-haiku-4-5-20251001",
    "briefing_critique": "claude-haiku-4-5-20251001",
    # MISSING: provider_fallback, sentiment_analysis, theme_extraction,
    #          relevance_scoring, insight_generation
}

def _validate_model_routing(self, operation: str, model: str) -> None:  # line 240
    if operation in _OPERATION_MODEL_ROUTING:
        expected_model = _OPERATION_MODEL_ROUTING[operation]
        if model != expected_model:
            logger.warning(
                f"Model routing mismatch: operation '{operation}' "
                f"expected '{expected_model}' but got '{model}'. "
                f"This may cause unexpected cost increases."
            )
    # returns None — call proceeds with wrong model

# call() — line 407
self._validate_model_routing(operation, model)   # return value discarded

# call_sync() — line 519
self._validate_model_routing(operation, model)   # return value discarded
```

---

## Resolution

**Status:** ✅ FIXED
**Fixed:** 2026-04-14 18:30:00 UTC
**Branch:** docs/bug-076-migration-complete
**Commit:** c05404e

### Root Cause

`_validate_model_routing` was implemented in Sprint 14 as a detection-only method (return type `-> None`) for backward compatibility with tests. The enforcement step — overriding the model at the call site — was deferred but never ticketed. The call sites discard the return value, so no override is possible under the current signature.

### Changes Required

**1. Change `_validate_model_routing` to return the correct model string:**

```python
def _validate_model_routing(self, operation: str, model: str) -> str:
    """
    Validate and enforce model routing for an operation.

    If the operation has a registered expected model and the caller passed
    a different model, overrides to the expected model and logs a warning.

    Returns the model string to use for the API call.
    """
    if operation in _OPERATION_MODEL_ROUTING:
        expected_model = _OPERATION_MODEL_ROUTING[operation]
        if model != expected_model:
            logger.warning(
                f"Model routing mismatch: operation '{operation}' "
                f"expected '{expected_model}' but got '{model}'. "
                f"Overriding to '{expected_model}'."
            )
            return expected_model
    return model
```

**2. Use the return value at both call sites:**

```python
# call() — line 407
model = self._validate_model_routing(operation, model)

# call_sync() — line 519
model = self._validate_model_routing(operation, model)
```

**3. Add missing operation names to `_OPERATION_MODEL_ROUTING`:**

```python
_OPERATION_MODEL_ROUTING = {
    # existing entries ...
    "provider_fallback": "claude-haiku-4-5-20251001",
    "sentiment_analysis": "claude-haiku-4-5-20251001",
    "theme_extraction": "claude-haiku-4-5-20251001",
    "relevance_scoring": "claude-haiku-4-5-20251001",
    "insight_generation": "claude-haiku-4-5-20251001",
}
```

### Testing

1. Run the full gateway test suite (22 tests + any new ones): all should pass.
2. Manually call `call_sync()` with `operation="narrative_generate"` and `model="claude-opus-4-6"`. Verify:
   - Warning is logged with "Overriding to" language.
   - The `model` field in `llm_traces` shows `claude-haiku-4-5-20251001`, not `claude-opus-4-6`.
3. After deploying to production, confirm no `claude-opus-4-6` entries appear in `llm_traces` from production code paths:
   ```javascript
   db.llm_traces.find({
     model: "claude-opus-4-6",
     timestamp: { $gte: new Date(Date.now() - 86400000) }
   })
   // Expected: 0 results from production operations
   ```

### Files to Change

- `src/crypto_news_aggregator/llm/gateway.py`
  - `_OPERATION_MODEL_ROUTING` dict (add 5 entries)
  - `_validate_model_routing()` signature and body (lines 240–257)
  - `call()` call site (line 407)
  - `call_sync()` call site (line 519)