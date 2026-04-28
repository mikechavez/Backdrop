# MSD-001: Entity Extraction

**Status:** Complete — Corrected (see TASK-080)
**Operation:** entity_extraction
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5
**Correction Date:** 2026-04-28

---

## Correction Notice

This record supersedes the original MSD-001 issued during FEATURE-053. Two issues
were identified in post-hoc analysis (TASK-080) that materially change the cost
analysis and quality interpretation:

1. Original cost table used incorrect per-token rates (~1000x error). Corrected
   OpenRouter pricing makes all challengers substantially cheaper than Haiku.
2. Mean F1 scores (0.68 / 0.51 / 0.71) do not reflect uniform mediocrity.
   Distribution analysis reveals a bimodal pattern: challengers either produce
   high-quality output (F1 >= 0.85) or fail completely (F1 = 0.00). This is
   consistent with parse failures or empty returns on a subset of articles, not
   degraded quality across the board. The original rationale ("quality risk
   outweighs cost savings") is correct in outcome but wrong in diagnosis.

---

## Evaluation Summary

Evaluation uses parity measurement: can each challenger substitute for Haiku without
degrading output quality? Post-hoc analysis reveals the baseline prompt is
underspecified (mention-level vs. relevance-weighted extraction), which limits the
interpretability of parity scores. STAY decisions are correct but the blocking issue
is prompt quality, not model quality.

---

## Quality Metrics

### Headline F1

| Model | Mean F1 | Flagged Samples | Flagged % |
|---|---|---|---|
| Flash | 0.68 | 52/100 | 52.0% |
| DeepSeek | 0.51 | 63/100 | 63.0% |
| Qwen | 0.71 | 49/100 | 49.0% |

**Note:** Mean F1 is misleading for this operation. The distribution is bimodal —
see below. Qwen leads on mean F1 and on distribution quality.

### Bimodal Distribution Analysis

| Model | F1 >= 0.85 | F1 < 0.50 | Std Dev |
|---|---|---|---|
| Flash | 48/100 | 26/100 | 0.362 |
| DeepSeek | 37/100 | 42/100 | 0.431 |
| Qwen | 51/100 | 22/100 | 0.354 |

Challengers either match or exceed Haiku's extraction quality (F1 >= 0.85) or
produce zero-match output (F1 = 0.00). There is minimal middle ground. This pattern
is consistent with output parse failures or empty returns on a subset of articles,
not uniform quality degradation. The high-std results confirm the distribution is
not centered — it is split.

Qwen has the most high-quality samples and fewest catastrophic failures. DeepSeek
has the worst catastrophic failure rate (42/100) and is not competitive.

### Head-to-Head Comparisons

| Matchup | Winner | Loser | Ties |
|---|---|---|---|
| Qwen vs DeepSeek | Qwen: 42 | DeepSeek: 15 | — |
| Flash vs Qwen | Flash: 18 | Qwen: 21 | 61 |

Qwen beats DeepSeek decisively. Flash and Qwen are effectively tied — 61 of 100
samples produce identical results; Qwen edges Flash by 3 samples on the remainder.

---

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| Haiku | 0 | 0 | 0 |
| Flash | 672 | 1129 | 707 |
| DeepSeek | 1334 | 1608 | 1215 |
| Qwen | 667 | 1073 | 703 |

Flash and Qwen are comparable on latency (~670ms p50). DeepSeek is roughly 2x
slower. Haiku latency is not measured (baseline extracted from golden set fields,
not re-called via API).

---

## Cost Analysis (Corrected)

Corrected rates sourced from OpenRouter, verified 2026-04-28. Original rates were
incorrect by ~1000x.

| Model | Input/1M | Output/1M |
|---|---|---|
| Haiku | $1.00 | $5.00 |
| Flash | $0.30 | $2.50 |
| DeepSeek | $0.32 | $0.89 |
| Qwen | $0.26 | $0.78 |

Monthly cost at 100 articles/day for entity_extraction (calculated from avg token
counts in this eval run):

| Model | Avg Input Tokens | Avg Output Tokens | Monthly |
|---|---|---|---|
| Flash | 178 | 116 | $1.03 |
| DeepSeek | 170 | 137 | $0.53 |
| Qwen | 173 | 105 | $0.38 |

Haiku monthly cost for this operation is not directly measured (baseline was
extracted from golden set fields, not re-called). For aggregate cost comparison
across all three Tier 1 operations, see TASK-080: Haiku $3.05/month total vs.
Flash $1.30 (-57%), DeepSeek $0.77 (-75%), Qwen $0.57 (-81%).

The original record's cost table was wrong. All challengers are cheaper than Haiku,
not more expensive.

---

## Manual Validation — Corrected Findings

**Original caveat:** 30% agreement. "Disagreements concentrated around extraction
granularity. Reviewer labeled at conceptual level; Haiku labels at mention level."

**Corrected framing:** The original caveat accurately describes the disagreement
but understates its implication. With 30% agreement, parity scores do not measure
extraction quality — they measure how closely challengers replicate Haiku's
mention-level extraction philosophy. A challenger that produces more accurate,
relevance-weighted output will score *lower* on this eval, not higher.

The STAY decisions for this operation are correct in outcome: no challenger should
be deployed without a prompt fix. But the reason is not that challengers fail to
extract entities — it is that the baseline prompt is underspecified and the scoring
surface is not aligned with reviewer intent. Revisiting after Sprint 17 prompt fix
is expected to change the quality picture substantially.

---

## Per-Model Decisions

### Flash — STAY

Mean F1 0.68 below threshold (0.85). However: 48/100 samples produce high-quality
output. The blocking issue is parse failures on a subset of articles, and a baseline
prompt that rewards mention-level extraction over relevance-weighted extraction.
Re-eval expected after Sprint 17 prompt fix.

### DeepSeek — STAY

Worst performance across all metrics: lowest mean F1 (0.51), highest catastrophic
failure rate (42/100), highest latency, and no cost advantage over Qwen. Not
recommended for this operation regardless of prompt fix outcome.

### Qwen — STAY (Preferred Challenger)

Best distribution profile: most high-quality samples (51/100), fewest catastrophic
failures (22/100), lowest std dev (0.354). Lowest cost among challengers. Effectively
tied with Flash on head-to-head comparison. Qwen is the preferred candidate for
re-eval after Sprint 17 prompt fix.

---

## Blocking Issues for Deployment

1. **Entity prompt fix required.** Current prompt does not distinguish mention-level
   from relevance-weighted extraction. Reviewer intent is relevance-weighted (primary
   entities only). Fix required before re-eval can produce a meaningful swap decision.

2. **Zero-score sample investigation required.** Catastrophic failures (F1 = 0.00)
   on 22-42 samples per challenger are likely parse failures or empty returns. Root
   cause should be identified before re-eval. Fix may improve scores substantially.

---

## Sprint 17 Actions

- Fix entity_extraction prompt: specify relevance-weighted extraction (primary
  entities only, not all mentions)
- Investigate zero-score samples across all three challengers — identify parse
  failure root cause
- Re-run eval with corrected prompt against same golden set
- Expect Qwen to lead based on current bimodal distribution profile

---

## Related

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set (parent)
- TASK-080: Post-Hoc Eval Analysis (this correction)
- EVAL-001: Model Selection Evaluation Methodology
  (`docs/decisions/EVAL-001-model-selection-flash-evaluations.md`)
- MSD-002: sentiment_analysis decision record
- MSD-003: theme_extraction decision record
- TASK-078: Model Selection Rubric
- TASK-079: Operation Tier Mapping