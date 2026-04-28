# EVAL-001: Model Selection Evaluation Methodology
## Flash Evaluations — Tier 1 Operations

**Status:** Complete
**Sprint:** 16
**Date:** 2026-04-28
**Author:** FEATURE-053 / TASK-080

---

## Purpose

This document records the methodology, scoring contracts, decision framework, and
known limitations for the Tier 1 model selection evaluations completed in Sprint 16
(FEATURE-053). It is the permanent reference for interpreting the MSD-001/002/003
decision records and for reproducing or extending this evaluation in future sprints.

This document is distinct from the evaluation contract
(`docs/decisions/EVAL-001-evaluation-contract.md`), which defines the locked scoring
logic applied in Phase 5. This document covers the broader methodology: why the eval
was structured this way, what the results mean, and what the limitations are.

---

## Scope

**Operations evaluated (Tier 1):**

| Operation | MSD | Decision |
|---|---|---|
| entity_extraction | MSD-001 | STAY (all challengers) |
| sentiment_analysis | MSD-002 | CONDITIONAL (Flash preferred) |
| theme_extraction | MSD-003 | STAY (all challengers) |

**Challenger models evaluated:**

| Role | Model String |
|---|---|
| Primary target | `google/gemini-2.5-flash` |
| Challenger A | `deepseek/deepseek-chat` |
| Challenger B | `qwen/qwen-plus` |

**Baseline:** `anthropic/claude-haiku-4-5-20251001` (Haiku 4.5). Baseline output
was extracted from existing golden set fields — Haiku was not re-called via API.

**Infrastructure:** All challenger model calls via OpenRouter
(`https://openrouter.ai/api/v1`). OpenAI-compatible request format. Single HTTP
client across all models.

**Out of scope (Sprint 16):** Tier 2 operations (narrative_generate,
narrative_theme_extract, cluster_narrative_gen, narrative_polish,
insight_generation). Production routing changes. Haiku prompt improvements.

---

## Evaluation Approach

### Parity Measurement

The evaluation answers one question: *can each challenger substitute for Haiku
without degrading output quality?* This is parity measurement — not absolute quality
measurement. A challenger that produces objectively better output than Haiku but in
a different format or at a different level of granularity will score low under
parity measurement. This is intentional: the goal is drop-in substitution without
behavioral change.

**Implication:** Parity scores are only meaningful when the baseline is reliable.
For operations where manual validation reveals systematic baseline quality issues
(entity_extraction: 30% agreement; theme_extraction: 10% agreement), parity scores
measure baseline replication, not output quality. See Manual Validation section.

### Golden Set

Pre-extracted files at `/Users/mc/*.json`. Fixed inputs — golden set was not
re-queried from MongoDB during the evaluation.

| Operation | File | Samples |
|---|---|---|
| entity_extraction | `entity_extraction_golden.json` | 100 |
| sentiment_analysis | `sentiment_analysis_golden.json` | 100 |
| theme_extraction | `theme_extraction_golden.json` | 100 |

All samples use the same `_id` values across all model runs for reproducibility.

### Production Prompts

Challenger models used production prompts extracted verbatim from the codebase.
Prompts were not rewritten, summarized, or adjusted. This ensures challenger outputs
are evaluated under production conditions.

---

## Scoring Logic

Scoring logic is locked in `docs/decisions/EVAL-001-evaluation-contract.md`. Summary:

### entity_extraction

- **Metric:** F1 score (precision + recall harmonic mean) with alias normalization
- **Alias table:** ~20 common crypto entity aliases (fed→federal reserve,
  btc→bitcoin, u.s.→united states, etc.), version-controlled in scoring code
- **Sample regression flag:** F1 < 0.85
- **Operation flag:** > 5% of samples flagged

### sentiment_analysis

- **Metric:** Binary label match (100 if match, 0 if not)
- **Labels:** positive / negative / neutral (exact class match required)
- **Sample regression flag:** any mismatch
- **Operation flag:** > 5% of samples flagged

### theme_extraction

- **Metric:** Adjusted F1 with two-pass matching
  - Pass 1: normalized string match F1
  - Pass 2: ≥ 50% token overlap counts as match, score capped at 100
- **Sample regression flag:** adjusted F1 < 0.80
- **Operation flag:** > 5% of samples flagged

### Output Normalization

Applied before scoring (Phase 4). Without normalization, formatting differences
produce false regressions. Normalization covers: markdown code block stripping,
HTML stripping, lowercasing, punctuation removal, deduplication, and sorting. For
entity extraction, the `name` field is extracted from entity objects. For sentiment,
numeric scores are converted to labels.

---

## Decision Framework

Three outcomes per challenger per operation:

| Decision | Criteria |
|---|---|
| SWAP | Quality threshold met; cost savings justify latency increase |
| STAY | Quality threshold not met, or risk does not justify savings |
| CONDITIONAL | Threshold met under specific conditions only |

Decisions are data-driven. No outcome was assumed in advance.

**Quality thresholds (from eval contract):**

| Operation | Threshold | Metric |
|---|---|---|
| entity_extraction | F1 ≥ 0.85 | Mean F1 |
| sentiment_analysis | ≥ 75% accuracy | Label match rate |
| theme_extraction | F1 ≥ 0.80 | Adjusted mean F1 |

---

## Manual Validation

Manual validation was completed before the evaluation runs. Agreement was measured
by reviewing a sample of Haiku baseline outputs against reviewer judgment.

| Operation | Agreement | Implication |
|---|---|---|
| entity_extraction | 30% | Baseline uses mention-level extraction; reviewer uses relevance-weighted. Parity scores measure baseline replication, not quality. |
| sentiment_analysis | 80% | Normal variance. Two disagreements on genuine neutral/negative boundary cases. Baseline is trustworthy with caveat (see below). |
| theme_extraction | 10% | Systematic philosophy gap. Haiku includes entity names as themes; reviewer labels only conceptual themes. Parity scores are not meaningful for swap decisions. |

**Post-hoc correction to sentiment_analysis caveat (TASK-080):** The original 80%
agreement figure and "baseline is trustworthy" finding were partially revised.
Manual review of 12 specific samples (Flash=negative, Haiku=neutral) found Haiku
correct on 0/12, borderline on 3/12, and Flash correct on 9/12. Haiku has a
documented bias on crime/legal/regulatory/loss articles: it labels them neutral
when the dominant signal is negative. The 80% figure remains valid for the overall
distribution, but Haiku's reliability on the neutral class is lower than originally
assessed.

---

## Pricing Methodology

All costs are calculated from OpenRouter per-token rates applied to average token
counts per article observed in challenger model runs. Haiku token counts were not
captured (baseline extracted from golden set, not re-called); Haiku costs are
estimated from aggregate TASK-080 figures.

**Corrected rates (verified OpenRouter, 2026-04-28):**

| Model | Input/1M | Output/1M |
|---|---|---|
| Haiku | $1.00 | $5.00 |
| Flash | $0.30 | $2.50 |
| DeepSeek | $0.32 | $0.89 |
| Qwen | $0.26 | $0.78 |

**Note:** Original MSD-001/002/003 records used incorrect rates (~1000x error).
Corrected records supersede the originals. See TASK-080 for correction details.

**Monthly volume assumption:** 100 articles/day across all three Tier 1 operations
(3,000 articles/month per operation).

---

## Known Limitations and Open Issues

### Scorer Label Field Bug

The Phase 5 scoring harness hardcoded `flash_label` as the challenger label field
for all three scored files. DeepSeek and Qwen scored files contain `flash_label`
instead of `deepseek_label` / `qwen_label`. Accuracy totals (derived from the
`match` field) are correct. Per-class breakdowns are valid but the field naming is
misleading. Fix required before next eval run.

### Baseline Quality — Entity and Theme

With 30% manual validation agreement on entity_extraction and 10% on
theme_extraction, parity scores for these two operations measure baseline
replication rather than extraction quality. Sprint 17 prompt fixes are required
before re-eval results for these operations can support deployment decisions.

### Neutral Class Definition — Sentiment

The sentiment_analysis prompt does not define the neutral class. All three
challengers collapse to 4% accuracy on neutral articles (1/24). This is a prompt
problem. Strong positive (98%/98%/92%) and negative (96%/85%/92%) class performance
confirms the model can perform the task; the neutral failure is a missing definition,
not a model limitation.

### Haiku Neutral Bias — Sentiment

Haiku has a systematic bias on crime/legal/regulatory/loss articles: it labels them
neutral when the dominant signal is negative. This reduces the reliability of parity
scoring on the neutral class specifically. Flash's disagreements on this article type
appear to reflect higher accuracy, not lower.

### Entity Zero-Score Samples

Catastrophic failures (F1 = 0.00) on 22-42 samples per challenger in
entity_extraction are likely parse failures or empty returns, not genuine quality
failures. Root cause investigation is a Sprint 17 action.

---

## Sprint 16 Outputs

| Artifact | Location | Status |
|---|---|---|
| Eval contract | `docs/decisions/EVAL-001-evaluation-contract.md` | Locked |
| Phase 2 script | `scripts/phase_2_baseline_extraction.py` | Complete |
| Phase 3 script | `scripts/phase_3_challenger_models.py` | Complete |
| Phase 4 script | `scripts/phase_4_output_normalization.py` | Complete |
| Phase 5 script | `scripts/phase_5_scoring_harness.py` | Complete |
| Phase 6 script | `scripts/phase_6_decision_records.py` | Complete |
| Run outputs | `docs/decisions/msd-flash/runs/2026-04-28/` | Complete |
| MSD-001 (corrected) | `docs/decisions/MSD-001-entity_extraction.md` | Complete |
| MSD-002 (corrected) | `docs/decisions/MSD-002-sentiment_analysis.md` | Complete |
| MSD-003 (corrected) | `docs/decisions/MSD-003-theme_extraction.md` | Complete |
| This document | `docs/decisions/EVAL-001-model-selection-flash-evaluations.md` | Complete |

---

## Sprint 17 Handoff

**Actionable now (with constraint):**
Flash is the preferred challenger for sentiment_analysis. Deploy on non-critical
briefing paths after neutral class prompt fix and re-eval.

**Requires prompt fix before re-eval:**
- entity_extraction: specify relevance-weighted extraction; investigate zero-score
  parse failures; expect Qwen to lead
- theme_extraction: exclude proper nouns, company names, coin names from theme
  output; re-run manual validation before eval; full re-eval required

**Requires fix before next eval run:**
- Scorer label field bug: fix `flash_label` hardcoding in Phase 5 harness

---

## Related

- FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set
- TASK-080: Post-Hoc Eval Analysis — FEATURE-053 Findings Review
- EVAL-001 contract: `docs/decisions/EVAL-001-evaluation-contract.md`
- MSD-001: `docs/decisions/MSD-001-entity_extraction.md`
- MSD-002: `docs/decisions/MSD-002-sentiment_analysis.md`
- MSD-003: `docs/decisions/MSD-003-theme_extraction.md`
- TASK-078: Model Selection Rubric
- TASK-079: Operation Tier Mapping