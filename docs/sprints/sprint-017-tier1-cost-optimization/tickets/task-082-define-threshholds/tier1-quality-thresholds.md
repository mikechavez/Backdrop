# TIER1 Quality Thresholds

**Date:** 2026-04-29  
**Sprint:** Sprint 17 — Tier 1 Cost Optimization  
**Task:** TASK-082  
**Status:** FINAL

---

## Overview

This document defines acceptable quality loss thresholds for each Tier 1 operation. These thresholds guide model selection in FEATURE-054 (Tier 1 Cost Optimization Evals) by establishing the minimum quality floor—the lowest score a challenger model can achieve while still being considered acceptable to deploy.

**Philosophy:** Threshold-based evaluation (not comparison-based). We are not asking "does Flash match Haiku?" We are asking "does Flash exceed the minimum acceptable quality for this operation?" This approach acknowledges that corrected baselines may not be perfect, and allows us to deploy cost-optimized models when their quality is good enough for the use case.

---

## Thresholds by Operation

### 1. Entity Extraction

| Metric | Value |
|--------|-------|
| **Threshold** | F1 >= 0.82 |
| **Acceptable Loss** | <3% |
| **User Impact** | High |
| **Rationale** | Entity extraction drives downstream narrative analysis and clustering. Extraction errors (false negatives: missing entities; false positives: noise entities) cascade through the briefing generation pipeline. Keep quality bar high to prevent cascade failures. 3% loss (~0.82 F1) preserves core narrative entities while allowing minor degradation. |

**Context:**
- Corrected baseline (from TASK-081): Haiku extracts primary/relevance-weighted entities only, not all mentions
- Errors manifest as: missing key entities in briefing, or including irrelevant entities that pollute clustering
- Cost impact: Entity extraction is ~15% of Tier 1 volume; even small optimizations add up

**Deployment Constraint:**
- If bimodal distribution discovered in Phase 4 (zero F1 on some articles), investigate root cause before deployment
- Spot-check failures must be systematic errors (fixable), not random quality gaps

---

### 2. Sentiment Analysis

| Metric | Value |
|--------|-------|
| **Threshold** | Accuracy >= 77% |
| **Acceptable Loss** | <8% |
| **User Impact** | Medium |
| **Rationale** | Sentiment is internal enrichment—not directly exposed to end users. Used for narrative classification and briefing tone hints. 77% accuracy is acceptable because: (1) sentiment misclassification doesn't break core narrative extraction; (2) internal enrichment tolerates more error than user-facing operations; (3) cost savings on sentiment are substantial (Flash is 57% cheaper than Haiku). 8% loss from corrected baseline allows conservative bias or neutral class drift. |

**Context:**
- Corrected baseline (from TASK-081): Neutral class now defined (-0.3 to 0.3 range for factual reporting without strong directional bias)
- TASK-081 validation showed: Neutral class definition working, but model being conservative (safe bias)
- Baseline accuracy expected to be ~85% on corrected prompts (vs. ~75% in FEATURE-053 due to better neutral definition)
- 77% threshold allows 8% loss from corrected baseline, targeting 77% overall accuracy

**Deployment Constraint:**
- No constraints—internal operation with high error tolerance
- Monitor for extreme bias (all neutral, all bullish) but unlikely with explicit neutral class

---

### 3. Theme Extraction

| Metric | Value |
|--------|-------|
| **Threshold** | Adjusted F1 >= 0.78 |
| **Acceptable Loss** | <5% |
| **User Impact** | Medium |
| **Rationale** | Themes structure the daily briefing (e.g., "Regulation", "Market Volatility", "Adoption"). Errors reduce briefing utility but don't break narrative extraction. Moderate tolerance for degradation because: (1) themes are secondary to entities and sentiment; (2) missing a theme doesn't prevent users from understanding the day's news; (3) extra themes clutter but don't confuse. 5% loss is conservative—reflects that theme quality directly affects briefing readability. |

**Context:**
- Corrected baseline (from TASK-081): Themes now conceptual only (exclude proper nouns, coin names)
- TASK-081 validation incomplete (test harness issue), but prompt is structurally correct
- Expected baseline: ~83% F1 on corrected prompts (after excluding entity names)
- 78% threshold allows 5% loss, targeting 78% F1 overall

**Deployment Constraint:**
- Requires successful Phase 1 validation (corrected Haiku baseline must be clear)
- If baseline is bimodal or unclear, defer theme extraction to Sprint 18 for deeper investigation

---

## Summary Table

| Operation | Threshold | User Impact | Acceptable Loss | Notes |
|-----------|-----------|-------------|-----------------|-------|
| **entity_extraction** | F1 >= 0.82 | High | <3% | Core to narrative extraction. Zero tolerance for cascade failures. |
| **sentiment_analysis** | Accuracy >= 77% | Medium | <8% | Internal enrichment. Conservative bias acceptable. |
| **theme_extraction** | Adjusted F1 >= 0.78 | Medium | <5% | Briefing structure. Missing themes acceptable, bimodal failures not. |

---

## How These Are Used

**Phase 3 (Threshold Scoring):**
- For each model (Flash, DeepSeek, Qwen) on each operation:
  - Calculate score (F1 or accuracy)
  - Compare against threshold (>= or <)
  - Mark as PASS or FAIL

**Phase 4 (Manual Analysis):**
- For models scoring near threshold (82.0–83.0 on entity extraction):
  - Spot-check 5–10 samples to assess failure mode quality
  - Determine if PASS is safe or if failure mode is blocking
- For operations with no models passing:
  - Investigate whether threshold is too strict or operation is genuinely hard to optimize
  - Flag for Sprint 18 investigation

---

## Provisional Nature

These thresholds are **provisional**. Phase 4 manual analysis may suggest revisions based on:
- Actual failure mode distribution (bimodal vs. normal)
- Cost impact significance (10% loss worth 90% cost savings?)
- User impact on briefing quality (detected through manual review)

If Phase 4 manual analysis recommends threshold adjustment, update this document and re-score Phase 3 results. Current thresholds are conservative starting points.

---

## Related Documents

- TASK-081: Fix Tier 1 Prompts (establishes corrected baselines)
- FEATURE-054: Tier 1 Cost Optimization Evals (uses these thresholds in Phase 3)
- EVAL-001: Model Selection Evaluation Methodology (scoring methodology)