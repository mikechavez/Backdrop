# Sprint 15 Closeout — Cost Stability + Enforcement

**Status:** ✅ COMPLETE
**Duration:** 2026-04-14 to 2026-04-26
**Sprint Goal:** ✅ ACHIEVED
_Fixed budget enforcement blind spot, closed model routing gap, labeled all cost operations, completed RSS fingerprint coverage, established reliable cost baseline for feature development._

---

## Final Score

| Category | Metric |
|---|---|
| **Tickets Completed** | 13/13 (100%) |
| **Deferred (low priority)** | TASK-070, TASK-071 — carry to Sprint 16 backlog |
| **True Daily Baseline** | $0.54/day (~$16/month) |
| **Monthly Hard Limit** | $30/month enforced via `check_llm_budget()` |
| **Model Routing** | 100% Haiku — zero Opus/Sonnet in production paths |
| **Cost Visibility** | 100% — all calls traced, attributed, enforced via `llm_traces` |

---

## Completed Work

### Cost Enforcement (BUG-079, BUG-077, BUG-078, FEATURE-013)
- ✅ BUG-079: `llm_traces` made single source of truth — `get_daily_cost()` now returns true spend including entity_extraction ($0.177/day previously invisible)
- ✅ BUG-077: `_validate_model_routing()` now enforces model selection — silently overrides wrong models, logs warning, prevents Opus ($0.039/call) reaching API
- ✅ BUG-078: RSS enrichment async methods now pass operation names — zero `provider_fallback` entries post-deploy, $0.26/day now correctly attributed to `article_enrichment_batch`
- ✅ FEATURE-013: Monthly API spend guard deployed — hard limit $30/month, soft limit $22.50/month with Slack alert, monthly dimension overrides daily limits

### Article Quality + Fingerprinting (BUG-076, BUG-080, BUG-081, BUG-082, BUG-084)
- ✅ BUG-076: RSS ingest path now generates article fingerprints — 1,762 articles backfilled, 4 duplicates tagged
- ✅ BUG-080: Briefing date mismatch fixed — UTC→CST/CDT conversion in `_build_generation_prompt()` using `ZoneInfo("America/Chicago")`
- ✅ BUG-081: Briefing guardrails added — rules 9-11 consolidate duplicate events, require named entities, verify figure plausibility
- ✅ BUG-082: Narrative summary pipeline validates implausible figures — regex pattern + post-generation plausibility check with $50B threshold
- ✅ BUG-084: Narrative summary grounding constraints prevent fabricated events — LLM instructed to verify claims against source articles only

### Narrative Pipeline (BUG-083, BUG-088, TASK-073, FEATURE-012)
- ✅ BUG-083 Parts 1 + 2: Market event detector disabled (no new phantoms), existing phantom narratives cleaned from MongoDB
- ✅ BUG-088: Merge path now flags narratives for summary refresh
- ✅ TASK-073: Auto-dormant logic for zombie narratives — one-time cleanup + periodic check deployed
- ✅ FEATURE-012: Scheduled narrative summary regen consumer — 20 refreshes/run cap, budget enforcement, dormant exclusion

### Dead Code Cleanup (BUG-089)
- ✅ BUG-089: `SONNET_MODEL` constant removed from `optimized_anthropic.py` — dead code since Sprint 13 gateway consolidation

---

## Confirmed Cost Baseline (post-sprint)

| Operation | Calls/day | Cost/day |
|---|---|---|
| entity_extraction | ~174 | $0.152 |
| narrative_generate | ~51 | $0.125 |
| article_enrichment_batch | ~variable | ~$0.150 |
| briefing_refine | ~4 | $0.032 |
| briefing_critique | ~4 | $0.023 |
| briefing_generate | ~2 | $0.020 |
| cluster_narrative_gen | ~6 | $0.006 |
| narrative_polish | ~6 | $0.003 |
| **Total** | | **~$0.54** |

Previous high: $2.50–5.00/day (Sprint 12). Reduction: ~89%.

---

## What Didn't Happen (Deferred)

- **TASK-070**: Narrative cost investigation (cache hit rate, batch job volume) — spend is already under target, low urgency, carry to Sprint 16 backlog
- **TASK-071**: Spend threshold recalibration — true spend ($0.54/day) already well under hard limit ($1.00/day), not blocking anything

---

## Handoff to Sprint 16

### Sprint 16 Goal: Model Tiering + Provider Evaluation

Foundation is solid. Every LLM call is traced, attributed, and enforced. `factory.py` already uses a strategy pattern — `LLM_PROVIDER` config supports swapping providers with minimal refactor. `draft_capture.py` has captured production data for evaluation inputs.

**Sprint 16 tasks:**
1. Map every Backdrop operation and both planned agent tasks to complexity tiers
2. Implement Gemini 2.5 Flash provider using existing `factory.py` interface
3. Run challenger models against `draft_capture.py` data on entity_extraction and narrative_generate (highest-volume operations)
4. Score quality, cost, latency — document model selection decisions
5. Wire Helicone proxy in `gateway.py` for unified trace UI across pipeline and future agents
6. TASK-070 from backlog: investigate narrative cache hit rate

### Known carry-forward items
- TASK-070: narrative cost investigation (P3, backlog)
- TASK-071: threshold recalibration (P4, not urgent)

---

## Key Decisions Made

1. **`llm_traces` is the single source of truth** — all cost enforcement, reporting, and alerting reads from here. `api_costs` and `llm_usage` are legacy, not authoritative.
2. **Model routing is enforced at the gateway, not call sites** — `_validate_model_routing()` silently corrects misrouted models before they reach the API.
3. **True baseline is $0.54/day** — the $1.134/day figure from Sprint 14 close was inflated by BUG-066's rolling window bug. Post-fix validation in Session 30 confirmed the real number.
4. **Cost dashboard already existed** — `CostMonitor.tsx` was production-ready; TASK-069 was effectively complete before sprint close.

---

## Sprint 15 Lessons

1. **Confirm what already exists before scoping** — TASK-069 (cost dashboard) was already built as `CostMonitor.tsx`. Better pre-sprint inventory would have caught this.
2. **Baseline numbers need validation** — the $1.134/day figure carried forward from Sprint 14 was wrong. Always re-validate baselines after fixing measurement bugs.
3. **Dead code costs more than the line it occupies** — `SONNET_MODEL` in `optimized_anthropic.py` triggered a 20-minute investigation before being confirmed harmless. Remove dead code at the point of consolidation, not later.

---

**Approved for Sprint 16 transition: ✅**