# MSD-002: Sentiment Analysis

**Status:** Complete — Corrected (see TASK-080)
**Operation:** sentiment_analysis
**Golden Set Size:** 100 samples
**Evaluation Date:** 2026-04-28
**Baseline Model:** Haiku 4.5
**Correction Date:** 2026-04-28

---

## Correction Notice

This record supersedes the original MSD-002 issued during FEATURE-053. Three issues
were identified in post-hoc analysis (TASK-080) that materially change the cost
analysis, per-class interpretation, and manual validation caveat:

1. Original cost table used incorrect per-token rates (~1000x error). Corrected
   OpenRouter pricing makes Flash 57% cheaper than Haiku, not more expensive.
2. Headline accuracy numbers (75%/72%/71%) obscure a complete neutral class collapse
   (4% across all challengers). This is a prompt problem, not a model problem.
3. Manual validation caveat was incorrect. Baseline is not fully trustworthy — Haiku
   has a documented bias on crime/legal/compensation articles.

---

## Evaluation Summary

Evaluation uses parity measurement: can each challenger substitute for Haiku without
degrading output quality? Post-hoc analysis reveals the baseline itself has a
systematic labeling bias, which limits the interpretability of parity scores for
neutral-class articles.

---

## Quality Metrics

### Headline Accuracy

| Model | Accuracy | Flagged Samples |
|---|---|---|
| Flash | 75.0% | 25/100 |
| DeepSeek | 72.0% | 28/100 |
| Qwen | 71.0% | 29/100 |

**Note:** Headline accuracy is misleading. All misses are concentrated in the neutral
class. Positive and negative class performance is strong across all challengers.

### Per-Class Breakdown

| Class | Distribution | Flash | DeepSeek | Qwen |
|---|---|---|---|---|
| Positive | 50/100 | 98% | 98% | 92% |
| Negative | 26/100 | 96% | 85% | 92% |
| Neutral | 24/100 | 4% | 4% | 4% |

All three challengers achieve 1/24 on the neutral class. The neutral class is
undefined in the current prompt — challengers have no signal for what distinguishes
neutral from negative or positive on crypto news articles.

### Neutral Misclassification Direction

| Model | neutral→negative | neutral→positive |
|---|---|---|
| Flash | 12 | 10 |
| DeepSeek | 7 | 16 |
| Qwen | 14 | 9 |

Flash and Qwen lean negative on neutral articles; DeepSeek leans positive. This is
consistent behavioral divergence, not random noise.

---

## Latency Analysis

| Model | p50 (ms) | p95 (ms) | avg (ms) |
|---|---|---|---|
| Haiku | 0 | 0 | 0 |
| Flash | 673 | 3249 | 1270 |
| DeepSeek | 1373 | 1889 | 1310 |
| Qwen | 707 | 1180 | 775 |

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

Monthly cost at 100 articles/day for sentiment_analysis:

| Model | Monthly | vs Haiku |
|---|---|---|
| Haiku | $0.339 | baseline |
| Flash | $0.111 | -67% |
| DeepSeek | $0.077 | -77% |
| Qwen | $0.057 | -83% |

Flash is 67% cheaper than Haiku at current volumes. The original record's conclusion
that Flash was more expensive than Haiku was incorrect.

---

## Scorer Bug — Label Field Naming

Post-hoc file inspection revealed the scorer hardcoded `flash_label` as the
challenger label field for all three scored files. DeepSeek and Qwen scored files
contain `flash_label`, not `deepseek_label` / `qwen_label`. Accuracy totals (derived
from the `match` field) are correct. Per-class breakdowns for DeepSeek and Qwen are
valid but the field naming is misleading. Fix required before next eval run.

---

## Manual Validation — Corrected Findings

**Original caveat (incorrect):** 80% agreement, "baseline is trustworthy."

**Corrected finding:** Manual review of the 12 samples where Flash=negative and
Haiku=neutral found Flash correct on 9/12, borderline on 3/12, and Haiku correct
on 0/12. Haiku has a documented bias: it labels crime/legal/regulatory/loss articles
as neutral when the dominant signal is negative (enforcement action, asset seizure,
market failure, trader liquidations).

Representative examples where Flash was correct and Haiku was not:
- CFTC probes oil futures trades tied to Trump/Iran moves (investigation framing)
- DeFi exploit $148M recovery plan, Circle pushback (exploit + loss framing)
- CFTC chair grilled by lawmakers on prediction markets (adversarial hearing)
- BTC tug of war, $137M in trader liquidations (loss framing)

The 12 Flash=negative disagreements likely represent Flash being more accurate than
Haiku on this article type, not less. This finding does not change the CONDITIONAL
decision but materially changes the reasoning.

---

## Per-Model Decisions

### Flash — CONDITIONAL (Preferred Challenger)

Flash is the preferred challenger for sentiment_analysis:
- Best accuracy (75%) among challengers
- Best negative class performance (96%)
- 67% cheaper than Haiku ($0.111/month vs $0.339/month)
- Neutral misclassification leans negative, consistent with article content

**Constraint:** Do not deploy before neutral class prompt fix. 4% neutral accuracy
will degrade briefing quality on crime/legal/regulatory articles, which are
disproportionately important in crypto news coverage.

### DeepSeek — STAY

No advantage over Flash on accuracy, cost, or latency. DeepSeek leans positive on
neutral articles (neutral→positive: 16), which is a less defensible error direction
for crypto news than Flash's negative lean. Not recommended for this operation.

### Qwen — CONDITIONAL (Secondary)

Comparable accuracy to Flash (71% vs 75%) with lower cost ($0.057/month). Neutral
misclassification leans negative (14) more strongly than Flash. May be worth
revisiting after neutral class prompt fix if Flash re-eval shows regression.

---

## Blocking Issues for Deployment

1. **Neutral class prompt fix required.** The prompt does not define neutral. Add
   explicit guidance distinguishing neutral from negative for regulatory, legal, and
   market-volatility articles. Re-eval after fix before any deployment.

2. **Scorer label field bug.** Fix `flash_label` hardcoding before next eval run so
   DeepSeek and Qwen results are correctly identified in scored files.

---

## Sprint 17 Actions

- Write neutral class definition into sentiment_analysis prompt
- Re-run eval (Flash primary, Qwen secondary)
- Deploy Flash on non-critical briefing paths after re-eval clears threshold
- Fix scorer label field naming bug

## Sprint 16 Closeout Actions

- Create EVAL-001 methodology record before Sprint 16 close
  (`docs/decisions/EVAL-001-model-selection-flash-evaluations.md`)

---

## Related

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set (parent)
- TASK-080: Post-Hoc Eval Analysis (this correction)
- MSD-001: entity_extraction decision record
- MSD-003: theme_extraction decision record
- TASK-078: Model Selection Rubric
- TASK-079: Operation Tier Mapping