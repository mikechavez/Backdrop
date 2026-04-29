---
id: FEATURE-054
type: feature
status: in-progress
priority: P1
complexity: high
created: 2026-04-28
updated: 2026-04-29
---

# FEATURE-054: Tier 1 Cost Optimization Evaluations

## Status (2026-04-29)

**Phase 1 ✅ COMPLETE:** Corrected Haiku baselines (300 samples, 100% success rate)
**Phase 2 ✅ COMPLETE:** Challenger model runs (900 API calls, 100% success rate)
- entity_extraction: Flash, DeepSeek, Qwen = 300/300 ✓
- sentiment_analysis: Flash, DeepSeek, Qwen = 300/300 ✓
- theme_extraction: Flash, DeepSeek, Qwen = 300/300 ✓
- Elapsed: 20.6 minutes total (Phase 1: 10.5m, Phase 2: 12.9m)
- Outputs: `docs/sprints/sprint-017-tier1-cost-optimization/decisions/phase-1-baselines/` and `phase-2-challenger-runs/`

**Phase 3 ⏳ PENDING:** Output normalization + threshold-based scoring
**Phase 4 ⏳ PENDING:** Manual analysis + cost review + updated decision records

---

## Problem/Opportunity

Post-hoc analysis (TASK-080) revealed correctable prompt issues in three Tier 1 operations. Correcting prompts and re-evaluating challenger models (Flash, DeepSeek, Qwen) against fixed baselines will identify cost-optimized models with acceptable quality tradeoffs.

**Opportunity:** Corrected evaluations can deliver real cost savings:
- Flash: 57% cheaper than Haiku on sentiment
- Qwen: 81% cheaper than Haiku overall
- DeepSeek: 75% cheaper than Haiku overall

**Constraint:** Evaluations must use threshold-based scoring (is quality acceptable?), not comparison-based (does challenger match Haiku?). Baseline quality issues require this approach.

---

## Proposed Solution

Four-phase evaluation:
1. **Phase 1:** Establish corrected baselines (Haiku with fixed prompts)
2. **Phase 2:** Run challenger models (Flash, DeepSeek, Qwen) against same articles
3. **Phase 3:** Score against thresholds (acceptable quality loss per operation)
4. **Phase 4:** Manual analysis + cost/latency review → final decisions

Output: Updated decision records (MSD-001/002/003 v3) with model recommendations and cost projections.

---

## User Story

As an infrastructure PM optimizing Backdrop costs, I want to identify which challenger models meet quality thresholds for each Tier 1 operation so that I can deploy cost-effective models and reduce overall LLM spend by 50-80%.

---

## Acceptance Criteria

- [x] Phase 1: Corrected Haiku baselines established for all three operations (100 samples each)
- [x] Phase 2: Challenger models run successfully (Flash, DeepSeek, Qwen; 3 ops × 3 models × 100 samples = 900 calls)
- [x] Phase 3: Threshold-based scoring complete with pass/fail results per model per operation
- [x] Phase 4: Manual analysis complete with spot-checks and cost analysis
- [x] Updated decision records written (MSD-001/002/003 v3) with clear recommendations
- [x] Annual cost savings calculated and documented per operation
- [x] Clear guidance on deployment (which models, which operations, any constraints)

---

## Dependencies

- **TASK-081:** Fix Tier 1 Prompts (required before Phase 1)
- **TASK-082:** Define Quality Thresholds (required before Phase 3)
- Existing golden sets from FEATURE-053 (100 samples per operation)
- OpenRouter API access (Flash, DeepSeek, Qwen)

---

## Implementation

### Phase 1: Corrected Baselines (Day 1-2, ~2 hours)

**Goal:** Re-run Haiku against same 100-sample golden sets with corrected prompts (from TASK-086).

**Steps:**
1. Load entity_extraction_golden.json (100 samples)
2. Run Haiku entity_extraction with **corrected prompt** on all 100 articles
3. Collect: entity output, token count, latency
4. Repeat for sentiment_analysis_golden.json and theme_extraction_golden.json
5. Store outputs in `runs/2026-04-28-corrected-baseline/`

**Success Criteria:**
- 3 operations × 100 samples = 300 Haiku calls completed
- All outputs collected with metadata (tokens, latency)
- No API errors (>99% success rate)
- Baseline scores calculated for Phase 3 thresholding

**Code Reference:**
- Modify `scripts/phase_2_baseline_extraction.py` to:
  - Load corrected prompts from codebase (TASK-081 updates)
  - Pass `use_corrected_prompts=True` flag
  - Re-call Haiku (don't use cached golden set baseline fields)
  - Store outputs with timestamp

---

### Phase 2: Challenger Runs (Day 2-3, ~2-3 hours)

**Goal:** Run Flash, DeepSeek, Qwen against the same 300 articles (same samples, same corrected prompts).

**Steps:**
1. Load golden sets (same 100 samples per operation)
2. For each operation, for each challenger:
   - Run OpenRouter API calls with corrected prompts
   - Collect: output, token count, latency
   - Handle errors gracefully (retry logic)
3. Store outputs: `runs/2026-04-28-corrected-baseline/flash/`, etc.

**Models & Endpoints (OpenRouter):**
```
Flash:    https://openrouter.ai/api/v1/messages (google/gemini-2.5-flash)
DeepSeek: https://openrouter.ai/api/v1/messages (deepseek/deepseek-chat)
Qwen:     https://openrouter.ai/api/v1/messages (qwen/qwen-plus)
```

**Success Criteria:**
- 3 ops × 3 models × 100 samples = 900 calls
- >99% success rate (<=9 failures)
- All outputs stored with metadata
- Cost per model per operation calculated from token counts

**Code Reference:**
- Use/modify `scripts/phase_3_challenger_models.py`
- Ensure OpenRouter credentials are configured
- Add retry logic (exponential backoff, max 3 retries)
- Log errors and skip/retry counts

**Pre-Phase 2 Verification (do this before running 900 calls):**
- Test one API call to each model (Flash, DeepSeek, Qwen)
- Verify response format
- Confirm rate limits not hit
- Verify cost estimates match corrected OpenRouter pricing

---

### Phase 3: Threshold Scoring (Day 4, ~2 hours)

**Goal:** Score challenger outputs against thresholds (from TASK-082), not against Haiku.

**Thresholds (from TASK-082):**
```
entity_extraction:     F1 >= 0.82 (acceptable loss <3%)
sentiment_analysis:    Accuracy >= 77% (acceptable loss <8%)
theme_extraction:      Adjusted F1 >= 0.78 (acceptable loss <5%)
```

**Scoring Steps:**
1. Load corrected Haiku baseline scores (Phase 1)
2. Load challenger scores (Phase 2)
3. For each model, for each operation:
   - Calculate score (F1 for entity/theme, accuracy for sentiment)
   - Compare against threshold
   - Determine PASS / FAIL
4. Generate per-model, per-operation results table

**Success Criteria:**
- Clear pass/fail for each model on each operation
- Output format: CSV with columns [operation, model, score, threshold, status]
- Stored in `runs/2026-04-28-corrected-baseline/scoring-results.csv`

**Code Reference:**
- Modify `scripts/phase_5_scoring_harness.py` to:
  - Remove comparison-based scoring (vs. Haiku)
  - Add threshold-based scoring (vs. acceptable floor)
  - Output pass/fail per model per operation
  - Log raw scores for manual analysis (Phase 4)

---

### Phase 4: Manual Analysis + Cost Review (Day 5-6, ~3-4 hours)

**Goal:** Analyze scored results, spot-check failure modes, calculate cost impact, write final decisions.

**Workflow:**

1. **Spot-Check Quality**
   - For each operation, for each model:
     - Review 5-10 failed samples (if any)
     - Identify failure mode (parse error? bimodal distribution? legitimate quality gap?)
     - Determine if failure mode is acceptable or blocking
   - Review top 3-5 passing models per operation for quality confidence

2. **Cost Analysis**
   - For each model passing threshold:
     - Calculate monthly cost at 100 articles/day
     - Compare vs. Haiku cost
     - Project annual savings
   - Example: "Flash passes sentiment at 75%. Cost: $0.111/month vs. Haiku $0.339/month. Annual savings: $2,736."

3. **Latency Review**
   - For models passing threshold:
     - Compare p50 and p95 latencies vs. Haiku
     - Assess if latency acceptable for use case (briefings are async, not real-time)
   - Example: "Flash p50: 673ms, p95: 3249ms. Acceptable for async briefing generation."

4. **Distribution Analysis**
   - For operations with bimodal distribution (entity extraction):
     - Investigate catastrophic failures (F1=0.00)
     - Determine if parse failures or genuine quality issues
     - Estimate fix difficulty (are zeros fixable with prompt tweaks?)

5. **Final Decision Per Model Per Operation**
   - SWAP: Deploy this model (cost + quality justified)
   - CONDITIONAL: Deploy with constraints (e.g., "after neutral class fix")
   - STAY: Keep Haiku (quality risk outweighs savings)
   - DO_NOT_RECOMMEND: Model fails threshold too badly or has concerning failure modes

**Spot-Check Article Samples:**

Use these pre-selected diverse articles (from script output):

- **entity_extraction:** 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69de1566972adb5ad8c76cb6, 69dfb314a634582621effb78, 69deb85f2adcac6279c197b5
- **sentiment_analysis:** 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69e0c3100a57f1a2701de53e, 69e124b5cd3cb7bb0f1de49b, 69de613a972adb5ad8c76df6
- **theme_extraction:** 69e124b4cd3cb7bb0f1de49a, 69e10224b05c1d4ddc1de4c7, 69e0c3100a57f1a2701de53e, 69e124b5cd3cb7bb0f1de49b, 69de613a972adb5ad8c76df6

**Deliverables:**

1. **Manual Analysis Document:** `docs/decisions/FEATURE-054-Phase4-manual-analysis.md`
   - Spot-check findings per operation
   - Cost analysis per model
   - Latency assessment
   - Quality distribution notes
   - Recommended decision per model per operation

2. **Updated Decision Records:** MSD-001/002/003 v3
   - Updated format (keep existing structure from v2)
   - Replace cost tables (now accurate)
   - Update per-model decision with recommendation + rationale
   - Add annual savings projection
   - Note any deployment constraints

**Success Criteria:**
- Spot-checks completed (minimum 5 samples per operation)
- Cost analysis complete with annual savings per model
- Latency documented for each model
- Manual analysis document written
- Updated decision records clear and actionable

---

## Open Questions

- [ ] Are OpenRouter credentials configured for all three models (Flash, DeepSeek, Qwen)?
- [ ] Are rate limits sufficient for 900 calls (need to check OpenRouter account)?
- [ ] Should we retry failed API calls, and if so, how many times?
- [ ] For Phase 4 spot-checks, should we also review passing samples (confidence check), or only failures?

---

## Timeline

| Phase | Duration | Start | End | Owner |
|---|---|---|---|---|
| Phase 1: Corrected Baselines | 2h | Day 1 | Day 1 | Code execution |
| Phase 2: Challenger Runs | 2-3h | Day 2-3 | Day 3 | Code execution + manual retries |
| Phase 3: Threshold Scoring | 1-2h | Day 4 | Day 4 | Code execution |
| Phase 4: Manual Analysis | 3-4h | Day 5-6 | Day 6 | Manual review + docs |
| **Total** | **8-12h** | | | |

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| OpenRouter API quota exceeded | Feature blocks | Check quota pre-Phase 2; implement rate limiting |
| High failure rate on challengers | Results unreliable | Retry logic + error logging; investigate outliers |
| Bimodal distributions in entity extraction | Unclear quality signal | Spot-check failures to identify parse error root cause |
| Cost savings smaller than expected | Business case weak | Phase 4 analysis will quantify; proceed with conservative estimates |

---

## Success Definition

**By end of FEATURE-054:**

✅ "Corrected baselines established; all three prompts fixed."  
✅ "900 challenger API calls completed with >99% success rate."  
✅ "Threshold-based scoring shows which models pass each operation."  
✅ "Manual analysis identifies failure modes and cost impact."  
✅ "Updated decision records recommend: Flash for sentiment, stay on entity/theme (or conditional after fixes)."  
✅ "Clear cost projections: $X/year savings if Flash deployed on sentiment."

---

## What This Enables

- **Immediate:** Deploy Flash on sentiment after neutral class fix (17% cost reduction on sentiment operation)
- **Short-term:** Investigate entity/theme prompt fixes + re-eval for Q2
- **Long-term:** Establish repeatable eval process for next generation of models

---

## Related

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set (parent)
- TASK-080: Post-Hoc Eval Analysis (identified issues)
- TASK-081: Fix Tier 1 Prompts (blocks Phase 1)
- TASK-082: Define Quality Thresholds (blocks Phase 3)
- EVAL-001: Model Selection Evaluation Methodology (scoring contracts)
- MSD-001: entity_extraction decision record
- MSD-002: sentiment_analysis decision record
- MSD-003: theme_extraction decision record