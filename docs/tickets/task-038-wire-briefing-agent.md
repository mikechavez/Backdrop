---
id: TASK-038
type: feature
status: backlog
priority: critical
complexity: high
created: 2026-04-08
updated: 2026-04-08
---

# Wire briefing_agent.py Through LLM Gateway

## Problem/Opportunity

`briefing_agent.py` is the primary suspected cost driver. It runs its own `httpx.AsyncClient` directly to `api.anthropic.com` with Sonnet 4.5, completely bypassing the spend cap. The self-refine loop (generate + up to 2×(critique + rewrite)) produces up to 5 LLM calls per briefing, 10/day. All 5 calls are tagged generically as `"briefing_generation"` — no way to distinguish generate vs critique vs refine in cost data.

## Proposed Solution

Rip out all direct API access from `briefing_agent.py` and route every LLM call through the gateway from TASK-036. Tag each call with a distinct operation name so attribution data can show exactly which phase costs what.

## Acceptance Criteria

- [ ] `ANTHROPIC_API_URL` constant (line 53) removed from `briefing_agent.py`
- [ ] `DEFAULT_MODEL` constant (line 54) removed — model selection moves to the call site using the gateway
- [ ] `FALLBACK_MODELS` list (lines 55-57) removed
- [ ] `_call_llm` method (lines 800-885) replaced with a thin wrapper that calls `gateway.call()`
- [ ] `import httpx` removed from `briefing_agent.py` (no longer needed)
- [ ] `self.api_key` removed from `BriefingAgent.__init__` (gateway owns the key)
- [ ] Three distinct operation tags used: `briefing_generate`, `briefing_critique`, `briefing_refine`
- [ ] `generate_briefing` (line 355 area) calls gateway with `operation="briefing_generate"`
- [ ] `_self_refine` critique call (line 393 area) uses `operation="briefing_critique"`
- [ ] `_self_refine` refinement call (line 416 area) uses `operation="briefing_refine"`
- [ ] On spend cap breach, `LLMError` propagates up and kills the briefing (no silent fallback)
- [ ] Model fallback chain (Sonnet → Haiku) preserved via retry logic in the new wrapper, NOT in the gateway
- [ ] Unit tests: mock gateway, verify correct operation tags passed for generate/critique/refine
- [ ] Integration test: mock gateway to raise LLMError on spend cap, verify briefing generation aborts cleanly

## Dependencies

- TASK-036 (gateway must exist)
- TASK-037 (tracing schema, so traces are written correctly)

## Implementation Notes

### What to remove from `briefing_agent.py`

```python
# DELETE these lines:
# Line 17:  import httpx
# Lines 52-57:
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
FALLBACK_MODELS = [
    "claude-haiku-4-5-20251001",
]

# REMOVE from __init__ (lines 94-108):
#   self.api_key = api_key or settings.ANTHROPIC_API_KEY
#   if not self.api_key: raise ValueError(...)
#   self.cost_tracker = None
# REMOVE: _get_cost_tracker method (lines 110-116)
# REMOVE: entire _call_llm method (lines 800-885)
```

### What to add

```python
# New imports at top of file:
from crypto_news_aggregator.llm.gateway import get_gateway, GatewayResponse
from crypto_news_aggregator.llm.exceptions import LLMError

# New constants (local to this module, not API config):
BRIEFING_PRIMARY_MODEL = "claude-sonnet-4-5-20250929"
BRIEFING_FALLBACK_MODEL = "claude-haiku-4-5-20251001"

# In __init__, replace api_key handling with:
self.gateway = get_gateway()

# New _call_llm replacement:
async def _call_llm(
    self,
    prompt: str,
    system_prompt: str,
    operation: str,
    max_tokens: int = 2048,
) -> str:
    """Call the LLM via gateway with model fallback.

    Args:
        prompt: User message content
        system_prompt: System message
        operation: One of briefing_generate, briefing_critique, briefing_refine
        max_tokens: Max response tokens

    Returns:
        Response text

    Raises:
        LLMError: On spend cap breach or all models failing
    """
    messages = [{"role": "user", "content": prompt}]
    models = [BRIEFING_PRIMARY_MODEL, BRIEFING_FALLBACK_MODEL]

    for model in models:
        try:
            response = await self.gateway.call(
                messages=messages,
                model=model,
                operation=operation,
                max_tokens=max_tokens,
                system=system_prompt,
            )
            if model != BRIEFING_PRIMARY_MODEL:
                logger.info(f"Using fallback model: {model}")
            return response.text
        except LLMError as e:
            if e.error_type == "spend_limit":
                raise  # Never retry on spend cap
            if e.error_type == "auth_error":
                logger.warning(f"403 for {model}, trying fallback...")
                continue
            raise
    raise RuntimeError("All LLM models failed")
```

### Call site changes

In `generate_briefing` (around line 355):
```python
# BEFORE:
response_text = await self._call_llm(prompt, system_prompt)
# AFTER:
response_text = await self._call_llm(prompt, system_prompt, operation="briefing_generate")
```

In `_self_refine` critique (around line 393):
```python
# BEFORE:
critique_response = await self._call_llm(critique_prompt, "You are a quality reviewer...")
# AFTER:
critique_response = await self._call_llm(critique_prompt, "You are a quality reviewer...", operation="briefing_critique")
```

In `_self_refine` refinement (around line 416):
```python
# BEFORE:
refined_response = await self._call_llm(refinement_prompt, "You are a crypto briefing writer...")
# AFTER:
refined_response = await self._call_llm(refinement_prompt, "You are a crypto briefing writer...", operation="briefing_refine")
```

### Remove old cost tracking from _call_llm

The gateway handles all cost tracking and tracing now. The old `tracker.track_call()` block inside `_call_llm` (lines 854-871) is deleted along with the method.

### Test file: `tests/test_briefing_gateway.py`

1. `test_generate_uses_correct_operation` — mock gateway.call, call generate_briefing, assert operation="briefing_generate"
2. `test_critique_uses_correct_operation` — trigger self_refine, assert operation="briefing_critique" 
3. `test_refine_uses_correct_operation` — trigger self_refine with needs_refinement=True, assert operation="briefing_refine"
4. `test_spend_limit_kills_briefing` — mock gateway to raise LLMError(spend_limit), assert generate_briefing raises
5. `test_fallback_on_403` — mock gateway to raise LLMError(auth_error) on first call, succeed on second, assert fallback model used

## Open Questions

- None

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: