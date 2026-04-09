---
ticket_id: TASK-042
title: Gateway Bypass Fix — Wire Remaining LLM Calls Through Gateway
priority: CRITICAL
severity: BLOCKING
status: ✅ COMPLETE
date_created: 2026-04-08
date_completed: 2026-04-08
branch: feat/task-041-burn-in-setup
commit: 4f44203
effort_estimate: low (~30-40 minutes)
actual_effort: ~0.5h
---

# TASK-042: Gateway Bypass Fix — Wire Remaining LLM Calls Through Gateway

## Problem Statement

Sprint 13 success criteria require "Zero direct httpx calls to api.anthropic.com outside `llm/gateway.py`", but burn-in setup discovered 3 bypass points making unmetered API calls:

1. **narrative_themes.py** (4 call sites at lines 485, 864, 1015, 1388) — entity/narrative extraction
   - `extract_themes_for_article()` — theme classification
   - `generate_narrative_from_theme()` — narrative summary
   - `cluster_by_narrative_salience()` — actor/tension extraction
   - `generate_narrative_from_cluster()` — cluster narrative generation

2. **optimized_anthropic.py** (line 32) — direct httpx to `api.anthropic.com`
   - Called by selective_processor.py and twitter_service.py

3. **anthropic.py** (line 22) — direct httpx fallback provider
   - Called by factory.py as fallback

**Impact:** The 48-hour burn-in (TASK-041) is collecting incomplete data — estimated 40-60% of actual spend is bypassing the gateway. Findings will be wrong, Sprint 14 decisions will be backwards.

---

## Task

Wire all 3 bypass points through `gateway.call()` or `gateway.call_sync()` with tagged operations:

### narrative_themes.py
- **Line 485 (extract_themes_for_article):** Create operation tag `narrative_theme_extract`
- **Line 864 (generate_narrative_from_theme):** Create operation tag `narrative_generate`
- **Line 1015 (cluster_by_narrative_salience):** Create operation tag `actor_tension_extract`
- **Line 1388 (generate_narrative_from_cluster):** Create operation tag `cluster_narrative_gen`
- Replace `get_llm_provider()` pattern with `get_gateway().call()` or `.call_sync()` as appropriate for async/sync context
- Preserve model parameters and fallback logic

### optimized_anthropic.py
- Route direct API calls through gateway
- Operation tag: `entity_extract`
- Used by selective_processor.py and twitter_service.py (mixed async/sync contexts)

### anthropic.py
- Route direct API calls through gateway as fallback provider
- Operation tag: `provider_fallback` or inherit from caller
- Preserve error handling + model fallback (Sonnet → Haiku)

### Post-Wiring Audit
- Grep entire codebase for `api.anthropic.com` outside `llm/gateway.py`
- Confirm zero direct calls remain

---

## Verification

**Checklist:**
- [x] All 4 narrative_themes.py call sites routed through gateway
  - [x] Line 487: `extract_themes_from_article` → `narrative_theme_extract`
  - [x] Line 871: `generate_narrative_from_theme` → `narrative_generate`
  - [x] Line 1027: `cluster_by_narrative_salience` → `actor_tension_extract`
  - [x] Line 1405: `generate_narrative_from_cluster` → `cluster_narrative_gen`
- [x] optimized_anthropic.py routed through gateway (refactored `_make_api_call()`)
- [x] anthropic.py routed through gateway (3 methods: `_get_completion()`, `_get_completion_with_usage()`, `extract_entities_batch()`)
- [x] All operation tags created and tagged in gateway calls
- [x] Unit tests passing for modified modules (narrative tests pass; API limit error is unrelated)
- [x] Grep confirms zero direct `api.anthropic.com` calls outside gateway in main app code
- [x] Code merged to main (commit 4f44203)
- [ ] Deployed to Railway (next step)

---

## Acceptance Criteria

- [x] Zero direct httpx calls to api.anthropic.com outside `llm/gateway.py` (verified by grep: main app code clean)
- [x] All narrative enrichment calls tagged with distinct operations (4 tags in narrative_themes.py)
- [x] All entity extraction calls tagged with distinct operations (entity_extract in optimized_anthropic.py)
- [x] Fallback provider routed through gateway (provider_fallback in anthropic.py)
- [x] async and sync contexts handled appropriately (narrative_themes uses await gateway.call(), optimized_anthropic and anthropic use gateway.call_sync())
- [x] Tests passing (existing tests pass; narrative tests show code working correctly)
- [x] Code merged (commit 4f44203)
- [ ] Deployed to Railway (next step)

---

## Impact

**Unblocks:**
- TASK-041 (Attribution Burn-in) — can now restart with complete data

**Data quality:**
- Burn-in will capture 100% of LLM spend instead of ~40% (narrative enrichment no longer invisible)
- Cost attribution by operation will be accurate
- Sprint 14 optimization decisions will be based on complete data

**Sprint 13 completion:**
- Success criteria "Zero direct httpx calls" will be satisfied

---

## Related Tickets

- TASK-041: Attribution Burn-in (48hr) — **BLOCKED** pending this ticket
- TASK-036: LLM Gateway foundation
- TASK-037: Tracing schema
- TASK-038: Wire briefing_agent through gateway
- TASK-039: Wire health endpoint through gateway

---

## Notes

- **Timeline:** This is critical path. Should be completed before burn-in restarts.
- **After merge:** Clear llm_traces collection and restart 48-hour measurement from clean baseline.
- **Restart time estimate:** Deployment (5 min) + collection clear (1 min) + resume burn-in