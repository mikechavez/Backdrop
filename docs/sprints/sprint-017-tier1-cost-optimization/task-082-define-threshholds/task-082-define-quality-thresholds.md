---
ticket_id: TASK-082
title: Define Quality Thresholds for Tier 1 Operations
priority: P1
severity: blocker
status: COMPLETE
date_created: 2026-04-28
date_completed: 2026-04-29
branch: feat/sprint-17-tier1-thresholds
effort_estimate: 1h
actual_effort: 1h
---

# TASK-082: Define Quality Thresholds for Tier 1 Operations

## Problem Statement

FEATURE-055 will evaluate challenger models (Flash, DeepSeek, Qwen) against corrected baselines. To determine pass/fail per model per operation, we need explicit quality thresholds. These thresholds define "acceptable quality loss" — how much degradation from Haiku is acceptable to justify cost savings.

**Important:** Thresholds are one dimension of the model decision. Final decision will depend on manual analysis (cost, latency, quality distribution, failure modes). Thresholds are provisional and may be revised based on Phase 4 findings.

---

## Task

Write one-page decision document defining provisional acceptable quality loss thresholds per Tier 1 operation. Thresholds should reflect user impact and business context, not hard rules.

---

## Thresholds

### Entity Extraction
**Operation:** `entity_extraction`  
**User Impact:** HIGH — Extracted entities drive narrative analysis, clustering, and briefing enrichment. Errors cascade.  
**Acceptable Quality Loss:** <3% (mean F1 score degradation)  
**Rationale:**
- Extraction errors directly impact entity-based analysis quality
- Missing or incorrect entities degrade downstream narrative understanding
- Briefing users rely on accurate entity tagging for context
- High bar justified by downstream risk

**Threshold Interpretation:**
- Haiku baseline F1: 0.85 (corrected baseline from Phase 1)
- Acceptable floor: 0.82 (0.03 loss)
- Challenger F1 >= 0.82 → PASS
- Challenger F1 < 0.82 → FAIL

---

### Sentiment Analysis
**Operation:** `sentiment_analysis`  
**User Impact:** MEDIUM — Sentiment is internal enrichment (briefing structure, user-facing summaries). Not user-facing primary signal.  
**Acceptable Quality Loss:** <8% (accuracy degradation)  
**Rationale:**
- Sentiment guides briefing tone and theme organization, not primary narrative
- Some error acceptable; errors affect briefing structure, not core facts
- Cost savings are material (67% cheaper with Flash)
- Medium tolerance justified by internal-only use

**Threshold Interpretation:**
- Haiku baseline accuracy: ~85% (corrected baseline from Phase 1)
- Acceptable floor: 77% (0.08 loss)
- Challenger accuracy >= 77% → PASS
- Challenger accuracy < 77% → FAIL

---

### Theme Extraction
**Operation:** `theme_extraction`  
**User Impact:** MEDIUM — Themes structure briefings and guide narrative summary organization. Important but not user-facing primary signal.  
**Acceptable Quality Loss:** <5% (adjusted F1 degradation)  
**Rationale:**
- Themes organize briefing structure; errors affect navigation, not facts
- More tolerant than entity extraction (downstream impact lower)
- Less tolerant than sentiment (more user-facing in briefings)
- Moderate tolerance justified by moderate impact

**Threshold Interpretation:**
- Haiku baseline adjusted F1: 0.82 (corrected baseline from Phase 1)
- Acceptable floor: 0.78 (0.04 loss, ~5%)
- Challenger adjusted F1 >= 0.78 → PASS
- Challenger adjusted F1 < 0.78 → FAIL

---

## Notes

### Provisional Status
These thresholds are **provisional**. FEATURE-055 Phase 4 manual analysis may reveal:
- Distribution patterns that justify tighter or looser thresholds
- Failure modes that change risk assessment
- Cost/latency tradeoffs that override threshold rules

If Phase 4 findings suggest revising thresholds, update this document and re-run analysis.

### Beyond Thresholds
Model selection will also consider:
- Cost savings (annual impact)
- Latency (p50, p95)
- Quality distribution (bimodal vs. consistent)
- Failure mode severity
- Manual spot-check results

A model may PASS threshold but not be recommended if cost savings are minimal or failure modes are concerning. A model may FAIL threshold but be conditional if confidence is high and savings are large.

### Contingencies
If manual validation of corrected prompts (TASK-086 spot-check) reveals different baseline quality:
- Recalculate thresholds against actual corrected baseline
- Do not change threshold philosophy, only absolute values

---

## Deliverable

Create file: `docs/decisions/TIER1-quality-thresholds.md`

Format:

```markdown
# TIER1 Quality Thresholds

**Status:** Provisional  
**Effective Date:** 2026-04-28  
**Review:** After FEATURE-055 Phase 4 (manual analysis)

## Summary Table

| Operation | Haiku Baseline | Acceptable Loss | Threshold Floor | Metric |
|---|---|---|---|---|
| entity_extraction | 0.85 | <3% | 0.82 | Mean F1 |
| sentiment_analysis | 85% | <8% | 77% | Accuracy |
| theme_extraction | 0.82 | <5% | 0.78 | Adjusted F1 |

## Per-Operation Details

[Include one section per operation with user impact, rationale, and interpretation]

## Notes

- Thresholds are provisional pending Phase 4 manual analysis
- Final model decisions depend on cost, latency, distribution, and failure modes — not just thresholds
- May be revised based on corrected baseline quality (TASK-086 spot-check results)
```

---

## Acceptance Criteria

- [x] Provisional thresholds defined for all three Tier 1 operations
- [x] User impact justified for each operation
- [x] Thresholds documented with clear pass/fail interpretation
- [x] Document specifies thresholds are provisional and may be revised after Phase 4
- [x] Document clarifies thresholds are one dimension, not sole decision driver
- [x] Deliverable written: `docs/sprints/sprint-017-tier1-cost-optimization/task-082-define-threshholds/tier1-quality-thresholds.md`

**Completion Notes:**
- All three thresholds finalized and documented with full rationale
- User impact clearly tied to downstream effects (entity extraction cascades; sentiment internal; theme structural)
- Acceptable loss percentages provisional and tied to business context, not arbitrary
- Document explicitly notes Phase 4 manual analysis may revise thresholds based on real failure modes
- Clear pass/fail interpretation per operation (F1 threshold for entity/theme, accuracy for sentiment)

---

## Impact

**Unblocks:** FEATURE-054 Phase 3 (threshold-based scoring) — scoring harness needs threshold values. ✅ READY

**Note:** Thresholds are inputs to Phase 4 analysis, not final decisions. Phase 4 manual analysis will validate or revise thresholds based on real data.

---

## Related Tickets

- TASK-081: Fix Tier 1 Prompts (prerequisite for baseline validation)
- FEATURE-054: Tier 1 Cost Optimization Evals (uses these thresholds in Phase 3)
- TASK-080: Post-Hoc Eval Analysis (identified quality issues)
- EVAL-001: Model Selection Evaluation Methodology