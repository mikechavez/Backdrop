# MSD-001: Entity Extraction

**Status:** Complete
**Operation:** entity_extraction
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5

## Evaluation Summary

This decision record evaluates three challenger models (Flash, DeepSeek, Qwen) against Haiku baseline for entity_extraction. The evaluation uses parity measurement: can each challenger substitute for Haiku without users noticing a difference?


## Quality Metrics

| Model | Mean F1 | Flagged Samples | Flagged % |
|---|---|---|---|
| flash      | 0.68 |  52/100 |  52.0% |
| deepseek   | 0.51 |  63/100 |  63.0% |
| qwen       | 0.71 |  49/100 |  49.0% |

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| haiku      |        0 |        0 |        0 |
| flash      |      672 |     1129 |      707 |
| deepseek   |     1334 |     1608 |     1215 |
| qwen       |      667 |     1073 |      703 |

## Cost Analysis

| Metric | Haiku | Flash | DeepSeek | Qwen |
|---|---|---|---|---|
| Cost / 1k tokens | $0.8000 | $2.2500 | $0.0980 | $0.1200 | 
| Avg input tokens | 0 | 178 | 170 | 173 | 
| Avg output tokens | 0 | 116 | 137 | 105 | 

## Per-Model Decisions

### Flash

**STAY**

Mean F1 0.68 below threshold (0.85). Quality risk outweighs cost savings.

### Deepseek

**STAY**

Mean F1 0.51 below threshold (0.85). Quality risk outweighs cost savings.

### Qwen

**STAY**

Mean F1 0.71 below threshold (0.85). Quality risk outweighs cost savings.

## Manual Validation Caveat

Manual validation agreement: **30%**

Disagreements concentrated around extraction granularity. Reviewer labeled at conceptual level; Haiku labels at mention level. Haiku is internally consistent. Parity scores measure whether challengers match Haiku's mention-level philosophy. Prompt refinement deferred to Sprint 17.

## Recommendations

1. Review per-model decisions above
2. If SWAP: prepare rollout plan with gradual traffic shift
3. If CONDITIONAL: document specific constraints in code
4. If STAY: defer to Sprint 17 after prompt refinement
