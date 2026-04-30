# Sprint 17 — Tier 1 Cost Optimization (Prompt Fixes + Threshold Evaluation)

**Status:** ⏳ IN PROGRESS  
**Actual Start:** 2026-04-28 (accelerated)  
**Target End:** 2026-05-17 (extended to include TASK-085, TASK-086 Phase 1, and queued TASK-087 reliability refactor)  
**Sprint Goal:** Fix broken Tier 1 baselines, define quality thresholds, run evaluations, identify cost-optimized models, **add DeepSeek support through LLMGateway, route the existing enrichment batch to DeepSeek, and validate production behavior with rollback.**

**Major Discovery (2026-04-30):** Direct DeepSeek API is 10-12x cheaper than OpenRouter. Recommendation: **DeepSeek on all Tier 1 operations saves $55k/year.** Repo review corrected the implementation path: DeepSeek should be added through `LLMGateway`, not as a standalone provider path. Phase 1 routes the existing `article_enrichment_batch` path to DeepSeek and validates sentiment as the primary quality signal because sentiment, relevance, and themes are currently batched together.

**Current Phase:** FEATURE-054 complete. TASK-085 has been rewritten as a minimal gateway integration. TASK-086 Phase 1 remains the production validation/monitoring step. TASK-087 has been added as the follow-up reliability refactor after the minimal integration works.

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

## Open Tickets (Sprint 17 In Progress)

| ID | Title | Priority | Status | Effort | Blocks / Notes |
|---|---|---|---|---|---|
| TASK-081 | Fix Tier 1 prompts | P1 | ✅ COMPLETE | 2-3h | — |
| TASK-082 | Define quality thresholds | P1 | ✅ COMPLETE | 1h | — |
| FEATURE-054 | Tier 1 Cost Optimization Evals | P1 | ✅ COMPLETE (Phases 1-4) | 8-10h | — |
| TASK-085 | Add DeepSeek support to LLMGateway and route enrichment batch | P1 | ⏳ IN PROGRESS | 3-4h | Blocks TASK-086 Phase 1 |
| TASK-086 Phase 1 | Deploy enrichment batch to DeepSeek + monitor sentiment quality | P1 | ⏳ QUEUED | 1 week | Requires TASK-085 |
| TASK-086 Phase 2 | Deploy entity extraction + validate | P1 | ⏳ CONDITIONAL | 2 weeks | Requires Phase 1 success |
| TASK-087 | Refactor gateway-owned reliability controls | P2 | ⏳ QUEUED | 4-6h | Do after TASK-085 works and rollback path is validated |
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

3. ⏳ **Day 5-6:** TASK-085 — IN PROGRESS
   - Add DeepSeek support through `LLMGateway`, not a standalone provider path
   - Add provider-aware routing for `anthropic:*` and `deepseek:*` model refs
   - Add DeepSeek config, request formatting, response parsing, cost tracking, and trace validation
   - Route `article_enrichment_batch` to `deepseek:deepseek-v4-flash` for Phase 1
   - Add `article_enrichment_batch` to existing rate limiter and circuit breaker tracked systems

4. ⏳ **Day 7-13:** TASK-086 Phase 1 — QUEUED
   - Production validation of DeepSeek-backed `article_enrichment_batch`
   - Sentiment is the primary validation metric because it has highest confidence from FEATURE-054
   - Monitor briefing quality, sentiment agreement, enrichment parse failures, trace correctness, costs, and fallback/revert path
   - Decision: keep DeepSeek route, revert to Anthropic, or extend validation

5. ⏳ **After TASK-085 works / after Phase 1 validation starts:** TASK-087 — QUEUED
   - Refactor circuit breaker and rate limiter ownership into `LLMGateway`
   - Add provider-scoped reliability keys such as `deepseek:article_enrichment_batch`
   - Remove duplicated caller-level reliability checks only after tests prove gateway enforcement works
   - Not required before the first DeepSeek production validation

6. ⏳ **Day 14-27 (conditional):** TASK-086 Phase 2 — CONDITIONAL
   - Entity extraction cutover only if Phase 1 succeeds
   - 2 weeks monitoring + validation
   - Decision: keep, revert, or proceed to theme rollout planning

7. ⏳ **Future / optional:** Theme reannotation + theme rollout
   - Theme extraction remains higher risk because FEATURE-054 found low agreement and reference/prompt mismatch
   - Create or revive a dedicated theme reannotation ticket only if pursuing theme rollout

---

**Sprint 17 completes when:**
- ✅ TASK-085: DeepSeek works through `LLMGateway` for `article_enrichment_batch`
- ✅ TASK-086 Phase 1: DeepSeek-backed enrichment batch has been monitored in production and a keep/revert decision is made

**If Phase 1 succeeds (>= 80% sentiment agreement, no material parse/briefing quality issues, and cost tracking is correct):**
- Keep DeepSeek route for `article_enrichment_batch`
- Proceed with TASK-087 reliability refactor if not already started
- Sprint 18 can begin with TASK-086 Phase 2 for entity extraction deployment

**If Phase 1 fails (agreement < 75%, parse failures, user-facing quality issues, or trace/cost tracking issues):**
- Revert `article_enrichment_batch` routing to Anthropic Haiku
- Close Sprint 17 with lesson learned
- Do not start entity/theme rollout until failure mode is understood

### Sprint 18 Roadmap (Conditional)

| Task | Effort | Timeline | Condition |
|---|---|---|---|
| **TASK-087** | Gateway-owned reliability controls + provider-scoped keys | 4-6h | After TASK-085 works and rollback path is validated |
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
| Effort (with deployment) | N/A (was Sprint 18) | 15-20 hours (TASK-085 + TASK-086 Phase 1 + conditional Phase 2) plus TASK-087 refactor if Phase 1 path is stable |
| Recommendation | Flash on sentiment ($7k/year savings) | DeepSeek on all three ($55k/year savings) |
| Work split | FEATURE-054 only | FEATURE-054 + TASK-085 + TASK-086 Phase 1 + TASK-087 queued (+ Phase 2/3 conditional) |
| Deliverables | 3 decision records | 6 docs + gateway integration + production validation + follow-up reliability refactor ticket |
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

---

## Philosophy for Sprint 17 (Current Phase)

**Focus:** Complete TASK-085 as a minimal `LLMGateway` integration, route `article_enrichment_batch` to DeepSeek, run TASK-086 Phase 1 production validation, and make a keep/revert decision.

**Not:** Refactor reliability ownership before DeepSeek works. Do not try all three Tier 1 operations at once. Keep phases sequential with rollback at each step.

**Rationale:** Sentiment has highest confidence (85% agreement), but production currently batches sentiment with relevance and themes. Route the existing batch first, validate sentiment as the primary metric, learn from production, then tackle entity extraction if Phase 1 succeeds. Keep theme extraction optional and dependent on reannotation.

**Taste:** Pragmatism + rigor. $55k/year opportunity doesn't require betting everything at once. Phased rollout minimizes risk. Minimal integration first, reliability refactor second.

---

*Sprint 17 IN PROGRESS (as of 2026-04-30). FEATURE-054 Phases 1-4 complete. TASK-085 rewritten as gateway integration and in progress. TASK-086 Phase 1 queued for ~2026-05-02. TASK-087 added as follow-up reliability refactor. Sprint closes ~2026-05-17 after Phase 1 monitored + decision made.*
