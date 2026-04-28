---
ticket_id: TASK-080
title: Post-Hoc Eval Analysis — FEATURE-053 Findings Review
priority: P2
severity: medium
status: OPEN
date_created: 2026-04-28
branch: feat/feature-053-tier1-flash-evals
effort_estimate: 1-2h
---

# TASK-080: Post-Hoc Eval Analysis — FEATURE-053 Findings Review

## Problem Statement

FEATURE-053 produced three decision records (MSD-001/002/003) based on aggregate
mean scores against fixed thresholds. Post-hoc analysis of the raw scored files and
manual validation data revealed three issues that meaningfully change how the results
should be interpreted:

1. **Pricing was wrong.** The MSD cost tables used incorrect per-token rates (off by
   ~1000x). Corrected OpenRouter pricing inverts the Flash conclusion — Flash is
   cheaper than Haiku on all three operations, not more expensive.

2. **Entity and theme evals measured the wrong thing.** Manual validation (30% and
   10% agreement respectively) revealed that Haiku's baseline behavior diverges
   systematically from reviewer intent. Parity scores measure whether challengers
   match Haiku's philosophy, not whether they produce better output. STAY decisions
   for these two operations are correct in outcome but the reasoning requires
   correction.

3. **Sentiment neutral class is a prompt problem, not a model problem.** All three
   challengers achieve 92-98% accuracy on positive and negative labels but collapse
   to 4% on neutral (1/24). The 75%/72%/71% headline accuracy numbers obscure this.
   The neutral class is undefined in the current prompt.

---

## Task

Document corrected findings across all three operations and update decision framing
for Sprint 17 handoff.

### Corrected Pricing (verified OpenRouter, 2026-04-28)

| Model | Input/1M | Output/1M |
|---|---|---|
| Haiku | $1.00 | $5.00 |
| Flash | $0.30 | $2.50 |
| DeepSeek | $0.32 | $0.89 |
| Qwen | $0.26 | $0.78 |

Monthly cost at 100 articles/day across all three Tier 1 operations:

| Model | Monthly | vs Haiku |
|---|---|---|
| Haiku | $3.05 | baseline |
| Flash | $1.30 | -57% |
| DeepSeek | $0.77 | -75% |
| Qwen | $0.57 | -81% |

### Entity Extraction — Corrected Interpretation

Mean F1 scores (Flash 0.68, DeepSeek 0.51, Qwen 0.71) appear to indicate consistent
mediocrity. Distribution analysis shows they are bimodal:

| Model | >=0.85 | <0.50 | Std |
|---|---|---|---|
| Flash | 48/100 | 26/100 | 0.362 |
| DeepSeek | 37/100 | 42/100 | 0.431 |
| Qwen | 51/100 | 22/100 | 0.354 |

Challengers either nail an article (F1 >= 0.85) or fail hard (F1 = 0.00). This
suggests output parse failures or empty returns on a subset of articles — not
uniform quality degradation. Qwen has the most perfect scores and fewest
catastrophic failures. Head-to-head: Qwen beats DeepSeek 42-15; Flash and Qwen
are essentially tied (18-21, 61 ties).

**Corrected decision rationale:** STAY is correct, but because the baseline prompt
is underspecified (mention-level vs. relevance-weighted), not because challenger
quality is uniformly poor. Re-eval required after Sprint 17 prompt fix.

### Sentiment Analysis — Corrected Interpretation

Per-class breakdown reveals the failure is concentrated entirely in the neutral class:

| Class | Distribution | Flash | DeepSeek | Qwen |
|---|---|---|---|---|
| Positive | 50/100 | 98% | 98% | 92% |
| Negative | 26/100 | 96% | 85% | 92% |
| Neutral | 24/100 | 4% | 4% | 4% |

The 24-26 `both_wrong` samples in head-to-head analysis are almost certainly all
neutral articles — challengers failing the same class systematically.

**Haiku bias finding:** Flash assigned `negative` to 12 articles Haiku labeled
`neutral`. Manual validation identified a Haiku bias on crime/legal/compensation
articles (Haiku calls them neutral; reviewer calls them negative). These 12
Flash disagreements may represent Flash being more accurate than Haiku, not less.
Requires manual review of the 12 sample IDs before closing.

**DeepSeek/Qwen label field gap:** Mismatch patterns show `neutral->?` for
DeepSeek and Qwen, meaning the `deepseek_label` / `qwen_label` fields were not
populated in the scored files. Accuracy totals are correct (from `match` field)
but per-class breakdown for these two models is unreliable.

**Corrected decision:** CONDITIONAL holds. Flash is the preferred challenger for
sentiment — best accuracy (75%), best negative class performance (96%), and
cost-justified at $0.111/month vs $0.339/month for Haiku. Neutral class requires
prompt fix before any deployment.

### Theme Extraction — Corrected Interpretation

Score floor of 0.182 across all challengers (vs. 0.000 in entity extraction)
confirms no catastrophic parse failures — challengers are producing output, just
diverging from Haiku's entity-inclusive theme philosophy. Std of 0.178-0.216
indicates consistent, systematic divergence rather than bimodal failure.

Qwen leads (mean 0.612, fewest <0.40 samples at 10/100). But with 10% manual
agreement on the baseline, these numbers are not meaningful for a swap decision.

**Corrected decision rationale:** STAY is correct. A single prompt change
(exclude proper nouns and coin names from theme output) will substantially change
baseline behavior, requiring full re-eval before any model decision.

---

## Verification

- [ ] Manually review 12 sample IDs where Flash=negative, Haiku=neutral
      (join `_id` from scored-sentiment_analysis-flash.jsonl to golden set)
- [ ] Confirm DeepSeek/Qwen label fields in scored sentiment files — determine
      whether `deepseek_label` / `qwen_label` were written or if scorer used
      generic `challenger_label`
- [ ] Confirm EVAL-001 meta-doc written and complete
      (`docs/decisions/EVAL-001-model-selection-flash-evaluations.md`)

---

## Acceptance Criteria

- [ ] Corrected pricing documented and propagated to MSD files or noted as
      correction in this ticket
- [ ] Entity bimodal distribution finding documented (not uniform mediocrity)
- [ ] Sentiment per-class breakdown documented (neutral class = prompt problem)
- [ ] 12 Haiku-neutral/Flash-negative samples reviewed and finding recorded
- [ ] Sprint 17 scope items derived from corrected findings (see Impact below)

---

## Impact

Corrected findings gate the following Sprint 17 decisions:

**Sentiment (actionable now, with constraint):**
- Flash is the preferred challenger — swap on non-critical paths after neutral
  class prompt fix
- Do not deploy before prompt fix; 4% neutral accuracy will degrade briefing
  quality on crime/legal articles

**Entity extraction (Sprint 17):**
- Fix prompt: specify relevance-weighted extraction (not mention-level)
- Re-run eval against corrected baseline
- Expect Qwen to lead based on current bimodal distribution
- Investigate zero-score samples — likely parse failures, fixable

**Theme extraction (Sprint 17):**
- Fix prompt: exclude proper nouns, company names, coin names from theme output
- Re-run eval against corrected baseline
- Full re-eval required before any model decision

**Cost framing:**
- Flash is 57% cheaper than Haiku — back in play for all Tier 1 operations
- Qwen is cheapest overall (81% cheaper) and leads on entity quality
- DeepSeek offers no advantage over Qwen on quality or cost for these operations

---

## Related Tickets

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set (parent)
- MSD-001: entity_extraction decision record
- MSD-002: sentiment_analysis decision record
- MSD-003: theme_extraction decision record
- TASK-078: Model Selection Rubric
- TASK-079: Operation Tier Mapping