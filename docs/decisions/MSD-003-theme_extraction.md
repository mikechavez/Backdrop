# MSD-003: Theme Extraction

**Status:** Complete
**Operation:** theme_extraction
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5

## Evaluation Summary

This decision record evaluates three challenger models (Flash, DeepSeek, Qwen) against Haiku baseline for theme_extraction. The evaluation uses parity measurement: can each challenger substitute for Haiku without users noticing a difference?


## Quality Metrics

| Model | Mean F1 | Flagged Samples | Flagged % |
|---|---|---|---|
| flash      | 0.54 |  88/100 |  88.0% |
| deepseek   | 0.52 |  83/100 |  83.0% |
| qwen       | 0.57 |  87/100 |  87.0% |

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| haiku      |        0 |        0 |        0 |
| flash      |      620 |     1258 |      769 |
| deepseek   |     1375 |     1764 |     1299 |
| qwen       |      664 |     1058 |      707 |

## Cost Analysis

| Metric | Haiku | Flash | DeepSeek | Qwen |
|---|---|---|---|---|
| Cost / 1k tokens | $0.8000 | $2.2500 | $0.0980 | $0.1200 | 
| Avg input tokens | 0 | 94 | 97 | 101 | 
| Avg output tokens | 0 | 10 | 16 | 10 | 

## Per-Model Decisions

### Flash

**STAY**

Mean F1 0.54 below threshold (0.85). Quality risk outweighs cost savings.

### Deepseek

**STAY**

Mean F1 0.52 below threshold (0.85). Quality risk outweighs cost savings.

### Qwen

**STAY**

Mean F1 0.57 below threshold (0.85). Quality risk outweighs cost savings.

## Manual Validation Caveat

Manual validation agreement: **10%**

Systematic philosophy gap — Haiku includes entity names as themes; reviewer labeled only conceptual themes. Haiku is internally consistent. Interpret parity scores conservatively for this operation. Prompt refinement deferred to Sprint 17.

## Recommendations

1. Review per-model decisions above
2. If SWAP: prepare rollout plan with gradual traffic shift
3. If CONDITIONAL: document specific constraints in code
4. If STAY: defer to Sprint 17 after prompt refinement
