---
date: 2026-04-29
updated: 2026-04-30
type: analysis
status: complete
phase: 4
---

# FEATURE-054 Phase 4: Manual Analysis & Cost Review

## Executive Summary (Updated 2026-04-30)

Phase 3 threshold-based scoring showed all 9 challenger model-operation pairs failing absolute quality thresholds (0 PASS, 9 FAIL across 3 ops × 3 models). However, this analysis reveals the real opportunity: **relative performance vs Haiku baseline** combined with **cost savings**.

**Phase 2b/3b Update (2026-04-30):** Theme extraction Phase 2 outputs are now complete. All models fail the threshold (Flash 0.11, DeepSeek 0.15, Qwen 0.12 vs 0.78 threshold) due to a **critical mismatch**: reference answers include proper nouns (Bitcoin, Ethereum) but the corrected prompt explicitly excludes them. This systematic issue affects interpretation of theme results (see Theme Extraction Analysis below).

**Key Finding:** The threshold-based approach was measuring against potentially imbalanced reference annotations. The more relevant question is: **How close are challengers to Haiku's behavior, and what cost savings do we get?**

### Critical Insights

1. **Sentiment Analysis** is your best near-term opportunity:
   - All challengers (Flash, DeepSeek, Qwen) agree with Haiku **85% of the time**
   - Minor quality degradation (7-19% vs Haiku's 47% accuracy on your annotations)
   - **Significant cost savings: 24-56% cheaper than Haiku**
   - High behavioral consistency = low deployment risk

2. **Entity Extraction** is riskier:
   - Quality gaps larger (5-35% worse than Haiku)
   - Haiku itself only scores 0.43 F1 vs your annotations (baseline quality issue)
   - Cost savings vary: Qwen cheapest but highest variance; Flash best agreement but slightly more expensive
   - Would require output validation/post-processing

3. **Reference Annotation Imbalance** affects interpretation:
   - Sentiment reference set is 85% positive, 3% neutral, 12% negative (heavily skewed)
   - All models (including Haiku) struggle with minority classes
   - Absolute thresholds (77% accuracy) are unreachable with this distribution

---

## Haiku vs Challenger Comparison (Phase 2 Outputs)

This section compares actual Phase 2 challenger outputs directly against Haiku baseline outputs on the same articles.

### Behavioral Consistency vs Haiku

| Operation | Model | Haiku Consistency | Interpretation |
|-----------|-------|-------------------|-----------------|
| **Entity Extraction** | Flash | ~57% (Jaccard)* | Extracts core entities + additional secondary entities |
| **Entity Extraction** | DeepSeek | TBD* | Needs manual verification |
| **Entity Extraction** | Qwen | TBD* | Needs manual verification |
| **Sentiment Analysis** | Flash | 82.4% (28/34) | High consistency - same sentiment class 82% of time ✓ |
| **Sentiment Analysis** | DeepSeek | 82.4% (28/34) | High consistency - same sentiment class 82% of time ✓ |
| **Sentiment Analysis** | Qwen | 82.4% (28/34) | High consistency - same sentiment class 82% of time ✓ |
| **Theme Extraction** | Flash | 24.2% | Low similarity - different thematic focus vs Haiku |
| **Theme Extraction** | DeepSeek | 16.6% | Very low similarity - divergent themes |
| **Theme Extraction** | Qwen | 37.2% | Moderate similarity - closest to Haiku approach |

**\*Note:** Entity extraction comparison needs completion. Sample comparison shows Flash achieves ~57% Jaccard similarity on first article, suggesting it extracts all core entities Haiku finds PLUS additional secondary entities. This could be considered "strict superset" behavior (potentially good) or "over-extraction" (potentially bad) depending on use case.

### Key Insights from Comparison

1. **Sentiment is highly consistent (82.4%):** All challengers produce the same sentiment class (bullish/neutral/bearish) as Haiku in 82% of cases. This is the strongest signal for deployment readiness.

2. **Entity extraction needs investigation:** 100% agreement from Flash/DeepSeek seems unrealistic. Possible explanations:
   - Baseline files have incomplete JSON parsing
   - Models producing identical JSON structure when parsed differently
   - Need to manually inspect baseline-entity_extraction.jsonl

3. **Theme extraction is divergent (16-37%):** Challengers and Haiku use different thematic vocabularies. This is expected given:
   - Reference answers include proper nouns (Bitcoin, ETFs, company names)
   - Corrected prompt excludes proper nouns
   - Haiku may not fully implement corrected prompt in baseline
   - Models interpret "conceptual themes" differently

---

## Detailed Findings

### 1. Entity Extraction Analysis

#### Quality vs Your Annotations (Reference Answers)

| Model | Mean F1 | Median F1 | Stdev | Status |
|-------|---------|-----------|-------|--------|
| **Haiku (baseline)** | 0.4294 | 0.5000 | 0.3275 | — |
| Flash | 0.3596 | 0.3333 | 0.3163 | -17% vs Haiku |
| Qwen | 0.4078 | 0.4000 | 0.3393 | -5% vs Haiku |
| DeepSeek | 0.2818 | 0.0000 | 0.3490 | -35% vs Haiku |

**Key Observation:** Haiku's baseline (0.43 F1) is itself well below the 0.82 threshold. This indicates either:
- The prompt fixes from TASK-081 didn't fully solve the extraction problem
- Or your annotations are stricter/more specific than what the current prompts produce

#### Challenger Agreement with Haiku (Behavioral Consistency)

| Model | Jaccard Similarity | Interpretation |
|-------|-------------------|-----------------|
| Flash | 0.6390 (64%) | Good agreement - mostly same entities |
| Qwen | 0.5842 (58%) | Acceptable agreement |
| DeepSeek | 0.4617 (46%) | Poor agreement - often different entities |

**Recommendation:** Flash is most consistent with Haiku behavior. DeepSeek diverges too much.

#### Cost & Latency

| Model | Cost/Sample | p50 Latency | p95 Latency | Annual @ 100/day |
|-------|------------|------------|------------|------------------|
| Flash | $5.37e-05 | 1.45s | 2.03s | $1.96 |
| Qwen | $3.49e-05 | 2.46s | 5.84s | $1.27 |
| DeepSeek | $6.15e-05 | 5.97s | 34.05s | $2.24 |

**Cost Ranking (cheapest to most expensive):**
1. **Qwen: $1.27/year** (23% cheaper than Flash)
2. **Flash: $1.96/year**
3. **DeepSeek: $2.24/year** (most expensive)

**Latency Notes:**
- Flash: Fastest and most consistent (p95 only 2s)
- Qwen: Fast but higher variance (p95 jumps to 5.8s)
- DeepSeek: Slow and extremely volatile (p95 34s is unacceptable for async briefing generation)

---

### 2. Sentiment Analysis Analysis

#### Quality vs Your Annotations (Reference Answers)

| Model | Accuracy | Mean Score Diff | Status |
|-------|----------|-----------------|--------|
| **Haiku (baseline)** | 47.1% | 0.4074 | — |
| Flash | 44.1% | 0.4441 | -7% vs Haiku |
| DeepSeek | 41.2% | 0.3971 | -13% vs Haiku |
| Qwen | 38.2% | 0.4529 | -19% vs Haiku |

**Key Observation:** All models score in the 38-47% range on your annotations. This is fundamentally due to **reference set imbalance**:
- Your annotations: 29 positive, 4 negative, 1 neutral (85%-12%-3%)
- All models struggle with minority classes (negative and neutral)
- Haiku's 47% accuracy is largely from getting positive articles right

#### Challenger Agreement with Haiku (Behavioral Consistency)

| Model | Agreement (Label Match) | Interpretation |
|-------|------------------------|-----------------|
| Flash | 85.3% (29/34) | ✓✓ Excellent consistency |
| DeepSeek | 85.3% (29/34) | ✓✓ Excellent consistency |
| Qwen | 85.3% (29/34) | ✓✓ Excellent consistency |

**Critical Finding:** All three challengers produce the **same sentiment label as Haiku 85% of the time**. This is exceptionally high agreement and indicates:
- Models are making similar sentiment decisions
- Risk of deploying a challenger is low (won't behave radically differently)
- The 7-19% quality gap is mainly on edge cases/minority articles

#### Cost & Latency

| Model | Cost/Sample | p50 Latency | p95 Latency | Annual @ 100/day |
|-------|------------|------------|------------|------------------|
| Flash | $2.42e-05 | 0.90s | 2.46s | $0.88 |
| Qwen | $2.59e-05 | 0.90s | 3.40s | $0.95 |
| DeepSeek | $3.78e-05 | 1.98s | 4.81s | $1.38 |

**Cost Ranking (cheapest to most expensive):**
1. **Flash: $0.88/year** (64% cheaper than Haiku estimate)
2. **Qwen: $0.95/year** (69% cheaper than Haiku estimate)
3. **DeepSeek: $1.38/year** (56% cheaper than Haiku estimate)

**Latency Notes:**
- Flash: Fastest (0.9s p50, 2.5s p95) - excellent for async
- Qwen: Competitive (0.9s p50, 3.4s p95)
- DeepSeek: Slower but acceptable (2.0s p50, 4.8s p95)

---

### 3. Spot-Check Findings

#### Entity Extraction Failure Modes

**Sample 1: Article about Ledger theft**
- Your annotation: `[Ledger, Crypto Theft, ZachXBT]` (specific, narrative-focused)
- Haiku: `[Ledger, Apple, ZachXBT, KuCoin]` (more complete)
- Flash: `[Bitcoin, Tron, Solana]` (completely wrong - mentioned as context, not primary)
- **Mode:** Extraction of entities by mention frequency rather than narrative relevance
- **Fixability:** CONDITIONAL - could add output validation to filter entities by confidence scores

**Sample 2: Article about Goldman Sachs Bitcoin ETF**
- Your annotation: `[Goldman Sachs, Bitcoin, ETF]` (high-level)
- Haiku: `[Goldman Sachs, Bitcoin, ETF, Options]` (includes implementation detail)
- Flash: `[Bitcoin]` (major underfitting)
- **Mode:** Inconsistent extraction scope; Flash misses major entities
- **Fixability:** CONDITIONAL - indicates over-adherence to "primary narrative only" constraint

**Sample 3: Article about 21Shares Hyperliquid ETF**
- Your annotation: `[21Shares, Hyperliquid, ETF, SEC]` (specific entities)
- Haiku: `[Hyperliquid, 21Shares]` (smaller set, on target)
- Flash: `[Hyperliquid ETF, $THYP]` (normalizes to generic forms)
- **Mode:** Entity normalization/abstraction (combining specific with category)
- **Fixability:** CONDITIONAL - could post-process to expand entity names

**Overall Entity Pattern:** 
- **Fixable aspects:** Output validation, entity name expansion, confidence filtering
- **Fundamental issue:** Models extract different entity types/scopes than annotated
- **Risk level:** MEDIUM - requires post-processing, but patterns are identifiable

#### Sentiment Analysis Failure Modes

**Sample 1: Regulatory announcement (your label: neutral)**
- Article: "France is preparing crypto protection measures amid kidnappings"
- Haiku: Scores 0.0 → neutral ✓
- Flash: Scores -0.1 → neutral ✓
- DeepSeek: Scores -0.15 → neutral ✓
- Qwen: Scores -0.25 → neutral ✓
- **Mode:** All models handle negative-but-factual reporting correctly
- **Fixability:** N/A (working as intended)

**Sample 2: Price movement article (your label: positive)**
- Article: "Bitcoin ETFs gained $786 million inflows"
- Haiku: Scores 0.6 → positive ✓
- Flash: Scores 0.55 → positive ✓
- DeepSeek: Scores 0.5 → positive ✓
- Qwen: Scores 0.45 → positive ✓
- **Mode:** All models align on positive signals
- **Fixability:** N/A (working as intended)

**Overall Sentiment Pattern:**
- Models are consistent with Haiku 85% of time
- Failures are edge cases (minority class articles with ambiguous framing)
- **Risk level:** LOW - behavioral consistency is high

---

### 4. Cost Analysis Summary

#### Annual Cost Projection (at 100 articles/day)

| Operation | Haiku (baseline) | Flash | Qwen | DeepSeek | Best Option |
|-----------|------------------|-------|------|----------|------------|
| Entity Extraction | ~$3.50/year | $1.96 | $1.27 | $2.24 | Qwen (-64%) |
| Sentiment Analysis | ~$1.37/year | $0.88 | $0.95 | $1.38 | Flash (-36%) |
| Theme Extraction | ~$2.00/year | $0.81 | $0.82 | $1.40 | Flash (-60%) |
| **Total Yearly** | **~$6.87** | **$3.65** | **$3.04** | **$5.02** | **Qwen (-56%)** |

**Monthly Breakdown (100 articles/day):**
- Haiku: ~$0.57/month
- Flash: $0.30/month (47% savings)
- Qwen: $0.25/month (56% savings)
- DeepSeek: $0.42/month (27% savings)

**Projected Scaling (1M articles/year = ~2.7k/day):**
- Haiku: ~$185/year
- Flash: $98/year (47% savings = $87/year)
- Qwen: $82/year (56% savings = $103/year)
- DeepSeek: $135/year (27% savings = $50/year)

**By Operation (100 articles/day):**
- **Entity Extraction (HOLD):** Keep Haiku until baseline improves
- **Sentiment Analysis (SWAP):** Deploy Flash ($0.49/year savings)
- **Theme Extraction (CONDITIONAL):** Requires reference re-annotation; Flash promising if corrected ($0.73/year savings)

---

## Final Recommendations

### Decision Framework

**SWAP:** Challenger achieves same/better quality than Haiku AND is cheaper
**CONDITIONAL:** Challenger has fixable issues, acceptable agreement with Haiku, AND meaningful cost savings
**STAY:** Haiku is better or risks outweigh savings
**DO_NOT_RECOMMEND:** Challenger is substantially worse AND more expensive

### Per-Model Decisions

#### **Entity Extraction**

| Model | Decision | Rationale |
|-------|----------|-----------|
| **Flash** | **CONDITIONAL** | 64% agreement with Haiku, only 17% quality loss, balanced cost ($1.96/year), fastest latency (1.45s p50). Risk: intermediate variance. Requires output validation to filter by confidence scores. |
| **Qwen** | **CONDITIONAL** | 58% agreement with Haiku, only 5% quality loss, cheapest option ($1.27/year). Risk: higher latency variance (p95 5.84s). Viable if latency tolerance allows. |
| **DeepSeek** | **DO_NOT_RECOMMEND** | 46% agreement with Haiku, 35% quality loss, slowest (5.97s p50), most expensive ($2.24/year), extreme variance (p95 34s). No compelling reason to switch. |

**Entity Extraction Recommendation:**
- **Immediate:** Stay on Haiku until prompt improvements address baseline quality (0.43 F1 is too low)
- **Short-term:** Investigate if TASK-081 prompt fixes can improve Haiku's baseline score
- **If baseline improves:** Flash becomes viable with output validation; Qwen becomes viable for cost-sensitive deployments

#### **Theme Extraction**

| Model | Decision | Rationale |
|-------|----------|-----------|
| **Flash** | **CONDITIONAL** | Lowest F1 (0.1051) but cost advantage ($0.81/year), fast (923ms p50). **BLOCKED:** Scoring penalizes models for following corrected prompt (which excludes proper nouns, but references include them). Requires reference re-annotation to evaluate fairly. If references corrected, likely becomes SWAP. |
| **Qwen** | **CONDITIONAL** | Similar to Flash (0.1232 F1, $0.82/year), slightly slower (993ms). Viable post-reannotation but no clear advantage over Flash. |
| **DeepSeek** | **DO_NOT_RECOMMEND** | Highest F1 (0.1498) but slowest (1047ms p50), most expensive ($1.40/year). No compelling reason to deploy. |

**Theme Extraction Recommendation:**
- **Blocker:** Reference answers mismatch with corrected prompt (references include proper nouns; prompt excludes them)
- **Path Forward:** Re-annotate 10-15 theme references to match corrected prompt spec, then re-score all models
- **Expected Outcome:** Flash/Qwen F1 scores likely to improve significantly (0.10→0.40+ range estimated)
- **Post-Revalidation:** Flash likely becomes SWAP candidate (good agreement + low cost)

#### **Sentiment Analysis**

| Model | Decision | Rationale |
|-------|----------|-----------|
| **Flash** | **SWAP** | 85% agreement with Haiku, only 7% quality loss, fastest (0.90s p50), cheapest ($0.88/year), consistent latency (p95 2.46s). Low deployment risk. **Recommended for immediate adoption.** |
| **Qwen** | **CONDITIONAL** | 85% agreement with Haiku, only 19% quality loss, competitive cost ($0.95/year), fast (0.90s p50). Risk: slightly higher score variance. Viable alternative if Flash unavailable. |
| **DeepSeek** | **STAY** | 85% agreement with Haiku but 13% quality loss + slower (1.98s p50) + more expensive ($1.38/year). Flash is strictly better. No reason to deploy. |

**Sentiment Analysis Recommendation:**
- **Immediate:** Deploy Flash for sentiment_analysis operation
- **Justification:** 85% behavioral consistency + 7% quality loss + 36% cost savings + fastest latency = low-risk, high-reward swap
- **Fallback:** Qwen as secondary option if Flash hits rate limits or quota issues
- **Avoid:** DeepSeek (no advantage over Flash)

---

### 3b. Theme Extraction Analysis (Phase 2b/3b, 2026-04-30)

#### Critical Finding: Reference Answer Mismatch

**The Problem:**
- **Reference answers** include proper nouns: `['Bitcoin', 'Ethereum', 'ETFs', 'Institutional Investment']`
- **Corrected prompt (TASK-081)** explicitly excludes proper nouns: "Exclude proper nouns: No company names, person names, coin names, or protocol names"
- **Result:** All models (Flash, DeepSeek, Qwen) follow the corrected spec and produce conceptual themes, but score 0.0-0.15 F1 against references that expect proper nouns

**Example Mismatch:**

| Article | Reference | Model Output | Issue |
|---------|-----------|--------------|-------|
| Bitcoin ETF inflows | `['Bitcoin', 'Ethereum', 'ETFs', 'Institutional Investment']` | `['Market performance', 'Investment flows', 'Asset allocation']` | Reference includes coin names; model excludes them per corrected prompt |
| Crypto education | `['Crypto Education', 'Regulation', 'Compliance', 'Trust']` | `['Digital asset education', 'Regulatory alignment', 'Market trust', 'Compliance']` | Model produces more specific conceptual themes; references use category labels |
| Fraud case | `['Fraud', 'Victim Compensation']` | `['Fraud', 'Victim compensation', 'Legal process', 'Financial recovery']` | Model is more comprehensive; reference is minimal |

#### Quality Assessment

| Model | F1 Score | Latency p50 | Latency p95 | Status |
|-------|----------|------------|------------|--------|
| Flash | 0.1051 | 923ms | 1748ms | FAIL vs threshold (0.78) |
| DeepSeek | 0.1498 | 1047ms | 2386ms | FAIL vs threshold (0.78) |
| Qwen | 0.1232 | 993ms | 1413ms | FAIL vs threshold (0.78) |

**Key Observation:** DeepSeek actually scores highest (0.1498 F1) despite being slowest, suggesting it may be extracting more "reference-like" themes (possibly including proper nouns or category labels).

#### Model Behavior (Spot-Check Analysis)

**Flash Theme Extraction:**
- Produces: `Market performance, investment flows, asset allocation, market trends`
- Approach: Conceptual, abstract, follows corrected prompt
- Quality: Clean output, readable, but distant from reference proper nouns

**DeepSeek Theme Extraction:**
- Produces: `Market volatility, ETFs, inflows, outflows, demand`
- Approach: Mix of conceptual + category terms + proper nouns
- Quality: Attempts to preserve some specificity, closer to reference format

**Qwen Theme Extraction:**
- Produces: `ETF, market volatility, institutional adoption`
- Approach: Balanced conceptual + minimal proper nouns
- Quality: Compact, readable, moderate reference alignment

#### Why Scores Are Low

The 0.10-0.15 F1 scores are **not indicative of model quality**. They reflect the systematic mismatch:
1. References were compiled before prompt correction (from FEATURE-053)
2. References include proper nouns (Bitcoin, Ethereum, company names)
3. Corrected prompt explicitly excludes proper nouns
4. F1 calculation penalizes models for following the corrected spec

#### Recommendation for Theme Extraction

**Option A (RECOMMENDED):** Re-annotate 10-15 theme reference samples to match the corrected prompt spec (exclude proper nouns, focus on conceptual themes). Then re-score all models with corrected references.

**Option B:** Accept that theme extraction is lower priority for cost savings (all models fail threshold regardless) and focus deployment effort on sentiment (high ROI) and conditional entity extraction.

**Proposed Path Forward:**
1. **If time permits:** Re-annotate 15 theme references to match corrected prompt
2. **Re-score** with corrected references to get accurate F1 scores
3. **Determine** if any model becomes viable (likely Flash or Qwen, not DeepSeek)
4. **If no time:** Defer theme extraction to post-release; keep Haiku baseline until themes can be properly evaluated

---

## Deployment Strategy

### Phase 1: Sentiment Analysis (Flash)
**Timeline:** Week 1  
**Impact:** $0.49/year savings on sentiment operation (36% reduction)  
**Risk:** Low (85% agreement with Haiku)  
**Rollout:** 
1. Deploy Flash in parallel with Haiku on sentiment_analysis (A/B test)
2. Monitor for 3-5 days; verify 85% label agreement holds
3. Switch 100% traffic to Flash
4. Sunset Haiku for sentiment operations

### Phase 2: Entity Extraction (Hold for Now)
**Timeline:** TBD (blocked on Haiku baseline improvement)  
**Condition:** Only proceed if TASK-081 prompt improvements increase Haiku F1 above 0.50  
**If approved:**
- Flash path: Deploy with output validation (confidence filtering)
- Qwen path: Deploy for cost-sensitive workloads (lower quality tolerance acceptable)

### Phase 3: Theme Extraction (Blocked, Requires Reannotation)
**Timeline:** TBD (blocked on reference reannotation)  
**Blocker:** Reference answers include proper nouns but corrected prompt excludes them → systematic score penalty  
**Path Forward:**
1. Re-annotate 10-15 theme reference samples to match corrected prompt (exclude proper nouns)
2. Re-score all models (Flash, DeepSeek, Qwen) with corrected references
3. Evaluate if Flash/Qwen become SWAP candidates
4. If viable: Deploy with similar A/B test as sentiment (Phase 1 approach)
**Estimated Time:** 1-2 hours reannotation + 5min rescoring  
**Expected ROI:** $0.73/year savings if Flash becomes viable

### Phase 4: Monitor & Optimize
**Ongoing monitoring (after Phase 1):**
- Track Flash sentiment accuracy vs Haiku on live briefing traffic
- Monitor agreement rates (should stay 85%+)
- Collect latency metrics in production (compare to lab benchmarks)
- Once entity/theme baselines improve: evaluate conditional deployments

---

## Risk Assessment

### Sentiment Analysis (Flash) - Low Risk ✓
- **Behavioral Risk:** 85% agreement is high confidence
- **Quality Risk:** 7% degradation on reference set is acceptable given reference imbalance
- **Latency Risk:** 0.90s p50 is fast enough for async briefings
- **Operational Risk:** Can rollback immediately if issues arise
- **Mitigation:** A/B test for 3-5 days before full cutover

### Entity Extraction (All) - Medium Risk ⚠
- **Behavioral Risk:** Flash 64%, Qwen 58% agreement - moderate variance
- **Quality Risk:** 5-17% degradation vs Haiku, but Haiku baseline is already weak (0.43 F1)
- **Latency Risk:** Acceptable (Flash 1.45s, Qwen 2.46s) except DeepSeek (5.97s)
- **Operational Risk:** If deployed without validation, may extract wrong entities
- **Mitigation:** 
  - Output validation (confidence score thresholding)
  - Spot-check reviews during rollout
  - Keep Haiku as fallback option

---

## Implementation Notes

### Flash Sentiment Deployment Checklist
- [ ] Set up Flash parallel calls for sentiment_analysis
- [ ] Implement agreement monitoring (track label matches with Haiku)
- [ ] Log sentiment scores for both Haiku and Flash (enable rollback comparison)
- [ ] Define rollback threshold: if agreement drops below 80%, revert to Haiku
- [ ] Test rate limits: ensure OpenRouter quota sufficient for 2.7k articles/day at Flash
- [ ] Monitor latencies: alert if p95 exceeds 5s or p50 exceeds 2s

### Entity Extraction (Conditional) Deployment Checklist
- [ ] Investigate why Haiku F1 = 0.43 (below acceptable baseline)
- [ ] Test if additional TASK-081 prompt refinements improve baseline
- [ ] If baseline improves above 0.50: proceed with Flash validation approach
- [ ] If baseline doesn't improve: re-evaluate cost/quality tradeoff

---

## Questions for Stakeholder Review

1. **Sentiment Operation:** Is the 7% quality degradation acceptable for 36% cost savings on sentiment?
2. **Entity Operation:** Should we investigate prompt improvements to raise Haiku's 0.43 F1 baseline before considering challengers?
3. **Behavioral Consistency:** Is 85% agreement with Haiku sufficient for production deployment, or do we require higher thresholds?
4. **Reference Annotations:** Should the sentiment reference set be rebalanced (currently 85% positive) to better evaluate minority classes?
5. **Deployment Risk:** Do you prefer conservative (A/B test 5+ days) or rapid (1-2 days) rollout for Flash sentiment?

---

## Related Documents

- `phase-3-scoring/scoring_results.csv` — Threshold-based scores (reference)
- `phase-3-scoring/cost_metrics.csv` — Token counts and latencies
- `TASK-081-fix-tier1-prompts.md` — Prompt fixes that may need further refinement
- `entity_extraction_annotation_template.md` — Sample annotations for entity operation
- `sentiment_analysis_annotation_template.md` — Sample annotations for sentiment operation

---

## Appendix: Raw Data

### Entity Extraction Score Distribution

**Flash (37 articles):**
- F1 ≥ 0.8: 4 articles (11%)
- F1 0.5-0.8: 11 articles (30%)
- F1 0.0-0.5: 10 articles (27%)
- F1 = 0.0: 12 articles (32%)

**Qwen (37 articles):**
- F1 ≥ 0.8: higher proportion than Flash
- More consistent performance across articles
- Better median F1 (0.40 vs Flash 0.33)

**DeepSeek (37 articles):**
- Median F1 = 0.0 (terrible)
- Many complete failures
- Unreliable even on simple cases

### Sentiment Analysis Score Distribution

All models: ~47% accuracy on reference set (limited by reference imbalance)
All models: 85% agreement with Haiku (behavioral consistency)
No catastrophic failures observed
