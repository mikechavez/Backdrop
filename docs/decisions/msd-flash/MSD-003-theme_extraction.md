# MSD-003: Theme Extraction

**Status:** Complete — Corrected (see TASK-080)
**Operation:** theme_extraction
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5
**Correction Date:** 2026-04-28

---

## Correction Notice

This record supersedes the original MSD-003 issued during FEATURE-053. Two issues
were identified in post-hoc analysis (TASK-080) that materially change the cost
analysis and quality interpretation:

1. Original cost table used incorrect per-token rates (~1000x error). Corrected
   OpenRouter pricing makes all challengers substantially cheaper than Haiku.
2. The STAY rationale ("quality risk outweighs cost savings") is correct in
   outcome but wrong in diagnosis. Low parity scores do not indicate poor extraction
   quality — they indicate systematic philosophical divergence from a baseline that
   is internally consistent but misaligned with reviewer intent. With 10% manual
   validation agreement, parity scores cannot support a swap decision in either
   direction.

---

## Evaluation Summary

Evaluation uses parity measurement: can each challenger substitute for Haiku without
degrading output quality? Post-hoc analysis reveals this framing is not meaningful
for theme_extraction at this time. The baseline (Haiku) includes entity names, coin
names, and company names as themes; reviewers labeled only conceptual themes. A
single prompt change — excluding proper nouns and coin names from theme output — is
expected to substantially alter baseline behavior, requiring full re-eval before any
model decision can be made.

---

## Quality Metrics

### Headline F1

| Model | Mean F1 | Flagged Samples | Flagged % |
|---|---|---|---|
| Flash | 0.54 | 88/100 | 88.0% |
| DeepSeek | 0.52 | 83/100 | 83.0% |
| Qwen | 0.57 | 87/100 | 87.0% |

**Note:** These scores do not reflect output quality. They measure how closely
challengers replicate Haiku's entity-inclusive theme philosophy. Qwen produces the
highest scores and fewest low-scoring samples, but with 10% manual validation
agreement on the baseline, no swap decision is supportable from this data alone.

### Distribution Analysis

Score floor of 0.182 across all challengers confirms no catastrophic parse failures —
challengers are producing output on every article. Standard deviations of 0.178-0.216
indicate consistent, systematic divergence rather than the bimodal pattern observed
in entity_extraction. Challengers are uniformly producing conceptual themes while
Haiku produces entity-inclusive themes. This is a philosophy mismatch, not a
quality failure.

| Model | Mean F1 | Std Dev | Score Floor | Low Samples (<0.40) |
|---|---|---|---|---|
| Flash | 0.54 | ~0.21 | 0.182 | — |
| DeepSeek | 0.52 | ~0.18 | 0.182 | — |
| Qwen | 0.57 | ~0.18 | 0.182 | 10/100 |

Qwen leads on mean F1 and has the fewest low-scoring samples (10/100 below 0.40).

---

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| Haiku | 0 | 0 | 0 |
| Flash | 620 | 1258 | 769 |
| DeepSeek | 1375 | 1764 | 1299 |
| Qwen | 664 | 1058 | 707 |

Flash and Qwen are comparable (~640ms p50). DeepSeek is roughly 2x slower. Haiku
latency is not measured (baseline extracted from golden set fields, not re-called).

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

Monthly cost at 100 articles/day for theme_extraction (calculated from avg token
counts in this eval run):

| Model | Avg Input Tokens | Avg Output Tokens | Monthly |
|---|---|---|---|
| Flash | 94 | 10 | $0.16 |
| DeepSeek | 97 | 16 | $0.14 |
| Qwen | 101 | 10 | $0.10 |

Theme extraction is the lowest-cost operation for all models due to short output
length (~10-16 tokens per article). Haiku monthly cost for this operation is not
directly measured (baseline was extracted from golden set fields, not re-called).
For aggregate cost comparison across all three Tier 1 operations, see TASK-080:
Haiku $3.05/month total vs. Flash $1.30 (-57%), DeepSeek $0.77 (-75%), Qwen $0.57
(-81%).

---

## Manual Validation — Corrected Findings

**Original caveat:** 10% agreement. "Systematic philosophy gap — Haiku includes
entity names as themes; reviewer labeled only conceptual themes."

**Corrected framing:** The original caveat correctly identifies the gap but
understates its consequence. At 10% agreement, the parity scores generated in this
eval are not a reliable signal for any swap decision — they measure baseline
replication, not output quality. A challenger could produce objectively better themes
and score *lower* than one that mimics Haiku's entity-inclusive behavior.

The STAY decision is correct, but the correct reasoning is: **the baseline must be
fixed before any model decision is possible for this operation.** This is a higher
bar than the entity_extraction case, where the direction of re-eval is already
clear. For theme_extraction, we do not yet know what the corrected baseline will
look like or how challengers will compare against it.

---

## Per-Model Decisions

### Flash — STAY

F1 0.54 below threshold. Decision is correct but driven by baseline invalidity, not
demonstrated model failure. Re-eval required after Sprint 17 prompt fix.

### DeepSeek — STAY

No quality or cost advantage over Qwen. Higher latency. Not recommended for
re-eval unless Qwen shows unexpected regression after prompt fix.

### Qwen — STAY (Preferred for Re-Eval)

Best mean F1 (0.57), fewest low-scoring samples, lowest cost. If the baseline prompt
fix produces a defensible new baseline, Qwen should be the first candidate for
re-evaluation.

---

## Blocking Issues for Deployment

1. **Theme prompt fix required.** Current prompt produces entity-inclusive themes
   (proper nouns, coin names, company names). Reviewer intent is conceptual themes
   only. A prompt change excluding proper nouns and coin names will substantially
   change baseline behavior. Full re-eval required after fix — no model decision
   is possible from current data.

2. **Manual validation re-run required after prompt fix.** With 10% baseline
   agreement, the current golden set labels are not a reliable scoring surface.
   Manual validation should be re-run against the corrected baseline before re-eval
   results are used for deployment decisions.

---

## Sprint 17 Actions

- Fix theme_extraction prompt: exclude proper nouns, company names, and coin names
  from theme output
- Re-run manual validation against corrected baseline before eval
- Re-run eval with corrected prompt against same golden set
- Qwen is the recommended first candidate; re-run Flash as secondary

---

## Related

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set (parent)
- TASK-080: Post-Hoc Eval Analysis (this correction)
- EVAL-001: Model Selection Evaluation Methodology
  (`docs/decisions/EVAL-001-model-selection-flash-evaluations.md`)
- MSD-001: entity_extraction decision record
- MSD-002: sentiment_analysis decision record
- TASK-078: Model Selection Rubric
- TASK-079: Operation Tier Mapping