bug-039-sonnet-fallback-cost-leak

---
id: BUG-039
type: bug
status: completed
priority: high
severity: high
created: 2026-02-24
updated: 2026-02-24
merged: 2026-02-24T20:51:29Z
pr: "183"
---

# Sonnet Fallback in General LLM Provider Causes 100+ Unnecessary Expensive Calls/Day

## Problem

`AnthropicProvider._get_completion()` includes `claude-sonnet-4-5-20250929` as a fallback model. This method is the **general-purpose LLM call** used by all narrative processing — not just briefings. Any 403 from Haiku (rate limit, transient error) silently escalates to Sonnet at **5x the cost**. Cost dashboard showed 112 Sonnet calls yesterday; only ~10-15 should be briefing-related.

## Expected Behavior

- Sonnet should **only** be used for briefing generation (in `briefing_agent.py`, which has its own model fallback chain)
- All narrative processing (`narrative_themes.py`) should use Haiku exclusively
- If Haiku fails, the call should fail — not silently escalate to an expensive model

## Actual Behavior

Every LLM call in the system goes through `_get_completion()` with this fallback chain:

```python
# src/crypto_news_aggregator/llm/anthropic.py (lines 38-43)
models_to_try = [
    self.model_name,                    # Haiku (from config)
    "claude-sonnet-4-5-20250929",       # ← PROBLEM: silent expensive fallback
    "claude-haiku-4-5-20251001",        # ← redundant (same as model_name)
]
```

Functions that call `get_llm_provider()._get_completion()` (all in `narrative_themes.py`):

| Function | Calls Per | Frequency |
|----------|-----------|-----------|
| `discover_narrative_from_article()` | 1 per article (up to 4 retries) | Every narrative detection cycle |
| `generate_narrative_from_cluster()` | 2 per cluster (generate + polish) | Per cluster |
| `extract_themes_from_article()` | 1 per article | Theme backfill |
| `generate_narrative_from_theme()` | 1 per theme | Per theme |

With 100-500 articles/day processed, even a 25% Haiku failure rate = 100+ Sonnet calls.

**Secondary issue:** `_get_completion()` does **not** write to the `api_costs` collection. Only `OptimizedAnthropicLLM` and `briefing_agent.py` track costs. So these Sonnet calls are invisible to cost monitoring.

## Steps to Reproduce
1. Observe cost dashboard showing 112 Sonnet calls in one day
2. Only 2 scheduled briefings/day (each uses ~5 Sonnet calls max with self-refine)
3. Remaining ~100 calls come from narrative processing falling back to Sonnet

## Environment
- Environment: production (Railway)
- User impact: high (cost — Sonnet is 3x input / 3x output vs Haiku)
- Estimated daily waste: ~$0.50-2.00/day depending on failure rate

---

## Resolution

**Status:** ✅ CODE COMPLETE (2026-02-24)
**Fixed:** 2026-02-24 (BUG-039)
**Branch:** `fix/bug-039-sonnet-fallback-cost-leak`
**Commit:** c997a27
**PR:** #183

### Root Cause

`AnthropicProvider._get_completion()` was designed with a defensive fallback chain, but Sonnet was included as a fallback for a method that handles **all** LLM calls system-wide. The briefing agent already has its own separate fallback chain in `_call_llm()` (lines 766-834), so the general provider doesn't need Sonnet.

### Changes Made

#### File 1: `src/crypto_news_aggregator/llm/anthropic.py`

**Change:** Remove Sonnet from `_get_completion()` fallback chain. Keep Haiku-only with a single retry.

**Before (lines 38-43):**
```python
models_to_try = [
    self.model_name,                    # Primary model from config
    "claude-sonnet-4-5-20250929",       # Sonnet 4.5
    "claude-haiku-4-5-20251001",        # Haiku 4.5 (fallback)
]
```

**After:**
```python
models_to_try = [
    self.model_name,  # Primary model from config (Haiku)
    # NOTE: Sonnet intentionally excluded. Sonnet is only used in
    # briefing_agent.py which has its own model fallback chain.
    # See BUG-039 for context.
]
```

**Also add logging (after line 59, inside the 403 handler):**
```python
if e.response.status_code == 403:
    logger.warning(
        f"403 Forbidden for model {model}. "
        f"NOT falling back to Sonnet (BUG-039). "
        f"Will retry or fail gracefully."
    )
```

#### File 2: `src/crypto_news_aggregator/llm/anthropic.py` — `extract_entities_batch()`

**Change:** Remove Sonnet fallback models from entity extraction batch method (lines ~165-170).

**Before:**
```python
models_to_try = [
    (settings.ANTHROPIC_ENTITY_MODEL, "Haiku 3.5"),
    (settings.ANTHROPIC_ENTITY_FALLBACK_MODEL, "Sonnet 3.5 (Fallback)"),
    ("claude-3-5-sonnet-20240620", "Sonnet 3.5 (June)"),
]
```

**After:**
```python
models_to_try = [
    (settings.ANTHROPIC_ENTITY_MODEL, "Haiku 4.5"),
    # NOTE: Sonnet fallbacks removed — entity extraction should
    # fail rather than silently use 5x more expensive model.
    # See BUG-039 for context.
]
```

#### File 3: `src/crypto_news_aggregator/core/config.py`

**Change:** Remove `ANTHROPIC_ENTITY_FALLBACK_MODEL` config or mark deprecated.

**Before (line ~49):**
```python
ANTHROPIC_ENTITY_FALLBACK_MODEL: str = "claude-sonnet-4-5-20250929"
```

**After:**
```python
# DEPRECATED by BUG-039: Entity extraction no longer falls back to Sonnet
# ANTHROPIC_ENTITY_FALLBACK_MODEL: str = "claude-sonnet-4-5-20250929"
```

### Where Sonnet IS Correctly Used (Do Not Change)

| Location | Purpose | Why Sonnet Is Correct |
|----------|---------|----------------------|
| `briefing_agent.py:766-834` (`_call_llm()`) | Briefing generation | Complex synthesis task, has own fallback chain |
| `optimized_anthropic.py:generate_narrative_summary()` | Narrative summaries | Explicitly chosen for complex reasoning |

### Testing

1. `grep -rn "sonnet" src/crypto_news_aggregator/ --include="*.py"` — verify Sonnet only appears in briefing_agent.py and optimized_anthropic.py (intentional uses)
2. Trigger narrative detection manually and confirm all calls use Haiku in worker logs
3. Monitor `api_costs` collection for 24 hours — Sonnet calls should drop to ~10-15/day (briefings only)
4. Verify briefings still generate correctly (briefing_agent.py has its own Sonnet fallback)

### Files Changed

- `src/crypto_news_aggregator/llm/anthropic.py` — Remove Sonnet from `_get_completion()` and `extract_entities_batch()` fallback chains
- `src/crypto_news_aggregator/core/config.py` — Deprecate `ANTHROPIC_ENTITY_FALLBACK_MODEL`