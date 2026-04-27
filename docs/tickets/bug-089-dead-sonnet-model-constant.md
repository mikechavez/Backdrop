---
id: BUG-089
type: bug
status: backlog
priority: low
severity: low
created: 2026-04-26
updated: 2026-04-26
---

# Dead `SONNET_MODEL` constant in `optimized_anthropic.py`

## Problem
`SONNET_MODEL = "claude-sonnet-4-5-20250929"` is defined at line 32 of `optimized_anthropic.py` but never referenced anywhere in the codebase. It is dead code left over from before Sprint 13's gateway consolidation, when `OptimizedAnthropicLLM` had its own model selection logic. All calls now route through `gateway.py` with model routing enforced via `_OPERATION_MODEL_ROUTING`.

## Expected Behavior
No unreferenced model constants in the LLM layer. Every defined constant is actively used or explicitly marked as intentional.

## Actual Behavior
`SONNET_MODEL` is defined but unused. During model tiering work (Sprint 16), this constant could cause confusion — a developer seeing it might assume Sonnet is actively selected somewhere, triggering a false debugging path.

## Steps to Reproduce
```bash
grep -rn "SONNET_MODEL" src/ --include="*.py"
# Returns only the definition at optimized_anthropic.py:32
# No call sites reference it
```

## Environment
- Environment: all (codebase issue, not runtime)
- User impact: low (no functional impact, risk is developer confusion)

---

## Resolution

**Status:** ✅ COMPLETED
**Fixed:** 2026-04-26
**Branch:** `docs/system-documentation-update`
**Commit:** 3ad3082

### Root Cause
`OptimizedAnthropicLLM` previously selected between Haiku and Sonnet based on task complexity. Sprint 13 consolidated all model routing into `gateway.py` via `_OPERATION_MODEL_ROUTING`. The constant was not removed during that refactor.

### Changes Made
✅ Removed line 32 from `src/crypto_news_aggregator/llm/optimized_anthropic.py`:
```python
# DELETED:
SONNET_MODEL = "claude-sonnet-4-5-20250929"  # For complex reasoning
```

✅ Updated module docstring (line 1-7) and class docstring (line 23-27) to reflect that model routing is handled by `gateway.py`.

### Testing
✅ Verified no references:
```bash
grep -rn "SONNET_MODEL" src/ --include="*.py"
# Returns: (no output — zero results)
```

### Files Changed
- `src/crypto_news_aggregator/llm/optimized_anthropic.py` — removed unused SONNET_MODEL constant and updated docstrings