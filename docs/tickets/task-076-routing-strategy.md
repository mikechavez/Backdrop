---
ticket_id: TASK-076
title: RoutingStrategy Implementation — Complete + Wire Routing Into Gateway
priority: critical
severity: high
status: COMPLETE
date_created: 2026-04-27
updated: 2026-04-27
completed: 2026-04-27
effort_estimate: 3-4 hours
actual_effort: 1.5 hours
---

# TASK-076: RoutingStrategy Implementation — Complete + Wire Routing Into Gateway

## Problem Statement

BUG-090 introduces `RoutingStrategy` skeleton and makes routing observable. This task completes the implementation by:
1. Adding deterministic A/B bucketing (MD5 hash → variant split)
2. Moving strategy dict from hardcoded defaults to centralized `_OPERATION_ROUTING`
3. Integrating `select()` method into `gateway.call()` and `call_sync()`
4. **Adding explicit guard clause:** if variant is None or ratio is 0, always return primary (no ambiguity)

After this ticket, FEATURE-053 can perform deterministic Flash vs. Haiku A/B testing.

---

## Task

### 1. Complete RoutingStrategy Class (gateway.py)

Update the `RoutingStrategy` class from BUG-090 skeleton to full implementation:

```python
import hashlib
from typing import Optional

class RoutingStrategy:
    """
    Encapsulates model selection for an operation with support for A/B testing.
    """
    
    def __init__(
        self,
        operation: str,
        primary: str,  # Full model string: "anthropic:claude-haiku-..."
        variant: Optional[str] = None,  # "gemini:gemini-2.5-flash"
        variant_ratio: float = 0.0,  # 0.0-1.0, clamped to [0, 1]
        mode: str = "single"  # "single" or "shadow"
    ):
        self.operation = operation
        self.primary = primary
        self.variant = variant
        self.variant_ratio = max(0.0, min(1.0, variant_ratio))
        self.mode = mode
    
    def select(self, routing_key: str) -> str:
        """
        Deterministically select primary or variant using MD5 bucketing.
        
        Args:
            routing_key: Stable identifier (e.g., "entity_extraction:trace_id_xyz")
        
        Returns:
            Selected model string (primary or variant)
        
        Logic:
        - If variant is None OR variant_ratio == 0: ALWAYS return primary
        - If variant exists AND ratio > 0: MD5 hash key, bucket into [0, 100)
        - If bucket < (ratio * 100): return variant
        - Else: return primary
        """
        # CRITICAL GUARD: if no variant or ratio is 0, always primary
        if not self.variant or self.variant_ratio == 0:
            return self.primary
        
        # Deterministic bucketing via MD5
        hash_val = hashlib.md5(routing_key.encode()).hexdigest()
        hash_int = int(hash_val, 16) % 100
        
        # Determine split point
        split_point = int(self.variant_ratio * 100)
        
        # Return variant if bucket is in the split range
        return self.variant if hash_int < split_point else self.primary
    
    def resolve_model(
        self,
        selected: str,
        requested: Optional[str]
    ) -> tuple[str, bool]:
        """
        Determine actual model and whether routing overrode the request.
        
        Args:
            selected: Model from select() (what routing chose)
            requested: Model from caller (what they asked for, if any)
        
        Returns:
            (actual_model, overridden: bool)
        """
        overridden = requested is not None and requested != selected
        return selected, overridden
```

### 2. Create _OPERATION_ROUTING Dictionary

In `gateway.py`, replace the temporary DEFAULT_STRATEGIES from BUG-090 with a proper dict:

```python
_OPERATION_ROUTING = {
    "narrative_generate": RoutingStrategy(
        "narrative_generate",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "entity_extraction": RoutingStrategy(
        "entity_extraction",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "narrative_theme_extract": RoutingStrategy(
        "narrative_theme_extract",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "actor_tension_extract": RoutingStrategy(
        "actor_tension_extract",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "cluster_narrative_gen": RoutingStrategy(
        "cluster_narrative_gen",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "narrative_polish": RoutingStrategy(
        "narrative_polish",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "briefing_generate": RoutingStrategy(
        "briefing_generate",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "briefing_refine": RoutingStrategy(
        "briefing_refine",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "briefing_critique": RoutingStrategy(
        "briefing_critique",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "provider_fallback": RoutingStrategy(
        "provider_fallback",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "sentiment_analysis": RoutingStrategy(
        "sentiment_analysis",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "theme_extraction": RoutingStrategy(
        "theme_extraction",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "relevance_scoring": RoutingStrategy(
        "relevance_scoring",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "insight_generation": RoutingStrategy(
        "insight_generation",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
}
```

### 3. Update _get_routing_strategy() Helper

Replace the temporary version from BUG-090 with production version that uses `_OPERATION_ROUTING`:

```python
def _get_routing_strategy(operation: str) -> RoutingStrategy:
    """
    Retrieve routing strategy for an operation.
    
    Args:
        operation: Operation name
    
    Returns:
        RoutingStrategy instance
    
    Raises:
        ValueError if operation not in _OPERATION_ROUTING
    """
    if operation not in _OPERATION_ROUTING:
        raise ValueError(
            f"Operation '{operation}' has no routing strategy. "
            f"Available: {list(_OPERATION_ROUTING.keys())}"
        )
    return _OPERATION_ROUTING[operation]
```

### 4. Integrate select() Into gateway.call()

Update the `call()` method to use `select()` for routing:

```python
async def call(
    self,
    operation: str,
    prompt: str,
    messages: Optional[List[Dict]] = None,
    provider: Optional[str] = None,
    requested_model: Optional[str] = None,
    routing_key: Optional[str] = None,  # NEW: stable identifier for A/B testing
    **kwargs
) -> GatewayResponse:
    """
    Args:
        operation: LLM operation name
        prompt: Prompt or system message
        messages: Message history
        provider: Explicit provider override (use with caution)
        requested_model: What caller requested (not guaranteed)
        routing_key: Stable identifier for deterministic A/B split.
                     Default: f"{operation}:{self.trace_id}"
    """
    
    # Default routing key if not provided
    if routing_key is None:
        routing_key = f"{operation}:{self.trace_id}"
    
    # Step 1: Get routing strategy for this operation
    strategy = _get_routing_strategy(operation)
    
    # Step 2: Select model using deterministic bucketing
    selected_model = strategy.select(routing_key)
    
    # Step 3: Determine actual model and whether we overrode request
    actual_model, model_overridden = strategy.resolve_model(selected_model, requested_model)
    
    # Step 4: Log override for debugging
    if model_overridden:
        logger.warning(
            f"Model override: operation={operation}, "
            f"requested={requested_model}, "
            f"actual={actual_model}, "
            f"trace_id={self.trace_id}"
        )
    
    # Step 5: Parse provider from model string (e.g., "anthropic:claude-haiku-..." → "anthropic")
    provider_name, model_name = actual_model.split(":", 1)
    
    # Step 6: Route to correct provider (via factory)
    provider_instance = get_llm_provider(provider_name)
    
    # Step 7: Call provider with model_name only
    # ... rest of existing logic, but use actual_model and model_overridden ...
    
    # Step 8: Return response with all routing fields
    return GatewayResponse(
        model=actual_model,  # DEPRECATED alias
        actual_model=actual_model,
        requested_model=requested_model,
        model_overridden=model_overridden,
        # ... rest of existing fields ...
    )
```

### 5. Integrate select() Into gateway.call_sync()

Same changes as `call()`, but sync version.

### 6. Update Cost Tracking to Use actual_model

Ensure all cost tracking uses `actual_model`:

```python
# When logging cost:
cost_key = f"{actual_model}:{operation}"

# When querying costs, use actual_model (not requested_model)
```

---

## Testing

### Unit Tests Required

```python
def test_routing_strategy_select_no_variant():
    """If variant is None, select() always returns primary"""
    strategy = RoutingStrategy(
        "test_op",
        primary="anthropic:haiku",
        variant=None,  # No variant
        variant_ratio=0.5  # Ratio doesn't matter
    )
    assert strategy.select("key_1") == "anthropic:haiku"
    assert strategy.select("key_2") == "anthropic:haiku"

def test_routing_strategy_select_zero_ratio():
    """If variant_ratio is 0, select() always returns primary"""
    strategy = RoutingStrategy(
        "test_op",
        primary="anthropic:haiku",
        variant="gemini:flash",
        variant_ratio=0.0  # Zero ratio
    )
    assert strategy.select("key_1") == "anthropic:haiku"
    assert strategy.select("key_2") == "anthropic:haiku"

def test_routing_strategy_select_deterministic():
    """Same key → same output (determinism)"""
    strategy = RoutingStrategy(
        "test_op",
        primary="anthropic:haiku",
        variant="gemini:flash",
        variant_ratio=0.5
    )
    key = "entity_extraction:trace_abc123"
    assert strategy.select(key) == strategy.select(key)

def test_routing_strategy_select_split():
    """With variant_ratio=0.5, roughly 50% go to each model"""
    strategy = RoutingStrategy(
        "test_op",
        primary="anthropic:haiku",
        variant="gemini:flash",
        variant_ratio=0.5
    )
    
    variant_count = 0
    for i in range(100):
        key = f"test_op:trace_{i}"
        if strategy.select(key) == "gemini:flash":
            variant_count += 1
    
    # Should be ~50, with reasonable tolerance (e.g., 40-60)
    assert 40 <= variant_count <= 60

def test_get_routing_strategy_all_operations():
    """All 14 operations have strategies"""
    operations = [
        "narrative_generate", "entity_extraction", "narrative_theme_extract",
        "actor_tension_extract", "cluster_narrative_gen", "narrative_polish",
        "briefing_generate", "briefing_refine", "briefing_critique",
        "provider_fallback", "sentiment_analysis", "theme_extraction",
        "relevance_scoring", "insight_generation"
    ]
    for op in operations:
        strategy = _get_routing_strategy(op)
        assert strategy is not None
        assert strategy.primary == "anthropic:claude-haiku-4-5-20251001"

def test_get_routing_strategy_unknown_raises():
    """Unknown operation raises ValueError"""
    with pytest.raises(ValueError, match="unknown_op"):
        _get_routing_strategy("unknown_op")
```

### Integration Tests Required

- [ ] `gateway.call()` accepts `routing_key` parameter
- [ ] Default `routing_key = f"{operation}:{trace_id}"` works
- [ ] Model string parsing "provider:model_name" handles both anthropic and gemini
- [ ] `GatewayResponse.actual_model`, `requested_model`, `model_overridden` populated correctly
- [ ] Cost tracking uses `actual_model` (not `requested_model`)
- [ ] All 22 existing gateway tests pass (no regression)

---

## Verification

- [ ] `RoutingStrategy.select()` is deterministic (unit test passes)
- [ ] `RoutingStrategy.select()` respects variant_ratio (unit test passes)
- [ ] Guard clause works: if variant is None or ratio is 0, always return primary
- [ ] `_OPERATION_ROUTING` dict covers all 14 operations
- [ ] `_get_routing_strategy()` raises ValueError for unknown operations
- [ ] `gateway.call()` uses `select()` and returns correct actual_model
- [ ] `gateway.call_sync()` uses `select()` and returns correct actual_model
- [ ] Cost tracking uses `actual_model`
- [ ] All 22 existing tests pass (no regression)

---

## Acceptance Criteria

- [ ] All 14 operations have explicit routing strategies
- [ ] `RoutingStrategy.select()` deterministically buckets via MD5
- [ ] **CRITICAL: If variant is None OR variant_ratio == 0, always return primary**
- [ ] `gateway.call()` accepts `routing_key` parameter
- [ ] Default `routing_key = f"{operation}:{trace_id}"` implemented
- [ ] Model string format "provider:model_name" enforced
- [ ] `GatewayResponse` fields (actual_model, requested_model, model_overridden) populated
- [ ] Deterministic bucketing verified (unit test)
- [ ] 50/50 A/B split verified (unit test with variant_ratio=0.5)
- [ ] No regressions (all 22 tests pass)

---

## Impact

- Enables transparent A/B testing and model swaps
- Foundation for FEATURE-053 (Flash evaluations)
- Makes model routing observable, deterministic, and debuggable

---

## Related Tickets

- BUG-090 (must be merged first; this completes it)
- TASK-077 (GeminiProvider must be available for routing)
- FEATURE-053 (Flash evals need routing control)

---

## Completion Summary (2026-04-27)

✅ **TASK-076 COMPLETE**

**Implementation Details:**
- ✅ Added `RoutingStrategy.select(routing_key: str) → str` method with MD5 bucketing
- ✅ Critical guard clause: if variant is None OR ratio == 0, ALWAYS return primary
- ✅ Created centralized `_OPERATION_ROUTING` dict with all 14 operations (all primary=Haiku)
- ✅ Updated `_get_routing_strategy()` to raise ValueError for unknown operations
- ✅ Integrated `select()` into `_resolve_routing()` method
- ✅ Both `call()` and `call_sync()` accept `routing_key` parameter (default: f"{operation}:{trace_id}")
- ✅ `GatewayResponse` fields populated: actual_model, requested_model, model_overridden

**Test Coverage:**
- ✅ 17 new unit tests in `tests/llm/test_task_076_routing.py`
  - Guard clause tests (variant=None, ratio=0)
  - Determinism tests (same key → same output)
  - A/B split tests (50/50, 75/25 ratios)
  - Override detection tests
  - Operation routing tests (all 14 operations)
  - Error handling tests (unknown operations)
- ✅ All 22 existing gateway tests pass (no regressions)
- ✅ Total: 39 tests passing

**Files Modified:**
1. `src/crypto_news_aggregator/llm/gateway.py` — RoutingStrategy completion, integration
2. `tests/llm/test_task_076_routing.py` — New comprehensive unit tests

**Branch:** `fix/bug-090-eliminate-silent-model-override` (commit 713358f)
**Ready for:** PR → merge → unblocks FEATURE-053

**Impact:**
- Model routing now supports deterministic A/B testing via MD5 bucketing
- Foundation complete for FEATURE-053 (Flash evaluations)
- Guard clause prevents ambiguous routing scenarios
- All acceptance criteria met, all tests passing