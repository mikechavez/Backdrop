---
id: BUG-090
type: bug
status: OPEN
priority: critical
severity: critical
created: 2026-04-27
updated: 2026-04-27
---

# BUG-090: Eliminate Silent Model Override — Introduce Observable Routing

## Problem Statement

Model routing currently happens silently. If a caller requests Model A but gateway overrides to Model B, there's no trace of this decision — making debugging impossible and cost attribution impossible. Additionally, the old `_OPERATION_MODEL_ROUTING` dict is hardcoded and doesn't support A/B testing or dynamic routing strategies.

This bug prevents:
- Observing what model was actually used (vs. what was requested)
- Supporting multi-model evaluation (Flash vs. Haiku)
- Debugging cost discrepancies
- Building interview artifacts around routing decisions

---

## Solution

Replace the old silent routing system with an observable `RoutingStrategy` foundation that:
1. Records whether routing was overridden
2. Makes the decision traceable
3. Supports future variant routing
4. Eliminates the hardcoded `_OPERATION_MODEL_ROUTING` dict

---

## Task

### 1. Remove Old Routing Dict
**File:** `src/crypto_news_aggregator/llm/gateway.py`

Delete the entire `_OPERATION_MODEL_ROUTING` dict (~line 28-38). This is dead code after this fix.

```python
# DELETE THIS ENTIRE BLOCK:
_OPERATION_MODEL_ROUTING = {
    "narrative_generate": "claude-opus-4-1-20250805",
    "entity_extraction": "claude-haiku-4-5-20251001",
    # ... etc
}
```

### 2. Introduce RoutingStrategy Skeleton
**File:** `src/crypto_news_aggregator/llm/gateway.py`

Add `RoutingStrategy` class as foundation for observable routing:

```python
class RoutingStrategy:
    """
    Encapsulates model selection for an operation.
    Supports deterministic routing for A/B testing in future sprints.
    
    Currently: all operations use primary model (no variants).
    Sprint 16+: variant_ratio controls split between primary and variant.
    """
    
    def __init__(
        self,
        operation: str,
        primary: str,  # Full model string: "anthropic:claude-haiku-..."
        variant: Optional[str] = None,  # "gemini:gemini-2.5-flash" (future)
        variant_ratio: float = 0.0,  # 0.0-1.0 (% to route to variant)
        mode: str = "single"  # "single" or "shadow" (future-proof)
    ):
        self.operation = operation
        self.primary = primary
        self.variant = variant
        # Clamp variant_ratio to [0, 1]
        self.variant_ratio = max(0.0, min(1.0, variant_ratio))
        self.mode = mode
    
    def resolve_model(
        self,
        requested: Optional[str]
    ) -> tuple[str, bool]:
        """
        Determine actual model and whether routing overrode the request.
        
        Args:
            requested: Model from caller (what they asked for, if any)
        
        Returns:
            (actual_model, overridden: bool)
        
        Currently: always returns primary (no variant yet).
        """
        # If variant is None or ratio is 0, always use primary (no split logic yet)
        if not self.variant or self.variant_ratio == 0:
            actual = self.primary
        else:
            # FUTURE: MD5 bucketing for deterministic split
            # For now, always primary
            actual = self.primary
        
        # Determine if routing overrode caller's request
        overridden = requested is not None and requested != actual
        return actual, overridden
```

### 3. Update GatewayResponse
**File:** `src/crypto_news_aggregator/llm/gateway.py` (GatewayResponse class)

Add fields to track routing decisions:

```python
class GatewayResponse:
    # ... existing fields ...
    
    model: str  # DEPRECATED: use actual_model instead
    actual_model: str  # What we actually used (after routing)
    requested_model: Optional[str]  # What caller asked for (if any)
    model_overridden: bool  # True if routing overrode the request
```

### 4. Update gateway.call() Method
**File:** `src/crypto_news_aggregator/llm/gateway.py`

Integrate `RoutingStrategy.resolve_model()` for observability:

```python
async def call(
    self,
    operation: str,
    prompt: str,
    messages: Optional[List[Dict]] = None,
    provider: Optional[str] = None,
    requested_model: Optional[str] = None,  # What caller asked for
    **kwargs
) -> GatewayResponse:
    """
    Args:
        operation: LLM operation name
        prompt: Prompt or system message
        messages: Message history
        provider: Explicit provider override (use with caution)
        requested_model: What caller requested (not guaranteed to be used)
    """
    
    # Step 1: Get routing strategy for this operation
    # (For now, this is hardcoded in a new _OPERATION_ROUTING dict)
    # TASK-076 will complete this
    strategy = _get_routing_strategy(operation)  # Will implement below
    
    # Step 2: Determine actual model and whether we overrode the request
    actual_model, model_overridden = strategy.resolve_model(requested_model)
    
    # Step 3: Log override for debugging
    if model_overridden:
        logger.warning(
            f"Model override: operation={operation}, "
            f"requested={requested_model}, "
            f"actual={actual_model}, "
            f"trace_id={self.trace_id}"
        )
    
    # Step 4: Use actual_model for all downstream logic
    # (existing call logic, but use actual_model instead of requested_model)
    
    # Step 5: Return response with all routing fields populated
    return GatewayResponse(
        model=actual_model,  # DEPRECATED
        actual_model=actual_model,
        requested_model=requested_model,
        model_overridden=model_overridden,
        # ... rest of existing fields ...
    )
```

### 5. Update gateway.call_sync() Method
**File:** `src/crypto_news_aggregator/llm/gateway.py`

Same changes as `call()`, but sync version.

### 6. Implement _get_routing_strategy() Helper
**File:** `src/crypto_news_aggregator/llm/gateway.py`

```python
def _get_routing_strategy(operation: str) -> RoutingStrategy:
    """
    Retrieve routing strategy for an operation.
    
    Sprint 16: All operations point to Haiku (primary only, no variants).
    Sprint 16+: TASK-076 wires variant routing for A/B testing.
    """
    # TEMPORARY: hardcoded until TASK-076 moves this to _OPERATION_ROUTING dict
    DEFAULT_STRATEGIES = {
        "narrative_generate": RoutingStrategy("narrative_generate", "anthropic:claude-haiku-4-5-20251001"),
        "entity_extraction": RoutingStrategy("entity_extraction", "anthropic:claude-haiku-4-5-20251001"),
        "narrative_theme_extract": RoutingStrategy("narrative_theme_extract", "anthropic:claude-haiku-4-5-20251001"),
        "actor_tension_extract": RoutingStrategy("actor_tension_extract", "anthropic:claude-haiku-4-5-20251001"),
        "cluster_narrative_gen": RoutingStrategy("cluster_narrative_gen", "anthropic:claude-haiku-4-5-20251001"),
        "narrative_polish": RoutingStrategy("narrative_polish", "anthropic:claude-haiku-4-5-20251001"),
        "briefing_generate": RoutingStrategy("briefing_generate", "anthropic:claude-haiku-4-5-20251001"),
        "briefing_refine": RoutingStrategy("briefing_refine", "anthropic:claude-haiku-4-5-20251001"),
        "briefing_critique": RoutingStrategy("briefing_critique", "anthropic:claude-haiku-4-5-20251001"),
        "provider_fallback": RoutingStrategy("provider_fallback", "anthropic:claude-haiku-4-5-20251001"),
        "sentiment_analysis": RoutingStrategy("sentiment_analysis", "anthropic:claude-haiku-4-5-20251001"),
        "theme_extraction": RoutingStrategy("theme_extraction", "anthropic:claude-haiku-4-5-20251001"),
        "relevance_scoring": RoutingStrategy("relevance_scoring", "anthropic:claude-haiku-4-5-20251001"),
        "insight_generation": RoutingStrategy("insight_generation", "anthropic:claude-haiku-4-5-20251001"),
    }
    
    if operation not in DEFAULT_STRATEGIES:
        raise ValueError(
            f"Operation '{operation}' has no routing strategy. "
            f"Available: {list(DEFAULT_STRATEGIES.keys())}"
        )
    
    return DEFAULT_STRATEGIES[operation]
```

### 7. Update Cost Tracking
**File:** `src/crypto_news_aggregator/llm/gateway.py` (cost recording section)

Use `actual_model` instead of `requested_model` for cost attribution:

```python
# OLD:
cost_key = f"{requested_model}:{operation}"

# NEW:
cost_key = f"{actual_model}:{operation}"
```

---

## Verification

- [ ] `_OPERATION_MODEL_ROUTING` dict deleted (no more hardcoded routing)
- [ ] `RoutingStrategy` class exists with `resolve_model()` method
- [ ] `GatewayResponse` includes `actual_model`, `requested_model`, `model_overridden` fields
- [ ] `gateway.call()` populates all three routing fields correctly
- [ ] `gateway.call_sync()` populates all three routing fields correctly
- [ ] Override is logged with trace_id for debugging
- [ ] Cost tracking uses `actual_model` (not `requested_model`)
- [ ] Default strategies cover all 14 operations
- [ ] All 22 gateway tests pass (no regression)

---

## Acceptance Criteria

- [ ] Old `_OPERATION_MODEL_ROUTING` dict completely removed
- [ ] `RoutingStrategy` class introduced as foundation (no A/B yet)
- [ ] `RoutingStrategy.resolve_model()` returns (model, overridden: bool)
- [ ] All routing information traceable in `GatewayResponse`
- [ ] Override logged with operation + requested + actual + trace_id
- [ ] Cost tracking uses actual_model (not requested)
- [ ] All 14 operations have explicit strategies
- [ ] `_get_routing_strategy()` raises ValueError if operation not found

---

## Impact

- Makes model routing observable (critical for debugging + cost attribution)
- Eliminates silent overrides
- Foundation for TASK-076 (completes variant routing)
- Enables FEATURE-053 (Flash evaluations need observable routing)

---

## Related Tickets

- TASK-076 (builds on this to add A/B variant routing)
- FEATURE-053 (depends on observable routing)
- BUG-090 (this ticket)

---

## Note

This is a **foundation ticket**, not a complete variant routing system. TASK-076 will add:
- MD5 bucketing for deterministic splits
- Variant models in RoutingStrategy
- Variant_ratio enforcement

For now, RoutingStrategy always returns primary (no variants). That's correct and intentional.