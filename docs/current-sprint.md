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

### TASK-078: Model Selection Rubric — Write Decision Framework Document ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** HIGH
- **Effort:** 2-3 hours
- **Goal:** ✅ Write generalizable framework for model selection decisions; becomes interview material and template for future model choices
- **Deliverable:** ✅ `docs/decisions/model-selection-rubric.md` with:
  - **Section 1:** Operation classification (5 types: Extraction, Synthesis, Critique, Polish, Agentic)
  - **Section 2:** Decision dimensions (5 axes: Quality Requirement, Volume, Latency Sensitivity, Determinism, Failure Cost)
  - **Section 3:** Tiering rules (Tier 0/1/2/3 with criteria, Flash strategy per tier)
    - Tier 1: High volume + deterministic + low failure cost (aggressive Flash testing)
    - Tier 2: Medium volume + generation + user-facing (cautious testing)
    - Tier 3: Low volume + reasoning required + safety-critical (no testing)
  - **Section 4:** Override conditions (when to break default tier assignment)
  - **Section 5:** Model selection algorithm (step-by-step for any new operation)
  - **Section 6:** All 14 operations tier summary table with Flash testing phase
- **Testing:** 
  - ✅ Rubric is readable one-pager + tables (printable/shareable)
  - ✅ All 14 operations can be classified using the rubric
  - ✅ Clear guidance on Flash testing scope (aggressive Tier 1, cautious Tier 2, none Tier 3)
  - ✅ Ready for interview reference and FEATURE-053 decision records
- **Implementation:**
  - ✅ Written at `docs/decisions/model-selection-rubric.md` (220 lines)
  - ✅ All 5 operation types defined with Backdrop examples
  - ✅ All 5 decision dimensions with scale and combination rules
  - ✅ All 4 tiers with entrance criteria, target models, and Flash strategies
  - ✅ Override conditions documented with examples
  - ✅ Model selection algorithm (step-by-step for any new operation)
  - ✅ Complete tier summary: all 14 operations with type, tier, current/target models
  - ✅ Sprint 16 scope note: "subset of 5 Tier 1 ops (3 ops: entity_extraction, sentiment_analysis, theme_extraction)"
- **Branch:** Not a code change; document only
- **Unblocks:** ✅ TASK-079, FEATURE-053 framing
- **Next:** TASK-079 can proceed; rubric is reference for operation classification

---

### TASK-079: Operation Tier Mapping — Classify All 14 Operations ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** HIGH
- **Effort:** 2-3 hours
- **Dependency:** TASK-078 ✅ completed first
- **Goal:** ✅ Classify all 14 LLM operations into tiers using the rubric; determines evaluation scope and priority
- **Deliverable:** ✅ `docs/decisions/operation-tiers.md` with:
  - Classification table for all 14 operations (operation, type, tier, rationale)
  - Summary by tier (which ops in each tier)
  - **Flash Evaluation Priority:**
    - **Phase 1 (Tier 1, Aggressive):** entity_extraction, sentiment_analysis, theme_extraction, actor_tension_extract, relevance_scoring (5 ops total)
    - **Phase 2 (Tier 2, Cautious):** narrative_generate (if cache miss confirmed), narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation
    - **Phase 3 (Tier 3, Deferred):** briefing_generate, briefing_critique, briefing_refine, provider_fallback (no testing)
  - **SPRINT 16 SCOPE NOTE:** "Sprint 16 evaluates **subset** of Tier 1 (3 ops: entity_extraction, sentiment_analysis, theme_extraction) due to time constraints. Full Tier 1 (5 ops) and Tier 2 evals deferred to Sprint 17+"
  - Decision gate: TASK-075 narrative_generate cache fix determines whether to include narrative_generate in later phases
- **Testing:** 
  - ✅ All 14 operations classified into tiers
  - ✅ Each operation has detailed rationale (why this tier?)
  - ✅ All 5 decision dimensions documented for each operation
  - ✅ Tier classification matches rubric criteria
  - ✅ Flash evaluation priority order clear and defensible
  - ✅ TASK-075 dependency documented (narrative_generate branching logic)
- **Implementation:**
  - ✅ Written at `docs/decisions/operation-tiers.md` (450+ lines)
  - ✅ Comprehensive tier summary table for all 14 operations
  - ✅ Tier 1 (5 ops): Aggressive Flash testing candidates
  - ✅ Tier 2 (5 ops): Cautious Flash testing candidates (narrative_generate gated on TASK-075)
  - ✅ Tier 3 (4 ops): No Flash testing (safety-critical, document rationale)
  - ✅ Flash evaluation execution order: Phase 1 (Tier 1, 3-op subset), Phase 2 (Tier 2), Phase 3 (Tier 3 deferred)
  - ✅ Decision gate scenarios documented: fixable cache, unfixable cache, working as intended
  - ✅ Interview positioning notes with talking points
- **Branch:** Not a code change; document only
- **Unblocks:** ✅ FEATURE-053 Phase 1 (golden set extraction)
- **Note:** SPRINT 16 EXPLICITLY LIMITS FEATURE-053 TO 3 OPS (entity_extraction, sentiment_analysis, theme_extraction)
- **Next:** FEATURE-053 Phase 1 can proceed; execution order determined

---

## Priority 3 — Enablement + Investigation

### TASK-074: Helicone Setup — Proxy + Kill Switch Configuration ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** MEDIUM
- **Effort:** 2-3 hours (actual: ~1.5 hours)
- **Goal:** ✅ Add Helicone proxy integration for trace visibility during Anthropic calls; toggle via env var
- **Key Note:** **Helicone only traces Anthropic calls.** Gemini calls via GeminiProvider will NOT appear in Helicone dashboards. This is expected and acceptable (separate observability for Gemini is out of scope).
- **Implementation:**
  - ✅ Added `USE_HELICONE_PROXY: bool = False` to `config.py` (env var, default off)
  - ✅ Added `HELICONE_API_KEY: Optional[str] = None` to `config.py` (env var)
  - ✅ Implemented `_get_anthropic_url()` in `gateway.py` to return proxy URL if enabled
  - ✅ Updated `_build_headers()` to add `Helicone-Auth` header when proxy enabled
  - ✅ Verified no performance degradation when proxy disabled
- **Testing:**
  - ✅ Gateway works with proxy disabled (baseline) — all 22 tests pass
  - ✅ Gateway works with proxy enabled (requires valid key)
  - ✅ Dynamic URL selection verified at runtime
  - ✅ Helicone-Auth header only added when enabled
  - ✅ 14 new comprehensive tests all passing
  - ✅ Zero regressions on existing tests
- **Branch:** `docs/task-078-model-selection-rubric` (commit 8be534d)
- **Note:** Implements optional but useful enhancement for Flash evaluation trace visibility
- **Next:** Ready to merge; unblocks FEATURE-053 Phase 1 with optional trace support

---

### TASK-075: Narrative Cache Investigation — Root Cause Analysis & Fix Proposal ✅ COMPLETE
- **Status:** COMPLETE (2026-04-27)
- **Priority:** CRITICAL
- **Effort:** 4-6 hours (actual: ~2 hours)
- **Goal:** ✅ Determined why narrative_generate has 0% cache hit rate; decision reached
- **Decision Gate Outcome: Option B — Root cause is unfixable (architectural constraint)**
  - Exact-match caching cannot help narrative operations under current architecture
  - Flash model swap confirmed as the correct cost lever for Sprint 17
  - Sprint 16 scope unchanged: FEATURE-053 remains Tier 1 only (3 ops)
- **Root cause (3 issues found):**
  - **Issue 1:** `narrative_generate` was likely not in `CACHEABLE_OPERATIONS` historically — explains 0 entries in `llm_cache` despite 3,524 calls
  - **Issue 2 (primary):** Narrative operations process unique per-article content. SHA-1 hash never repeats. One-pass ingestion pipeline + aggressive deduplication means no article is ever reprocessed. Cache hits are structurally impossible. (Contrast: `entity_extraction` hits 99.6% because Celery retries re-run the same content, a side effect not present in the narrative code path.)
  - **Issue 3:** `cluster_narrative_gen`, `actor_tension_extract`, `narrative_polish` are not in `CACHEABLE_OPERATIONS` at all — but adding them would not produce hits for the same reason
- **Secondary bug found:** `_save_to_cache` catches exceptions at `logger.debug` level — cache write failures are invisible in production logs. Fix: `logger.warning`.
- **Alternative strategies evaluated and scoped out:** Semantic caching (over-engineered for $6.64/month), component-level caching (requires pipeline redesign). Both deferred indefinitely.
- **Evidence:** `llm_cache` has 0 narrative entries; `llm_traces` aggregation shows `input_hash` is null on all documents (field not written to trace schema — confirmed across all operations)
- **Follow-on actions:**
  - Now: `logger.debug` → `logger.warning` in `_save_to_cache` (`gateway.py:285`)
  - Now: Add explicit cache hit/miss logging to gateway for observability
  - Sprint 17: Gemini Flash evaluation for narrative operations (Tier 2)
  - Do not pursue: semantic caching, entropy reduction, CACHEABLE_OPERATIONS hygiene fixes
- **Deliverable:** Updated `task-075-narrative-cache-investigation.md` with full findings
- **Unblocks:** ✅ TASK-071 (recalibrate on current cost data as-is); ✅ Sprint 17 Tier 2 Flash eval scoping

---

## Priority 4 — Tier 1 Flash Evaluations (Main Feature, Scoped)

### FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set
- **Status:** PHASES 2-3 COMPLETE, PHASES 4-6 PENDING
- **Priority:** CRITICAL
- **Effort:** 6-8 hours (Phases 2-3 complete; Phases 4-6 deferred to future sessions)
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
  - **Phase 2: ✅ COMPLETE — Baseline Extraction**
    - ✅ Loaded 100 samples per operation from golden set JSONL files
    - ✅ Extracted Haiku baselines from existing `entities`, `sentiment`, `themes` fields
    - ✅ HTML-stripped all input text (production-compliant)
    - ✅ Output: 3 JSONL files + metadata, all samples with `source: "historical"`
    - ✅ Files written to `/docs/decisions/msd-flash/runs/2026-04-28/`
  - **Phase 3: ✅ COMPLETE — Challenger Model Runs**
    - ✅ Ran 3 models (Flash, DeepSeek, Qwen) × 3 operations = 900 API calls
    - ✅ Success rate: 898/900 (99.8%) — 1 flash sentiment error, 1 deepseek theme error
    - ✅ Used production prompts extracted from codebase (exact strings, no rewrites)
    - ✅ Collected: model string, output/input tokens, latency_ms, raw output per sample
    - ✅ Output: 9 JSONL files (3 ops × 3 models) written to same dated directory
  - **Phase 4: ⏳ PENDING — Output Normalization** (future session)
    - Normalize both Haiku baseline and challenger outputs before scoring
    - Strip HTML, lowercase, remove punctuation, deduplicate arrays, sort alphabetically
  - **Phase 5: ⏳ PENDING — Scoring Harness** (future session)
    - Apply eval contract scoring logic exactly
    - F1 for entity_extraction, binary match for sentiment_analysis, adjusted F1 for theme_extraction
    - Flag regressions: F1 < 0.85 (entities), any mismatch (sentiment), F1 < 0.80 (themes)
    - Apply failure mode taxonomy to worst 10 samples per operation
  - **Phase 6: ⏳ PENDING — Decision Records** (future session)
    - Write MSD-001, MSD-002, MSD-003 with comparison tables, cost analysis, data-driven decisions
    - Format: `docs/decisions/MSD-XXX-operation.md`
    - **CRITICAL:** Decisions are data-driven; no forced outcomes
      - SWAP if cost reduction is significant AND no material quality loss
      - STAY if quality regression exceeds threshold
      - CONDITIONAL if tradeoffs depend on context
    - Each record includes: operation, metrics, decision, rationale, override conditions, rollout plan
- **Success Criteria for Sprint 16:**
  - [x] Golden set extracted: 100 samples per operation (3 ops)
  - [x] **Phase 2 optimization applied:** existing haiku_output used (no re-calls)
  - [x] Haiku baseline collected: all samples from golden set fields
  - [x] Flash variant run: all 3 models, real API calls via OpenRouter (898/900 successful)
  - [ ] Comparison table: Model | Quality | Cost/1k | p50ms | p95ms (Phase 5)
  - [ ] Quality regression detected and flagged if >5% (Phase 5)
  - [ ] 2-3 decision records written (MSD-001+) (Phase 6)
  - [ ] **Decisions are data-driven (no pressure to force "SWAP" outcomes)** (Phase 6)
  - [x] Golden set definition documented (reproducible)
  - [x] Production prompts extracted exactly (no rewrites)
  - [ ] Eval methodology documented (quality scoring rules, regression threshold) (Phase 5)
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
- [x] TASK-078 complete: `docs/decisions/model-selection-rubric.md` written, one-pager + tables ✅
- [x] TASK-079 complete: `docs/decisions/operation-tiers.md` with all 14 ops classified ✅
- [x] Tier 1 classification matches rubric (high volume + deterministic) ✅
- [x] Sprint 16 scope note: "subset of 5 Tier 1 ops (3 ops: entity_extraction, sentiment_analysis, theme_extraction for time constraints)" ✅

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
- [x] TASK-075 root cause documented: **structural — unique per-article inputs, one-pass processing, no retry repetition**
- [x] Decision recorded: **Accept as architectural constraint. Exact-match caching cannot help narrative operations.**
- [x] Alternative strategies evaluated and scoped out (semantic caching, component-level caching)
- [x] Cost impact: $0 savings from caching; Flash model swap confirmed as correct lever (Sprint 17)
- [x] Secondary observability bug found: logger.debug → logger.warning fix queued
- [x] Tier 2 ops (narrative_generate, etc.) confirmed deferred to Sprint 17 for Flash evaluation

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
| TASK-078 | Model Selection Rubric (5-tier framework) | P2 | ✅ COMPLETE | 2-3h | UNBLOCKED |
| TASK-079 | Operation Tier Mapping (all 14 ops + scope note) | P2 | ✅ COMPLETE | 2-3h | UNBLOCKED |
| TASK-074 | Helicone Setup (proxy + kill switch, Anthropic-only) | P3 | ✅ COMPLETE | 1.5h | Optional |
| TASK-075 | Narrative Cache Investigation (gates Tier 2) | P3 | ✅ COMPLETE | ~2h | Sprint 17 Tier 2 scoping unblocked |
| FEATURE-053 | Flash Evaluations (Tier 1 only, 3 ops, data-driven decisions) | P4 | OPEN | 6-8h | All P1/P2 tickets (P3 optional) |

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