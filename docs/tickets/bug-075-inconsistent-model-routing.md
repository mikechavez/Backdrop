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

**Status:** Open
**Fixed:**
**Branch:** fix/bug-075-model-routing
**Commit:**

### Root Cause
TBD — audit gateway model routing config for the `narrative_generate` operation. Likely either: (a) a hardcoded model override in a non-production config, or (b) a fallback default that resolves to Opus when the operation name lookup misses.

### Changes Made
TBD

### Testing
1. Trigger `narrative_generate` from all known call paths (scheduled pipeline, manual trigger, direct gateway call)
2. Confirm all traces show `claude-haiku-4-5-20251001`
3. Confirm no path can silently resolve to a higher-cost model

### Files Changed
TBD — likely gateway model routing config and/or the `narrative_generate` operation definition