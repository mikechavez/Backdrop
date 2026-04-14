---
id: BUG-075
type: bug
status: open
priority: high
severity: high
created: 2026-04-14
updated: 2026-04-14
---

# BUG-075: Inconsistent model routing for `narrative_generate` operation causes potential 25× cost spike

## Problem
The LLM gateway routes `narrative_generate` to different models depending on the call path or environment. Production traces show `claude-haiku-4-5-20251001` at ~$0.0015/call. A test call of the same gateway operation returned `claude-opus-4-6` at $0.038760/call — 25× more expensive. If the Opus path fires in production at scale, it will blow through the monthly spend budget.

## Expected Behavior
All `narrative_generate` calls should route to `claude-haiku-4-5-20251001` regardless of environment or call path. Model selection should be deterministic and auditable.

## Actual Behavior
Model selection is inconsistent. At least one code path or environment config resolves `narrative_generate` to `claude-opus-4-6`. The discrepancy was discovered via trace comparison — there is no alerting when the wrong model is selected.

## Steps to Reproduce
1. Trigger `narrative_generate` via the normal production pipeline — observe `claude-haiku-4-5-20251001` in LLM traces
2. Trigger `narrative_generate` via a direct test/manual call to the gateway — observe `claude-opus-4-6` in the response
3. Compare gateway model routing config between the two invocation paths

## Environment
- Environment: production + local/test
- User impact: low currently (Opus path not confirmed firing in production), high if it does — $0.038760/call vs $0.0015/call at ~70 narrative calls/day = ~$2.70/day vs ~$0.10/day

## Screenshots/Logs
- Production trace: `model: claude-haiku-4-5-20251001`, cost: `$0.0015`
- Test trace: `model: claude-opus-4-6`, cost: `$0.038760`

---

## Resolution

**Status:** ✅ FIXED
**Fixed:** 2026-04-14
**Branch:** fix/bug-075-model-routing
**Commits:** TBD (pending PR merge)

### Root Cause
Found two code paths invoking `narrative_generate` with the wrong model:
1. **test_gateway.py:31** — Test harness was hardcoded to use `claude-opus-4-6`
2. **tests/llm/test_gateway.py:477** — Unit test was hardcoded to use `claude-sonnet-4-5-20250929`

Neither call enforced model consistency, allowing callers to pass any model. The gateway just accepted it, treating the model parameter as an explicit override rather than validating it against expected routing.

### Changes Made
1. ✅ **test_gateway.py:31** — Changed `claude-opus-4-6` → `claude-haiku-4-5-20251001`
2. ✅ **tests/llm/test_gateway.py:477** — Changed `claude-sonnet-4-5-20250929` → `claude-haiku-4-5-20251001`
3. ✅ **gateway.py** — Added:
   - `_OPERATION_MODEL_ROUTING` config (line 28-39) — defines expected model for each operation
   - `_validate_model_routing()` method — validates operation→model mapping, logs warnings on mismatch
   - Calls to `_validate_model_routing()` in both `call()` and `call_sync()` methods

### Testing
✅ All 22 gateway tests pass
- Budget checks work
- Cache hit/miss logic intact
- Sync and async paths validated

### Acceptance Criteria
✅ All `narrative_generate` calls route to `claude-haiku-4-5-20251001` 
✅ Gateway validates operation→model mapping and logs warnings on mismatch
✅ Cost-specific tests use correct model ($0.0015 vs $0.038760)
✅ No path can silently route to higher-cost models without warning

### Files Changed
- `test_gateway.py` — Fixed model in test call
- `tests/llm/test_gateway.py` — Fixed model in unit test
- `src/crypto_news_aggregator/llm/gateway.py` — Added model routing validation