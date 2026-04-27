# Sprint 16 — Model Routing Observable + Tier 1 Flash Evaluations

**Status:** NOT STARTED  
**Target Start:** 2026-04-27  
**Target End:** 2026-05-03  
**Sprint Goal:** Make model routing observable and deterministic, wire multi-model provider support, and complete Tier 1 Flash evaluations against a golden set (3 operations, 2-3 decision records with data-driven outcomes).

---

## Context from Sprint 15

Sprint 15 stabilized cost tracking and enforcement across all 14 LLM operations. True daily spend is ~$0.54, well under the $1.00 hard limit. Cost dashboard and Slack alerts are wired. 

Key finding: `narrative_generate` has **0% cache hit rate** despite being the second-largest cost driver ($6.64/month). This is gated for investigation in Sprint 16 (TASK-075) but explicitly NOT in evaluation scope unless cache is unfixable.

Current blocker for multi-model testing: model routing is hard-coded and not observable. **BUG-090 tears out the old system entirely and introduces RoutingStrategy as foundation.** TASK-076 completes the implementation with deterministic A/B bucketing. Without this, Flash evaluations cannot run.

---

## Priority 1 — Model Routing + Provider Abstraction (Required Before Evals)

### BUG-090: Eliminate Silent Model Override — Introduce Observable Routing ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** CRITICAL
- **Effort:** 2-3 hours (actual: ~2 hours)
- **Goal:** **Tear out old `_OPERATION_MODEL_ROUTING` dict entirely.** Introduce `RoutingStrategy` skeleton as observable foundation for future variant routing. ✅ DONE
- **Implementation:** 
  - ✅ Deleted entire `_OPERATION_MODEL_ROUTING` dict
  - ✅ Added `RoutingStrategy` class with `resolve_model(requested)` → (actual_model, overridden: bool)
  - ✅ Implemented `_get_routing_strategy(operation)` with all 14 operations + graceful fallback for unknown ops
  - ✅ Updated `GatewayResponse` with `actual_model`, `requested_model`, `model_overridden` fields
  - ✅ Integrated into both `call()` and `call_sync()` methods
  - ✅ All overrides logged with operation + requested + actual for debugging
  - ✅ Updated test suite (2 tests modified, all 22 gateway tests pass)
- **Branch:** `fix/bug-090-eliminate-silent-model-override` (commit e89dc44)
- **PR:** Ready to merge
- **Blocks:** ✅ UNBLOCKED TASK-076, FEATURE-053

---

### TASK-076: RoutingStrategy Implementation — Complete + Wire Routing Into Gateway ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** CRITICAL
- **Effort:** 3-4 hours (actual: 1.5 hours)
- **Dependency:** BUG-090 ✅ merged first
- **Goal:** ✅ Complete `RoutingStrategy` with deterministic MD5 bucketing; wire into gateway for A/B testing
- **Implementation:** 
  - ✅ Added `RoutingStrategy.select(routing_key)` method with:
    - Guard clause: `if not self.variant or self.variant_ratio == 0: return self.primary`
    - MD5 hash bucketing: hash_int = int(md5(routing_key).hexdigest(), 16) % 100
    - Split point: int(self.variant_ratio * 100)
    - Return variant if hash_int < split_point else primary
  - ✅ Created `_OPERATION_ROUTING` dict with all 14 operations; all primary=Haiku, no variants yet
  - ✅ Updated `_get_routing_strategy()` to use `_OPERATION_ROUTING` (raises ValueError for unknown ops)
  - ✅ Updated `gateway.call()` and `call_sync()` to accept `routing_key` parameter (default: f"{operation}:{trace_id}")
  - ✅ Both methods now call `strategy.select(routing_key)` and `strategy.resolve_model()`
  - ✅ Model strings enforced as "provider:model_name" format
  - ✅ `GatewayResponse.actual_model`, `requested_model`, `model_overridden` all populated
  - ✅ Cost tracking uses `actual_model`
- **Testing:**
  - ✅ Determinism: same routing_key → same output (test_select_deterministic PASSED)
  - ✅ Guard clause: variant=None → always primary (test_guard_clause_none_variant PASSED)
  - ✅ Guard clause: ratio=0 → always primary (test_guard_clause_zero_ratio PASSED)
  - ✅ A/B split: 50 calls with ratio=0.5 → 40-60 split (test_select_50_50_split PASSED)
  - ✅ All 22 existing gateway tests pass (zero regressions)
  - ✅ Total: 39 tests passing (22 existing + 17 new)
- **Branch:** `fix/bug-090-eliminate-silent-model-override` (commit 713358f)
- **PR:** Ready for merge
- **Unblocks:** ✅ FEATURE-053 (Flash evaluations now have deterministic routing foundation)

---

### TASK-077: GeminiProvider Implementation — Stub + Factory Integration ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** CRITICAL
- **Effort:** 3-4 hours (actual: 1 hour)
- **Goal:** ✅ Create `GeminiProvider` class and wire into provider factory; return contract documented
- **Implementation:** 
  - ✅ Created `src/crypto_news_aggregator/llm/gemini.py` (151 lines)
  - ✅ `GeminiProvider` class inheriting from `LLMProvider`
  - ✅ Constructor: `__init__(api_key)` with ValueError validation ✅
  - ✅ All abstract methods implemented with NotImplementedError (Sprint 17 deferred)
  - ✅ `call()` method with comprehensive docstring documenting exact return shape
  - ✅ Updated `factory.py`:
    - Added GeminiProvider import
    - Added `"gemini": GeminiProvider` to PROVIDER_MAP
    - Updated `get_llm_provider(name)` function signature (optional provider name parameter, backward compatible)
    - Added gemini branch with GEMINI_API_KEY lookup
  - ✅ Updated `config.py`:
    - Added Field import
    - Added `GEMINI_API_KEY: Optional[str]` field with env var mapping
- **Testing:**
  - ✅ 15 new unit tests all passing (test_gemini_provider.py)
  - ✅ `get_llm_provider("gemini")` returns GeminiProvider instance ✅
  - ✅ `GeminiProvider` raises ValueError if api_key empty ✅
  - ✅ `GeminiProvider.call()` raises NotImplementedError ✅
  - ✅ All existing tests pass (no regression) ✅
  - ✅ Total: 39 gateway tests + 15 gemini tests = 54 passing
- **Branch:** `feat/task-077-gemini-provider` (commit a63fc16)
- **PR:** Ready for merge
- **Unblocks:** ✅ FEATURE-053 (GeminiProvider now available for routing)

---

## Priority 2 — Decision Framework (Required For Evals Framing)

### TASK-078: Model Selection Rubric — Write Decision Framework Document
- **Status:** OPEN
- **Priority:** HIGH
- **Effort:** 2-3 hours
- **Goal:** Write generalizable framework for model selection decisions; becomes interview material and template for future model choices
- **Deliverable:** `docs/model-selection-rubric.md` with:
  - **Section 1:** Operation classification (5 types: Extraction, Synthesis, Critique, Polish, Agentic)
  - **Section 2:** Decision dimensions (5 axes: Quality Requirement, Volume, Latency Sensitivity, Determinism, Failure Cost)
  - **Section 3:** Tiering rules (Tier 0/1/2/3 with criteria, Flash strategy per tier)
    - Tier 1: High volume + deterministic + low failure cost (aggressive Flash testing)
    - Tier 2: Medium volume + generation + user-facing (cautious testing)
    - Tier 3: Low volume + reasoning required + safety-critical (no testing)
  - **Section 4:** Override conditions (when to break default tier assignment)
  - **Section 5:** Model selection algorithm (step-by-step for any new operation)
  - **Section 6:** Interview positioning notes
- **Testing:** Rubric is readable one-pager; all 14 operations can be classified using it
- **Branch:** Not a code change; document only
- **Next:** Complete before TASK-079; reference in FEATURE-053 decision records

---

### TASK-079: Operation Tier Mapping — Classify All 14 Operations
- **Status:** OPEN
- **Priority:** HIGH
- **Effort:** 2-3 hours
- **Dependency:** TASK-078 must exist first
- **Goal:** Classify all 14 LLM operations into tiers using the rubric; determines evaluation scope and priority
- **Deliverable:** `docs/operation-tiers.md` with:
  - Classification table for all 14 operations (operation, type, tier, rationale)
  - Summary by tier (which ops in each tier)
  - **Flash Evaluation Priority:**
    - **Phase 1 (Tier 1, Aggressive):** entity_extraction, sentiment_analysis, theme_extraction, actor_tension_extract, relevance_scoring (5 ops total)
    - **Phase 2 (Tier 2, Cautious):** narrative_generate (if cache miss confirmed), narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation
    - **Phase 3 (Tier 3, Deferred):** briefing_generate, briefing_critique, briefing_refine, provider_fallback (no testing)
  - **SPRINT 16 SCOPE NOTE:** "Sprint 16 evaluates **subset** of Tier 1 (3 ops: entity_extraction, sentiment_analysis, theme_extraction) due to time constraints. Full Tier 1 (5 ops) and Tier 2 evals deferred to Sprint 17+"
  - Decision gate: TASK-075 narrative_generate cache fix determines whether to include narrative_generate in later phases
- **Testing:** Each operation has clear rationale; rubric criteria applied consistently
- **Branch:** Not a code change; document only
- **Note:** SPRINT 16 EXPLICITLY LIMITS FEATURE-053 TO 3 OPS (subset of 5 Tier 1 operations)
- **Next:** Complete before FEATURE-053 Phase 1 starts; determines execution order

---

## Priority 3 — Enablement + Investigation

### TASK-074: Helicone Setup — Proxy + Kill Switch Configuration
- **Status:** OPEN
- **Priority:** MEDIUM
- **Effort:** 2-3 hours
- **Goal:** Add Helicone proxy integration for trace visibility during Anthropic calls; toggle via env var
- **Key Note (from Feedback):** **Helicone only traces Anthropic calls.** Gemini calls via GeminiProvider will NOT appear in Helicone dashboards. This is expected and acceptable (separate observability for Gemini is out of scope).
- **Changes Required:**
  - Add `USE_HELICONE_PROXY: bool = False` to `config.py` (env var, default off)
  - Add `HELICONE_API_KEY: Optional[str] = None` to `config.py` (env var)
  - Implement `_get_anthropic_url()` in `gateway.py` to return proxy URL if enabled
  - Update `_build_headers()` to add `Helicone-Auth` header when proxy enabled
  - Verify no performance degradation when proxy disabled
- **Testing:**
  - Gateway works with proxy disabled (baseline)
  - Gateway works with proxy enabled (requires valid key)
  - Helicone dashboard receives traces when enabled
  - No header leakage when proxy disabled
- **Branch:** `feat/task-074-helicone-setup`
- **Note:** Optional for Sprint 16; prioritize if eval debugging needs are high. Not blocking FEATURE-053.
- **Next:** Optional completion; can be deferred if time is tight

---

### TASK-075: Narrative Cache Investigation — Root Cause Analysis & Fix Proposal
- **Status:** OPEN
- **Priority:** CRITICAL
- **Effort:** 4-6 hours
- **Goal:** Determine why `narrative_generate` has 0% cache hit rate; propose fix or accept as-is
- **Phases:**
  - **Phase 1 (Investigation):**
    - Verify cache is enabled for narrative_generate in `CACHEABLE_OPERATIONS` list
    - Query `llm_cache` collection for narrative_generate entries
    - Run aggregation on `llm_traces`: group by input_hash, count duplicates
    - Root cause analysis: unique inputs vs. excluded operation vs. hashing issue
  - **Phase 2 (Solution Design):**
    - Propose architecture (normalized input caching, re-enable, deterministic serialization)
    - Estimate cache hit improvement (if fixed)
    - Project cost savings ($X/month if implemented)
    - Document tradeoffs and risks
- **Decision Gate (Required Before Tier 2 Evals):**
  - Option A: Root cause is fixable → design solution, estimate benefit
  - Option B: Root cause is unfixable → accept as-is, confirm Flash swap justified
  - Option C: Working as intended → document why excluded
- **Deliverable:** `docs/decisions/NARRATIVE_CACHE_FIX.md` with root cause, proposed solution, cost impact
- **Branch:** `feature/narrative-cache-investigation`
- **Note:** **SPRINT 16 DOES NOT INCLUDE NARRATIVE_GENERATE IN FLASH EVALS.** This investigation runs in parallel; results inform Sprint 17 decisions.
- **Next:** Complete before sprint end; gate any Tier 2 decisions on findings

---

## Priority 4 — Tier 1 Flash Evaluations (Main Feature, Scoped)

### FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set
- **Status:** OPEN
- **Priority:** CRITICAL
- **Effort:** 6-8 hours (Phases 1-2 only; Tier 1 operations only)
- **Dependencies:**
  - BUG-090 merged (routing observable)
  - TASK-076 merged (RoutingStrategy wired)
  - TASK-077 merged (GeminiProvider available)
  - TASK-078 complete (rubric for framing)
  - TASK-079 complete (tier assignments)
- **Scope (EXPLICIT LIMITS):**
  - **Tier 1 Operations ONLY (3 operations, subset of 5 Tier 1 ops):**
    - `entity_extraction`
    - `sentiment_analysis`
    - `theme_extraction`
  - **NOT in Sprint 16:**
    - Other Tier 1 ops (actor_tension_extract, relevance_scoring)
    - Tier 2 operations (narrative_generate, narrative_theme_extract, etc.)
    - Full rollout decisions
    - Production swaps
- **Phases (Tier 1 only):**
  - **Phase 1: Extract Golden Set**
    - Load 50-100 samples per operation from `briefing_drafts` collection (last 7-14 days)
    - Schema: operation, input_id, input_text, articles[], timestamp, haiku_output{}
    - Include edge cases (long inputs, multiple articles)
  - **Phase 2: Baseline from Existing Haiku Outputs (OPTIMIZED)**
    - **KEY OPTIMIZATION (from Feedback):** Use existing `haiku_output` from golden set as baseline if available + valid
    - Only re-run Haiku if missing or inconsistent
    - Saves ~3-4 hours of unnecessary API calls
    - Collect: latency (p50, p95 ms), cost, input/output tokens, output text
    - Track source: "historical" (from golden set) vs. "recomputed" (fresh run)
  - **Phase 3: Run Flash Variant**
    - Set RoutingStrategy.variant = "gemini:gemini-2.5-flash", variant_ratio = 1.0
    - Run same golden set inputs through gateway
    - Collect same metrics as Phase 2
  - **Phase 4: Compare & Score**
    - Quality scoring:
      - Tier 1 (extraction): exact match or overlap score (0-100)
      - Regression threshold: >5% of samples show quality drop
    - Build comparison table (model, quality, cost/1k, p50, p95 latency)
  - **Phase 5: Produce Data-Driven Decision Records**
    - Write 2-3 decision records (MSD-001, MSD-002, MSD-003) minimum
    - Format: `docs/decisions/MSD-XXX-operation.md`
    - **CRITICAL (from Feedback):** Decisions must be data-driven; no forced outcomes
      - SWAP if cost reduction is significant AND no material quality loss
      - STAY if quality regression exceeds threshold
      - CONDITIONAL if tradeoffs depend on context
    - Each record includes: operation, metrics, **data-driven decision**, rationale, override conditions, rollout plan
- **Success Criteria for Sprint 16:**
  - [ ] Golden set extracted: 50-100 samples per operation (3 ops)
  - [ ] **Phase 2 optimization applied:** existing haiku_output used where available
  - [ ] Haiku baseline collected: latency, cost, output for all samples
  - [ ] Flash variant run: same metrics, real API calls (or deterministic mock if key unavailable)
  - [ ] Comparison table: Model | Quality | Cost/1k | p50ms | p95ms
  - [ ] Quality regression detected and flagged if >5%
  - [ ] 2-3 decision records written (MSD-001+)
  - [ ] **Decisions are data-driven (no pressure to force "SWAP" outcomes)**
  - [ ] Golden set definition documented (reproducible)
  - [ ] Eval methodology documented (quality scoring rules, regression threshold)
- **Interview Value:**
  - Decision records become talking points: "Here's how we evaluated Haiku vs. Flash"
  - Demonstrates systematic, data-driven cost-quality reasoning
  - Shows rigor in model selection process
  - Shows confidence in decision framework (not result-oriented)
- **Branch:** `feat/feature-053-tier1-flash-evals`
- **Note:**
  - Real Gemini API calls preferred if key available; deterministic mock acceptable
  - Phase 3 may raise NotImplementedError from GeminiProvider if deferred to Sprint 17; that's acceptable if mock is substituted
  - Do NOT attempt other Tier 1 ops or Tier 2 operations in this sprint
  - Do NOT plan production rollouts; decision records are for decision-making, not deployment
- **Next:** Start after all Priority 1/2 tickets merge; execute Phases 1-5 sequentially

---

## Success Criteria (Outcome-Based)

✅ **Model routing is observable and deterministic**
- [x] BUG-090 complete: `GatewayResponse` includes actual_model, requested_model, model_overridden fields
- [x] TASK-076 complete: `RoutingStrategy` class exists with deterministic MD5 bucketing verified (commit 713358f)
- [x] Guard clause verified: variant=None or ratio=0 → always primary (test_guard_clause_none_variant PASSED)
- [x] Same routing_key → same output verified (test_select_deterministic PASSED)
- [x] A/B split test passes: variant_ratio=0.5 → 40-60 split (test_select_50_50_split PASSED)

✅ **Provider abstraction supports multi-model routing**
- [x] TASK-077 complete: `GeminiProvider` exists and is wired in factory.py (commit a63fc16)
- [x] `get_llm_provider("gemini")` returns instance without error (with key set) ✅
- [x] `get_llm_provider("gemini")` raises ValueError if key not set ✅
- [x] **Return contract documented:** GeminiProvider.call() matches AnthropicProvider response shape ✅
- [x] Model string format "provider:model_name" enforced across gateway (TASK-076) ✅

✅ **Decision framework documents systematic model selection**
- [ ] TASK-078 complete: `docs/model-selection-rubric.md` written, one-pager + tables
- [ ] TASK-079 complete: `docs/operation-tiers.md` with all 14 ops classified
- [ ] Tier 1 classification matches rubric (high volume + deterministic)
- [ ] Sprint 16 scope note in TASK-079: "subset of 5 Tier 1 ops (3 ops for time constraints)"

✅ **Tier 1 Flash evaluation completed with data-driven outcomes**
- [ ] Golden set created: 50-100 samples per operation (3 ops)
- [ ] **Phase 2 optimization applied:** baseline from existing haiku_output where possible
- [ ] Haiku baseline collected: latency, cost, quality metrics
- [ ] Flash comparison run: same metrics on Gemini 2.5 Flash
- [ ] Comparison table produced: Model | Quality | Cost/1k | p50ms | p95ms
- [ ] Quality regression analyzed: flag any >5% drop
- [ ] 2-3 Decision records written (MSD-001+)
- [ ] **Decisions are data-driven (no forced "SWAP" or "STAY" outcomes)**
- [ ] Eval methodology documented: quality scoring rules, regression threshold

✅ **Narrative cache investigation complete and gates Tier 2**
- [ ] TASK-075 root cause documented: unique inputs / excluded / hashing issue
- [ ] Decision recorded: fixable / unfixable / working as intended
- [ ] Cost impact projection included (if fixable)
- [ ] Explicitly gates Tier 2 ops from Sprint 16 scope

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| BUG-090 / TASK-076 merge conflicts in gateway.py | Medium | Medium | Do sequentially (not parallel); test both in same PR review; same files require care |
| Gemini API key not available, mock not deterministic | Medium | Medium | Use deterministic mock at GeminiProvider level (same input → same output); acceptable for eval purposes |
| RoutingStrategy guard clause off-by-one bug | Low | High | Unit test variant=None, ratio=0, and ratio=0.5 edge cases before merging |
| Flash cost wildly higher than expected | Low | Medium | Tier 1 ops are low-failure-cost; can revert to Haiku without impact; decision records document surprises |
| FEATURE-053 scope creep (pressure to add Tier 2 mid-sprint) | High | High | Explicitly document "3 ops, Tier 1 ONLY" in sprint goal; defer all Tier 2 discussion to Sprint 17 |
| Cache investigation discovers major refactoring needed | Low | Medium | TASK-075 is parallel (not blocking); findings gate Tier 2 decisions, not Tier 1 evals |
| Golden set size too small | Low | Low | Baseline is 50 samples per op; can increase to 100 if data available in 7-14 day window |
| Phase 2 optimization fails (no haiku_output in golden set) | Low | Medium | Fall back to re-running Haiku baseline; adds ~3-4 hours but doesn't block evals |

---

## Open Tickets

| ID | Title | Priority | Status | Effort | Blocks |
|---|---|---|---|---|---|
| BUG-090 | Model routing observable (tear out old, introduce RoutingStrategy) | P1 | ✅ COMPLETE | 2h | UNBLOCKED |
| TASK-076 | RoutingStrategy completion + wiring (with guard clause) | P1 | ✅ COMPLETE | 1.5h | UNBLOCKED |
| TASK-077 | GeminiProvider stub + factory integration (return contract) | P1 | ✅ COMPLETE | 1h | UNBLOCKED |
| TASK-078 | Model Selection Rubric (5-tier framework) | P2 | OPEN | 2-3h | TASK-079, framing |
| TASK-079 | Operation Tier Mapping (all 14 ops + scope note) | P2 | OPEN | 2-3h | FEATURE-053 priority |
| TASK-074 | Helicone Setup (proxy + kill switch, Anthropic-only) | P3 | OPEN | 2-3h | Optional |
| TASK-075 | Narrative Cache Investigation (gates Tier 2) | P3 | OPEN | 4-6h | Sprint 17 (parallel) |
| FEATURE-053 | Flash Evaluations (Tier 1 only, 3 ops, data-driven decisions) | P4 | OPEN | 6-8h | All P1/P2 tickets |

---

## Execution Order (Dependencies Respected)

1. **Day 1-2:** BUG-090 (tear out old routing, introduce RoutingStrategy skeleton)
2. **Day 2-3:** TASK-076 (complete + wire RoutingStrategy with guard clause)
3. **Day 1-3 (parallel):** TASK-077 (GeminiProvider with return contract)
4. **Day 2-3 (parallel):** TASK-078 (write rubric)
5. **Day 3 (after TASK-078):** TASK-079 (classify all ops, note scope)
6. **Day 3-7 (parallel):** TASK-075 (cache investigation, gates Tier 2)
7. **Day 4-7 (after all P1/P2):** FEATURE-053 (Tier 1 evals with Phase 2 optimization + data-driven decisions)
8. **Day 5-7 (optional):** TASK-074 (Helicone, if bandwidth available)

---

## Notes for Sprint

**Tier 1 ONLY (3 ops).** Do not evaluate other Tier 1 operations (actor_tension_extract, relevance_scoring), Tier 2 operations (narrative_generate, etc.), or plan production rollouts. The goal is to validate the evaluation infrastructure and produce 2-3 data-driven decision records for interview material.

**Scope discipline.** This is how sprints stay on track. Enforce the 3-op, Tier 1-only boundary.

**TASK-075 gates Tier 2.** Narrative cache findings will inform whether narrative_generate needs Flash evaluation or just a cache fix. Do not wait for TASK-075; run in parallel. But do not include narrative_generate in FEATURE-053 scope.

**Phase 2 optimization matters.** Use existing haiku_output from golden set as baseline. Saves time and avoids drift (historical data is fixed reference).

**Data-driven decisions.** Let the metrics decide SWAP/STAY/CONDITIONAL. No pressure to produce a specific outcome. Bad data leading to "STAY" is better than forced "SWAP" without justification.

**Real evals preferred, mock acceptable.** If Gemini API key available, use real calls. If not, mock at provider level with deterministic responses (same input → same output). Eval loop must run reproducibly.

**Decision records are the deliverable.** MSD-001, MSD-002, MSD-003 are worth more than perfect coverage. Aim for quality over quantity.

**Helicone only traces Anthropic.** Gemini calls won't appear in dashboards. This is expected. Don't plan Gemini tracing for this sprint.