# MSD-002: Sentiment Analysis

**Status:** Complete
**Operation:** sentiment_analysis
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5

## Evaluation Summary

This decision record evaluates three challenger models (Flash, DeepSeek, Qwen) against Haiku baseline for sentiment_analysis. The evaluation uses parity measurement: can each challenger substitute for Haiku without users noticing a difference?


## Quality Metrics

| Model | Accuracy | Flagged Samples | Flagged % |
|---|---|---|---|
| flash      |   75.0% |  25/100 |  25.0% |
| deepseek   |   72.0% |  28/100 |  28.0% |
| qwen       |   71.0% |  29/100 |  29.0% |

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| haiku      |        0 |        0 |        0 |
| flash      |      673 |     3249 |     1270 |
| deepseek   |     1373 |     1889 |     1310 |
| qwen       |      707 |     1180 |      775 |

## Cost Analysis

| Metric | Haiku | Flash | DeepSeek | Qwen |
|---|---|---|---|---|
| Cost / 1k tokens | $0.8000 | $2.2500 | $0.0980 | $0.1200 | 
| Avg input tokens | 0 | 98 | 99 | 107 | 
| Avg output tokens | 0 | 3 | 4 | 3 | 

## Per-Model Decisions

### Flash

**CONDITIONAL**

Accuracy 75% near threshold. Acceptable for non-critical paths only.

### Deepseek

**CONDITIONAL**

Accuracy 72% near threshold. Acceptable for non-critical paths only.

### Qwen

**CONDITIONAL**

Accuracy 71% near threshold. Acceptable for non-critical paths only.

## Manual Validation Caveat

Manual validation agreement: **80%**

Two mismatches on neutral/negative boundary on genuinely ambiguous articles. Label-level agreement is reliable. Baseline is trustworthy.

## Recommendations

1. Review per-model decisions above
2. If SWAP: prepare rollout plan with gradual traffic shift
3. If CONDITIONAL: document specific constraints in code
4. If STAY: defer to Sprint 17 after prompt refinement
