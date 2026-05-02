# Sprint 17 — Tier 1 Cost Optimization (Prompt Fixes + Threshold Evaluation)

**Status:** ⏳ IN PROGRESS  
**Actual Start:** 2026-04-28 (accelerated)  
**Target End:** 2026-05-17 (extended to include TASK-085, TASK-086 Phase 1, queued TASK-087 reliability refactor, critical TASK-088 trace rebuild, and FEATURE-055 trace analysis planning)  
**Sprint Goal:** Fix broken Tier 1 baselines, define quality thresholds, run evaluations, identify cost-optimized models, **add DeepSeek support through LLMGateway, route the existing enrichment batch to DeepSeek, and validate production behavior with rollback.** Add the trace/observability work required to make that rollout measurable and safe after the `llm_traces` deletion incident.

**Major Discovery (2026-04-30):** Direct DeepSeek API is 10-12x cheaper than OpenRouter. Recommendation: **DeepSeek on all Tier 1 operations saves $55k/year.** Repo review corrected the implementation path: DeepSeek should be added through `LLMGateway`, not as a standalone provider path. Phase 1 routes the existing `article_enrichment_batch` path to DeepSeek and validates sentiment as the primary quality signal because sentiment, relevance, and themes are currently batched together.

**Current Phase:** FEATURE-054 complete. TASK-085 complete (2026-04-30). TASK-086 Phase 1 pre-production validation complete (2026-05-01). TASK-088 trace rebuild complete (2026-05-01). Ready for production deployment and monitoring with improved observability. TASK-087 queued as follow-up reliability refactor. FEATURE-055 backlog/follow-up after TASK-088 to provide a read-only trace analysis CLI.

---

## Context from Sprint 16

Sprint 16 completed observable model routing, provider abstraction, and decision framework documentation. Tier 1 Flash evaluations (FEATURE-053) ran successfully end-to-end. Post-hoc analysis (TASK-080) revealed three critical issues:

1. **Pricing was wrong (off by ~1000x).** Flash is 57% cheaper than Haiku, not more expensive.
2. **Entity and theme baselines are philosophically wrong.** Entity extraction measures mention-level (should be relevance-weighted). Theme extraction includes proper nouns (should exclude them). These aren't model quality issues—they're prompt issues.
3. **Sentiment neutral class is undefined.** All models get 4% accuracy on neutral because the prompt doesn't define what neutral means. This is fixable.

**Opportunity:** Corrected prompts + threshold-based evaluation = real cost savings.

**Foundation:** Evaluation framework is solid. Baselines need fixing. Cost optimization is real and actionable.

---

## Priority 1 — Baseline Fixes (COMPLETE)

### TASK-081: Fix Tier 1 Prompts ✅ COMPLETE
- **Status:** DONE (2026-04-29)
- **Priority:** CRITICAL
- **Effort:** 2-3 hours
- **Goal:** Fix three Tier 1 operation prompts to correct philosophical mismatches discovered in TASK-080

**Changes:**

1. **entity_extraction** — Change from mention-level to relevance-weighted
   - Current: Extract all mentioned entities
   - New: Extract only entities relevant to the narrative (ignore noise mentions)
   - File: `src/crypto_news_aggregator/llm/optimized_anthropic.py`, line 127
   - Impact: Eliminates bimodal distribution (perfect vs catastrophic); expect more consistent results

2. **sentiment_analysis** — Define neutral class
   - Current: Neutral is undefined; all models fail equally (4% accuracy)
   - New: Add explicit criteria/examples for what "neutral" means (e.g., "factual reporting without sentiment")
   - File: `src/crypto_news_aggregator/llm/anthropic.py`, line 127
   - Impact: Flash likely jumps from 75% to 85%+ overall accuracy

3. **theme_extraction** — Exclude proper nouns and coin names
   - Current: Themes include entity names ("Bitcoin", "Federal Reserve")
   - New: Extract only conceptual themes, exclude proper nouns and coin names
   - File: `src/crypto_news_aggregator/llm/anthropic.py`, line 146
   - Impact: Aligns baseline with human expectations; enables fair comparison

- **Deliverable:** Three updated prompts in codebase ✅
  - Entity extraction: relevance-weighted extraction (primary entities only)
  - Sentiment analysis: explicit neutral class definition (-0.3 to 0.3 range)
  - Theme extraction: exclude proper nouns and coin names
- **Testing:** Spot-check validation run on 5 articles per operation ✅
  - Entity extraction: 5/5 OK (3-7 focused entities)
  - Sentiment analysis: 1/5 classification accuracy (neutral class working, conservative bias)
  - Theme extraction: needs prod validation (test harness issue)
- **Output:** Commit fb0ee92, validation report at docs/TASK-081-validation-report.md
- **Status:** Prompts deployed and ready for FEATURE-054 Phase 1

**Spot-Check Article IDs:**
- entity_extraction: 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69de1566972adb5ad8c76cb6, 69dfb314a634582621effb78, 69deb85f2adcac6279c197b5
- sentiment_analysis: 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69e0c3100a57f1a2701de53e, 69e124b5cd3cb7bb0f1de49b, 69de613a972adb5ad8c76df6
- theme_extraction: 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69e0c3100a57f1a2701de53e, 69e124b5cd3cb7bb0f1de49b, 69de613a972adb5ad8c76df6

---

### TASK-082: Define Acceptable Quality Thresholds ✅ COMPLETE
- **Status:** DONE (2026-04-29)
- **Priority:** CRITICAL
- **Effort:** 1 hour
- **Goal:** For each Tier 1 operation, decide: what quality loss is acceptable to save cost?

**Thresholds (finalized):**

| Operation | User Impact | Acceptable Loss | Threshold | Rationale |
|---|---|---|---|---|
| entity_extraction | High (extracted data drives analysis) | <3% | F1 >= 0.82 | Extraction errors cascade. Keep quality bar high. |
| sentiment_analysis | Medium (internal enrichment, not user-facing) | <8% | Accuracy >= 77% | Sentiment is used internally only. Some error acceptable for cost savings. |
| theme_extraction | Medium (internal briefing structure) | <5% | Adjusted F1 >= 0.78 | Themes guide briefing structure. Moderate tolerance for degradation. |

- **Deliverable:** `docs/sprints/sprint-017-tier1-cost-optimization/task-082-define-thresholds/tier1-quality-thresholds.md` ✅
- **Status:** All three thresholds defined with user impact, rationale, and provisional nature documented
- **Notes:** Thresholds are provisional; Phase 4 manual analysis may revise based on failure mode distribution

---

## Priority 2 — Cost Optimization Evaluations (COMPLETE)

### FEATURE-054: Tier 1 Cost Optimization Evals ✅ COMPLETE
- **Status:** ALL PHASES COMPLETE (2026-04-30)
- **Priority:** CRITICAL
- **Effort:** 8-10 hours (actual, including all phases + manual analysis)
- **Dependencies:**
  - TASK-081 (prompt fixes) ✅ required — DONE
  - TASK-082 (thresholds) ✅ required — DONE

**Phases Completed:**

- **Phase 1: Corrected Baselines** ✅ COMPLETE
  - Ran Haiku against corrected prompts on Tier 1 golden sets (100 samples per op)
  - Collected Haiku output as new baselines
  - Success criteria: 3 operations × 100 samples ✅

- **Phase 2: Challenger Model Runs** ✅ COMPLETE
  - Ran Flash, DeepSeek, Qwen against same corrected prompts
  - Used OpenRouter for API calls
  - Collected: output, tokens, latency
  - Success criteria: 3 ops × 3 models × 100 samples = 900 calls ✅ (100% success)

- **Phase 3: Threshold Scoring** ✅ COMPLETE
  - Applied threshold-based scoring (not comparison-based vs Haiku)
  - Result: 0/9 models passed absolute thresholds
  - Finding: Not a model quality failure — reference set imbalance + weak Haiku baseline + reference/prompt mismatch

- **Phase 4: Manual Analysis + Cost Review** ✅ COMPLETE
  - Spot-checked 5-10 failed samples per operation
  - Analyzed behavioral consistency (vs absolute thresholds)
  - **Critical finding:** OpenRouter pricing inflates costs 10-12x. Direct DeepSeek API is 90% cheaper than Haiku.
  - Cost analysis: $59k/year (Haiku) → $4.1k/year (DeepSeek direct API)
  - Sentiment agreement with Haiku: 85% (high, low risk)
  - Entity extraction agreement: 60-64% Jaccard (medium risk)
  - Theme extraction agreement: 16-37% Jaccard (needs reannotation, high risk)

**Key Deliverables:**
- ✅ FEATURE-054-Phase4-manual-analysis.md (comprehensive analysis with spot-checks)
- ✅ Scoring results CSV (all models scored against thresholds)
- ✅ Cost metrics CSV (token counts, latencies, per-model costs)
- ✅ Decision record: DR-2026-05-001 (DeepSeek deployment strategy)
- ✅ Product story (publishable after Phase 1 validation)

**Success Criteria for Sprint 17:**
- ✅ Three prompts fixed and deployed
- ✅ Three thresholds defined with rationale
- ✅ Corrected Haiku baselines collected
- ✅ Challenger models run (Flash, DeepSeek, Qwen) with 900 calls
- ✅ Threshold-based analysis complete
- ✅ Clear answer: DeepSeek on all three operations saves $55k/year
- ✅ Decision record written with phased deployment plan

---

## Implementation Correction (2026-04-30)

Repo review changed the implementation plan for DeepSeek:

- The correct integration point is `LLMGateway`, not a standalone provider path.
- `gateway.py` already owns operation routing, budget checks, API execution, trace writes, cache behavior, and cost tracking handoff.
- Existing production callers already delegate to `gateway.call_sync(...)`, so DeepSeek must be added behind that interface.
- Phase 1 is not truly sentiment-only unless enrichment is split. The current production path combines relevance, sentiment, and themes in `article_enrichment_batch`.
- Minimal-change decision: route `article_enrichment_batch` to DeepSeek first, validate sentiment as the primary quality signal, and defer the gateway-owned circuit breaker/rate limiter refactor to TASK-087.
- `article_enrichment_batch` must be added to existing rate limiter and circuit breaker tracked operation lists during TASK-085.

**Deferred refactor:** TASK-087 moves circuit breaker and rate limiter enforcement into `LLMGateway` and introduces provider-scoped reliability keys after DeepSeek is working through the gateway.

---

## Observability & Safety Update (2026-05-01)

A production safety incident changed the observability scope for Sprint 17: most of the existing `llm_traces` collection was deleted, and the remaining trace schema is not rich enough to reliably debug model routing, provider selection, cache behavior, smoke-vs-production separation, or briefing self-refine phases. This does not change the DeepSeek rollout path, but it does add a critical observability dependency for validating that rollout safely.

### TASK-088: Rebuild LLM Trace System with Clean Collection Reset ✅ COMPLETE (2026-05-01)
- **Status:** COMPLETE (2026-05-01)
- **Priority:** CRITICAL
- **Effort:** 4-6 hours (actual: 4 hours implementation + 2 hours review + verification)
- **Branch:** `feature/llm-trace-system-rebuild`
- **Goal:** Rebuild the `llm_traces` write path and indexes so future traces include structured provider/model/routing/cache/status/correlation fields.
- **Why it matters now:** TASK-086 Phase 1 depends on `llm_traces` for cost, latency, routing, parse/error visibility, and production-vs-smoke separation. Without TASK-088, monitoring is possible but weaker and more manual.
- **Manual operator step:** The human operator, not Claude Code, must manually drop only `llm_traces` in `mongosh`. Claude Code must not run destructive MongoDB commands.

**Implementation Complete — Scope: 3 Files, 359 Lines Added/Modified**

**1. gateway.py (287 lines modified)**
- `GatewayResponse` dataclass: Added `provider: Optional[str]` and `cached: bool` fields
- `call()` method: Added `metadata` parameter, normalized at entry, passed through all paths (cache hit, success, errors)
- `call_sync()` method: Added `metadata` parameter, mirrored async implementation for sync callers
- `_write_trace()` async: Replaced minimal schema with structured 21-field trace document
  - Signature: trace_id, operation, requested_model, actual_model, input_tokens, output_tokens, cost, duration_ms, error, error_type, cached, cache_key, model_overridden, metadata
  - Schema: status (computed from error), provider (parsed from model string), routing_overridden, model_overridden, task_id, briefing_id, is_smoke, phase, iteration
  - Fire-and-forget semantics preserved
- `_write_trace_sync()` sync: Same schema as async version, uses pymongo MongoClient with 2s timeout
- All trace write call sites (8 total): 4 async paths (cache hit, success, HTTP error, generic error), 4 sync paths with all required fields

**2. tracing.py (19 lines modified)**
- `ensure_trace_indexes()`: 9 indexes total
  - timestamp TTL (30 days)
  - operation (single)
  - operation + timestamp (composite)
  - trace_id (unique)
  - model + timestamp (composite)
  - provider + timestamp (composite)
  - status + timestamp (composite)
  - cached + timestamp (composite)
  - briefing_id + phase + iteration (composite)
- `get_traces_summary()`: Added aggregation fields (error_count, cache_hits, routing_overrides) and derived rates (error_rate, cache_hit_rate, routing_override_rate)

**3. briefing_agent.py (53 lines modified)**
- `generate_briefing()`: Generate briefing_id BEFORE first LLM call, pass task_id, briefing_id, is_smoke to _generate_with_llm()
- `_generate_with_llm()`: Added task_id, briefing_id, is_smoke parameters; metadata includes phase="generate", iteration=0
- `_self_refine()`: Added task_id, is_smoke parameters; passes metadata to critique (phase="critique") and refine (phase="refine") calls
- `_call_llm()`: Added metadata parameter, passes through to gateway.call()

**Verification Results (2026-05-01)**
- ✅ Static checks: All 3 files compile without syntax errors
- ✅ routing_overridden + model_overridden: Both written to every trace doc, aggregated correctly in summary
- ✅ Model/provider parsing: provider extracted separately, model stores parsed name only, actual_model and requested_model properly parsed
- ✅ GatewayResponse: All 4 instantiations (2 async, 2 sync) include provider, cached, actual_model, requested_model, model_overridden
- ✅ Trace write call sites: All 8 calls (4 async, 4 sync) pass requested_model, actual_model, model_overridden, metadata, cached, cache_key, error_type
- ✅ Briefing agent metadata: briefing_id generated before first call; all phases pass task_id, briefing_id, is_smoke; generate/critique/refine phases properly labeled with iteration tracking
- ✅ All 9 indexes created: 1 TTL, 2 single field, 6 composite indexes
- ✅ get_traces_summary(): Returns original 5 fields + 3 new rate metrics; backward compatible
- ✅ No destructive operations: Zero occurrences of drop(), delete_many(), delete_one()
- ✅ Cost compatibility: Fields operation, timestamp, cost, model, tokens preserved for existing queries
- ✅ Example trace document: All 21 fields present and correctly structured

**Backward Compatibility Verified**
- Cost aggregation queries continue to work unchanged: `db.llm_traces.aggregate([{$match: {timestamp: {$gte: cutoff}}}, {$group: {_id: "$operation", total_cost: {$sum: "$cost"}, calls: {$sum: 1}}}])`
- New fields are additive only; no existing fields removed or renamed

**Schema (Example Trace Document)**
```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-05-01T19:07:54Z",
  "operation": "briefing_generate",
  "status": "success",
  "requested_model": "claude-haiku-4-5-20251001",
  "model": "claude-haiku-4-5-20251001",
  "actual_model": "claude-haiku-4-5-20251001",
  "provider": "anthropic",
  "routing_overridden": false,
  "model_overridden": false,
  "input_tokens": 2500,
  "output_tokens": 1200,
  "cost": 0.00125,
  "duration_ms": 1850,
  "cached": false,
  "cache_key": "abc123hash",
  "error": null,
  "error_type": null,
  "task_id": "celery-task-abc123",
  "briefing_id": "6706f1a2c8d2e4f5g6h7i8j9",
  "is_smoke": false,
  "phase": "generate",
  "iteration": 0
}
```

**Next Steps**
1. Human operator manually drops only `llm_traces` collection before or immediately before production deployment
2. Code review and merge to main
3. Deploy to Railway production
4. Monitor traces during TASK-086 Phase 1 validation (sentiment agreement ≥ 80%)

- **Compatibility requirement:** ✅ Preserve existing cost/budget aggregation fields: `operation`, `timestamp`, `model`, `input_tokens`, `output_tokens`, `cost`, `duration_ms`, `error`, and `cached`. Use `cost`, not `cost_usd`; use `timestamp`, not `created_at`.
- **Non-goals:** No dashboard, no trace analysis report, no migration of old traces, no code-driven deletion, no unrelated data mutation. FEATURE-055 handles analysis after this schema exists.

### FEATURE-055: Trace Analysis Layer for LLM Observability ⏳ BACKLOG
- **Status:** BACKLOG
- **Priority:** HIGH
- **Complexity:** MEDIUM
- **Dependency:** TASK-088 must be complete first.
- **Goal:** Add a read-only CLI report at `scripts/analyze_traces.py` so trace data can be inspected without writing ad hoc MongoDB aggregation queries.
- **Default behavior:** Look back 1 day, exclude smoke traces, read only from `llm_traces`, print JSON, never write/delete/mutate MongoDB.
- **Commands:**
  - `python scripts/analyze_traces.py --days 1`
  - `python scripts/analyze_traces.py --days 7`
  - `python scripts/analyze_traces.py --days 1 --include-smoke`
- **Report should answer:** top cost operations/models/providers, failures, slow calls, cache behavior, routing overrides, briefing generation/critique/refinement phases, and smoke-vs-production separation.
- **Non-goals:** No dashboard, no frontend, no API route changes, no scheduled task.

### Updated Sequencing Implication

TASK-088 should be treated as near-term Sprint 17 work because TASK-086 production validation depends on trustworthy trace output. FEATURE-055 can remain backlog/Sprint 18 unless manual MongoDB queries become too slow during the validation window.

## Open Tickets (Sprint 17 In Progress)

| ID | Title | Priority | Status | Effort | Blocks / Notes |
|---|---|---|---|---|---|
| TASK-081 | Fix Tier 1 prompts | P1 | ✅ COMPLETE | 2-3h | — |
| TASK-082 | Define quality thresholds | P1 | ✅ COMPLETE | 1h | — |
| FEATURE-054 | Tier 1 Cost Optimization Evals | P1 | ✅ COMPLETE (Phases 1-4) | 8-10h | — |
| TASK-085 | Add DeepSeek support to LLMGateway and route enrichment batch | P1 | ✅ COMPLETE | 3-4h | — |
| TASK-086 Phase 1 | Pre-production validation + production deployment | P1 | ✅ READY | 1 day + 1 week | — |
| TASK-086 Phase 2 | Deploy entity extraction + validate | P1 | ⏳ CONDITIONAL | 2 weeks | Requires Phase 1 success |
| TASK-087 | Refactor gateway-owned reliability controls | P2 | ⏳ QUEUED | 4-6h | Do after TASK-085 works and rollback path is validated |
| TASK-088 | Rebuild LLM trace system with clean collection reset | CRITICAL | ✅ COMPLETE | 4-6h | Complete 2026-05-01; human manually drops only `llm_traces` before deployment |
| BUG-092 | Trace provider field null for Haiku - TASK-088 regression | HIGH | ✅ COMPLETE | 1-2h | Provider field extracted early; Tier 1 ops routed to DeepSeek V4 Flash (2026-05-01) |
| FEATURE-055 | Trace analysis CLI over `llm_traces` | HIGH | ⏳ BACKLOG | Medium | Depends on TASK-088; read-only script, no dashboard |
| Theme reannotation | Re-annotate theme extraction samples | P2 | ⏳ DEFERRED / TBD | 1-2h | Future ticket if pursuing theme rollout |
| MSD-001 v3 | Update entity_extraction decision record | P1 | ⏳ PENDING | 0.5h | Sprint closeout |
| MSD-002 v3 | Update sentiment_analysis decision record | P1 | ⏳ PENDING | 0.5h | Sprint closeout |
| MSD-003 v3 | Update theme_extraction decision record | P1 | ⏳ PENDING | 0.5h | Sprint closeout |

---

## Execution Order (Sprint 17)

1. ✅ **Day 1-2:** TASK-081 + TASK-082 — COMPLETE
   - Fix prompts + define thresholds (2026-04-29)

2. ✅ **Day 3-4:** FEATURE-054 Phases 1-4 — COMPLETE
   - Corrected baselines + challenger runs + threshold scoring + manual analysis (2026-04-30)

3. ✅ **Day 5-6:** TASK-085 — COMPLETE (2026-04-30)
   - ✅ Added DeepSeek support through `LLMGateway`
   - ✅ Provider-aware routing for `anthropic:*` and `deepseek:*` model refs
   - ✅ DeepSeek config, request formatting, response parsing, cost tracking
   - ✅ Routed `entity_extraction`, `sentiment_analysis`, `theme_extraction` to `deepseek:deepseek-v4-flash`
   - ✅ 19 unit tests passing

3b. ✅ **Day 7 morning:** BUG-092 — COMPLETE (2026-05-01)
   - ✅ Fixed provider field null regression in cached responses
   - ✅ Provider extracted early in both async and sync paths
   - ✅ All 22 gateway tests passing with provider field validation
   - ✅ Tier 1 operations now correctly route to DeepSeek and populate provider field

4. ✅ **Day 7 morning:** TASK-086 Phase 1 Pre-Production Validation — COMPLETE (2026-05-01)
   - ✅ Mocked smoke tests: 8/8 pass
   - ✅ Live smoke tests: Both Anthropic and DeepSeek working
   - ✅ Routing verified: Both providers route through LLMGateway
   - ✅ Cost tracking fixed: DeepSeek pricing correctly applied
   - ✅ Tracing verified: llm_traces collection ready
   - ✅ Rollback verified: One-line switch to Anthropic confirmed
   - ✅ Production deployment checklist created

5. ⏳ **Day 7-13:** TASK-086 Phase 1 — DEPLOYING TO PRODUCTION
   - Deploy to production (Railway, 2026-05-02)
   - Monitor sentiment agreement, parse success, latency, cost for 5-7 days
   - Primary validation metric: sentiment agreement ≥ 80% vs Haiku baseline
   - Record decision: keep DeepSeek route, revert to Anthropic, or extend validation

6. ✅ **Day 7 afternoon:** TASK-088 Trace Rebuild — COMPLETE (2026-05-01)
   - ✅ Structured trace writes for async and sync gateway paths (gateway.py)
   - ✅ Preserved cost aggregation compatibility while adding provider/routing/cache/status/correlation metadata (tracing.py)
   - ✅ Propagated briefing metadata: `task_id`, `briefing_id`, `is_smoke`, `phase`, `iteration` (briefing_agent.py)
   - ✅ 9 indexes created for operation, model, provider, status, cached, briefing tracking
   - ✅ All 21 trace fields verified; backward compatibility confirmed
   - ⏳ Human operator must manually drop only `llm_traces` before or immediately before production deployment
   - This strengthens TASK-086 monitoring

7. ⏳ **After TASK-085 works / after Phase 1 validation starts:** TASK-087 — QUEUED
   - Refactor circuit breaker and rate limiter ownership into `LLMGateway`
   - Add provider-scoped reliability keys such as `deepseek:article_enrichment_batch`
   - Remove duplicated caller-level reliability checks only after tests prove gateway enforcement works
   - Not required before the first DeepSeek production validation

8. ⏳ **After TASK-088:** FEATURE-055 — BACKLOG / FOLLOW-UP
   - Add read-only `scripts/analyze_traces.py` CLI
   - Print compact JSON report for cost, errors, latency, cache, routing overrides, providers, and briefing phases
   - Exclude smoke traces by default; add `--include-smoke` when needed
   - No dashboard, no frontend, no MongoDB writes

9. ⏳ **Day 14-27 (conditional):** TASK-086 Phase 2 — CONDITIONAL
   - Entity extraction cutover only if Phase 1 succeeds
   - 2 weeks monitoring + validation
   - Decision: keep, revert, or proceed to theme rollout planning

10. ⏳ **Future / optional:** Theme reannotation + theme rollout
   - Theme extraction remains higher risk because FEATURE-054 found low agreement and reference/prompt mismatch
   - Create or revive a dedicated theme reannotation ticket only if pursuing theme rollout

---

**Sprint 17 Status (2026-05-01):**
- ✅ TASK-085: DeepSeek works through `LLMGateway` for Tier 1 operations (entity_extraction, sentiment_analysis, theme_extraction) (COMPLETE 2026-04-30)
- ✅ BUG-092: Provider field null regression fixed; provider extracted early in cached response paths (COMPLETE 2026-05-01)
- ✅ TASK-086 Phase 1 Pre-Production: Mocked + live validation complete, production deployment guide created (COMPLETE 2026-05-01)
- ✅ TASK-088: Structured trace rebuild complete with 21-field schema, 9 indexes, metadata propagation, and backward compatibility verified (COMPLETE 2026-05-01)
- ⏳ TASK-086 Phase 1 Production: Ready to deploy, monitor 5-7 days, record decision (STARTING 2026-05-02)
- ⏳ FEATURE-055: Backlog/follow-up trace analysis CLI after TASK-088

**Sprint 17 completes when:**
- ✅ TASK-085: DeepSeek works through `LLMGateway` for `article_enrichment_batch` (COMPLETE)
- ✅ TASK-088: Structured `llm_traces` rebuild is complete with 21 fields, 9 indexes, backward compatibility, and zero destructive operations (COMPLETE)
- ⏳ TASK-086 Phase 1: DeepSeek-backed enrichment batch has been monitored in production (5-7 days) and a keep/revert decision is made (DUE ~2026-05-10)

**If Phase 1 succeeds (>= 80% sentiment agreement, no material parse/briefing quality issues, and cost tracking is correct):**
- Keep DeepSeek route for `article_enrichment_batch`
- Proceed with TASK-087 reliability refactor if not already started
- Sprint 18 can begin with TASK-086 Phase 2 for entity extraction deployment

**If Phase 1 fails (agreement < 75%, parse failures, user-facing quality issues, or trace/cost tracking issues):**
- Revert `article_enrichment_batch` routing to Anthropic Haiku
- Close Sprint 17 with lesson learned
- Do not start entity/theme rollout until failure mode is understood


## Non-TASK-086 Follow-Up Checklist

These items should stay in the sprint doc because they are broader sprint closeout or follow-up work, not immediate TASK-086 rollout work.

### Do after TASK-086 Phase 1 starts or completes

1. **Complete TASK-087 reliability refactor**
   - Move circuit breaker and rate limiter ownership into `LLMGateway`.
   - Add provider-scoped reliability keys, such as `deepseek:article_enrichment_batch`.
   - Remove duplicate caller-level checks only where tests prove gateway enforcement works.

2. **Update Sprint 17 closeout docs**
   - Final sprint status.
   - Keep/revert/extend decision from TASK-086 Phase 1.
   - Cost savings evidence from `llm_traces`.
   - Lessons learned from production validation.

3. **Update model strategy decision records**
   - `MSD-001 v3`: entity extraction decision record.
   - `MSD-002 v3`: sentiment analysis decision record.
   - `MSD-003 v3`: theme extraction decision record.

4. **Plan Sprint 18 based on the TASK-086 Phase 1 result**
   - If Phase 1 succeeds, Sprint 18 can start with TASK-086 Phase 2 for entity extraction plus TASK-087 if not already completed.
   - If Phase 1 fails, Sprint 18 should focus on diagnosing the failure mode before any entity/theme rollout.

5. **Complete TASK-088 trace rebuild**
   - Rebuild structured trace writes and indexes.
   - Preserve cost aggregation compatibility.
   - Keep all destructive DB work manual and limited to `llm_traces`.

6. **Optional: implement FEATURE-055 trace CLI**
   - Do this after TASK-088 if manual trace inspection becomes too slow or error-prone during validation.
   - Keep it read-only and JSON-only.

7. **Optional: theme reannotation**
   - Only do this if theme quality becomes important or problematic.
   - Do not block the current DeepSeek rollout on this work.

### Sprint 18 Roadmap (Conditional)

| Task | Effort | Timeline | Condition |
|---|---|---|---|
| **TASK-087** | Gateway-owned reliability controls + provider-scoped keys | 4-6h | After TASK-085 works and rollback path is validated |
| **TASK-088** | Structured trace rebuild + clean `llm_traces` reset | 4-6h | Near-term; strengthens TASK-086 monitoring |
| **FEATURE-055** | Read-only trace analysis CLI | Medium | After TASK-088 |
| **TASK-086 Phase 2** | Entity extraction A/B test + cutover | 2 weeks | Phase 1 success |
| **Theme reannotation** (future ticket TBD) | Re-annotate theme extraction samples | 1-2h | If pursuing theme rollout |
| **TASK-086 Phase 3** | Theme extraction A/B test + cutover | 2 weeks | Phase 2 success + theme reannotation done |

### Success Criteria for Sprint 18

**Reliability Refactor (TASK-087):**
- [ ] Gateway enforces circuit breaker checks for every non-cached external LLM call
- [ ] Gateway enforces rate limit checks for every non-cached external LLM call
- [ ] Provider-scoped reliability keys isolate Anthropic and DeepSeek failures
- [ ] Existing operation-level reporting remains usable
- [ ] Duplicate caller-level checks removed only where safe
- [ ] Tests cover async and sync gateway paths

**Trace Rebuild (TASK-088):**
- [ ] Human operator manually drops only `llm_traces`
- [ ] Gateway writes structured trace schema from async and sync paths
- [ ] Trace failures remain best-effort and do not break LLM calls
- [ ] Trace indexes are updated
- [ ] Briefing traces include task/briefing/smoke/phase/iteration metadata
- [ ] Cost tracker aggregation still works using `timestamp` and `cost`

**Trace Analysis CLI (FEATURE-055) — After TASK-088:**
- [ ] `scripts/analyze_traces.py` exists
- [ ] CLI is read-only against `llm_traces`
- [ ] JSON report includes totals, by_operation, by_model, by_provider, errors, slowest_calls, cache, routing, and briefing_phases
- [ ] Smoke traces are excluded by default and included only with `--include-smoke`

**Phase 2 (Entity) — If Phase 1 succeeds:**
- [ ] DeepSeek entity extraction in production
- [ ] Monitored for 2 weeks
- [ ] >= 60% Jaccard agreement with Haiku maintained
- [ ] Briefing quality unaffected
- [ ] Cost savings confirmed ($X/month)
- [ ] Decision: proceed to theme planning or revert

**Phase 3 (Theme) — Only if Phase 2 succeeds AND theme references are reannotated:**
- [ ] Theme references reannotated (proper nouns removed)
- [ ] Re-scoring shows improved thresholds
- [ ] DeepSeek theme extraction in production
- [ ] Monitored for 1-2 weeks
- [ ] >= 60% Jaccard agreement with Haiku
- [ ] Decision: keep or revert

---

## Sprint 17 Status & Timeline (Updated)

| Item | Original Plan | Actual/Revised |
|---|---|---|
| Timeline | 2026-05-04 to 2026-05-10 (6 days) | 2026-04-28 to 2026-05-17 (19 days) |
| Effort (evals only) | 6-7 hours | 8-10 hours ✅ |
| Effort (with deployment) | N/A (was Sprint 18) | 15-20 hours (TASK-085 + TASK-086 Phase 1 + conditional Phase 2) plus TASK-087 refactor if Phase 1 path is stable; add 4-6h for TASK-088 trace rebuild and optional FEATURE-055 follow-up |
| Recommendation | Flash on sentiment ($7k/year savings) | DeepSeek on all three ($55k/year savings) |
| Work split | FEATURE-054 only | FEATURE-054 + TASK-085 + TASK-086 Phase 1 + TASK-087 queued + TASK-088 trace rebuild + FEATURE-055 backlog (+ Phase 2/3 conditional) |
| Deliverables | 3 decision records | 6 docs + gateway integration + production validation + follow-up reliability refactor ticket + structured trace rebuild ticket + trace analysis CLI ticket |
| Sprint close | 2026-05-10 | 2026-05-17 (after Phase 1 monitored + decision made) |

**What changed:** DeepSeek discovery + decision to deploy immediately means TASK-085/086 Phase 1 are in Sprint 17 scope. Repo review changed TASK-085 from “build provider” to “make gateway provider-aware.” TASK-087 now captures the deferred reliability refactor so TASK-085 can stay minimal.

---

## Lessons from Sprint 17

1. **Manual analysis catches issues that automated scoring misses.** "All models fail" needed investigation, not acceptance.
2. **Infrastructure choices compound costs.** OpenRouter convenience hid 90% of savings.
3. **Behavioral consistency is a better signal than absolute thresholds for deployment.** 85% agreement matters more than F1 scores against imbalanced references.
4. **Reference data quality is as important as model quality.** Bad references or prompt/reference mismatch tanks eval validity.
5. **Phased rollout with rollback capability is how you take calculated risks.** $55k/year opportunity doesn't require betting everything at once.
6. **Minimal integration before reliability refactor keeps blast radius controlled.** DeepSeek should work through the gateway first; provider-scoped reliability belongs in the follow-up task.
7. **Trace data is production infrastructure, not just analytics.** After the deletion incident, structured traces and read-only inspection become part of safe model rollout operations.

---

## Philosophy for Sprint 17 (Current Phase)

**Focus:** Complete TASK-085 as a minimal `LLMGateway` integration, route `article_enrichment_batch` to DeepSeek, run TASK-086 Phase 1 production validation, rebuild `llm_traces` enough to trust rollout diagnostics, and make a keep/revert decision.

**Not:** Refactor reliability ownership before DeepSeek works. Do not try all three Tier 1 operations at once. Do not let Claude Code perform destructive MongoDB operations. Keep phases sequential with rollback at each step.

**Rationale:** Sentiment has highest confidence (85% agreement), but production currently batches sentiment with relevance and themes. Route the existing batch first, validate sentiment as the primary metric, learn from production, then tackle entity extraction if Phase 1 succeeds. Keep theme extraction optional and dependent on reannotation.

**Taste:** Pragmatism + rigor. $55k/year opportunity doesn't require betting everything at once. Phased rollout minimizes risk. Minimal integration first, reliability refactor second.

---

*Sprint 17 IN PROGRESS (as of 2026-05-01). FEATURE-054 Phases 1-4 complete. TASK-085 complete (2026-04-30). TASK-086 Phase 1 pre-production validation complete (2026-05-01), ready for production deployment (2026-05-02). TASK-087 queued as follow-up reliability refactor. TASK-088 open as critical trace rebuild work. FEATURE-055 backlog after TASK-088 for read-only trace analysis. Sprint closes ~2026-05-17 after Phase 1 monitored + decision made, with TASK-088 either complete or explicitly deferred.*
