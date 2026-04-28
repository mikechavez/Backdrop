# EVAL-001: Evaluation Contract — Flash Evaluations (FEATURE-053)

**Status:** Locked  
**Sprint:** 16  
**Date:** 2026-04-27  
**Author:** Mike Chavez  

---

## Purpose

This document defines the evaluation methodology for FEATURE-053: Flash Evaluations. It locks all scoring definitions, ground truth strategy, thresholds, and failure taxonomies **before any code is written or eval runs are executed**. All decisions are pre-committed to prevent post-hoc rationalization.

Nothing proceeds to implementation until this contract is signed off.

---

## Scope

**Sprint 16 (this contract):** Tier 1 operations only.

| Operation | Type |
|---|---|
| entity_extraction | Extraction |
| sentiment_analysis | Classification |
| theme_extraction | Extraction |

Tier 2 operations (narrative_generate, narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation) are out of scope for Sprint 16.

---

## Ground Truth Strategy

**Method:** Parity measurement. Haiku outputs from production (`haiku_output` field in `briefing_drafts` collection) are used as pseudo-ground-truth.

**What this means:** We are measuring whether Flash agrees with Haiku, not whether Flash is objectively correct. This is the appropriate tool for the question being asked: can Flash substitute for Haiku without users noticing a difference? The bar is Haiku, not perfection.

**Explicit caveat (to be stated in EVAL-001 meta-doc):**
> "Haiku outputs used as pseudo-ground-truth. This evaluation measures parity, not absolute accuracy. Manual ground truth was not constructed at scale — appropriate given that the user-facing quality baseline is already Haiku, and the decision is relative substitution, not absolute quality assessment."

**Manual validation layer:** A stratified spot-check of 30 samples (10 per operation) is performed before scoring runs to validate that Haiku is a trustworthy baseline. See Section: Manual Validation Step.

---

## Manual Validation Step

### Purpose

Confirm that Haiku outputs align with human judgment before using them as pseudo-ground-truth. Results inform confidence in parity interpretation but do not override it.

### Sampling

- 10 samples per operation (30 total)
- **Stratified:** ~5 typical samples + ~5 edge cases per operation
- Edge cases defined as: long articles, multiple entities, mixed sentiment, abstract themes
- Selection by quick skim — no formal process required

### Process

1. Pull 10 samples per operation from the golden set
2. Read the input article **only** — do not look at Haiku's output yet
3. Write your own label:
   - entity_extraction: list the entities you would extract
   - sentiment_analysis: positive, negative, or neutral
   - theme_extraction: list the themes you would assign
4. Compare your labels against Haiku's output
5. Score agreement using **identical scoring functions** as model outputs (F1 / binary — see Scoring Definitions)

> **Critical:** Manual labels must be scored using the exact same scoring functions as model outputs. No "close enough" judgment. If the scoring function says no match, it is no match.

### Single-Reviewer Limitation

Manual validation is performed by a single reviewer (Mike Chavez). This is a directional sanity check, not a statistically robust ground truth. Thresholds should be interpreted accordingly.

### Agreement Thresholds

| Agreement Rate | Interpretation | Action |
|---|---|---|
| ≥90% | Strong signal — Haiku is trustworthy baseline | Proceed with confidence. Note in EVAL-001. |
| 75–89% | Normal single-reviewer variance — not necessarily a Haiku problem | Proceed. Note caveat per operation in decision record. |
| <75% | Real red flag — Haiku baseline is unreliable for this operation | Flag operation. Interpret parity scores conservatively. Note prominently in EVAL-001. |

### What to Capture

For each operation:
- Agreement rate (%)
- 1–2 sentences on where disagreements cluster (e.g., "Disagreements concentrated in multi-entity sentences" or "Themes were consistently more abstract in Haiku outputs")

**Governing rule:** Manual validation results do not override parity results. They inform confidence in how parity scores are interpreted.

---

## Golden Set Definition

**Source:** `briefing_drafts` MongoDB collection, `haiku_output` field  
**Date range:** Last 7–14 days from eval run date  
**Sample size:** 50–100 samples per Tier 1 operation (150–300 total)  
**Stability:** Golden set is fixed at extraction time. Same `trace_ids` used for all eval runs to ensure reproducibility.

**Selection criteria:**
- Cover last 7–14 days
- Include edge cases (long inputs, multiple articles, high-volume clusters)
- Exclude samples with missing or invalid `haiku_output` fields

**Schema:**
```json
{
  "operation": "entity_extraction",
  "input_id": "trace_123abc",
  "input_text": "...",
  "articles": [],
  "timestamp": "2026-04-20T10:30:00Z",
  "haiku_output": {}
}
```

---

## Scoring Definitions

### entity_extraction

**Score type:** F1 (harmonic mean of precision and recall)

**What is being measured:**
- Precision: what fraction of Flash's extracted entities appear in Haiku's output
- Recall: what fraction of Haiku's entities Flash also caught
- F1: combined score between 0–100

**Match method:** Normalized string match (lowercase, strip punctuation) plus alias normalization.

**Alias normalization:** A lookup table of ~20 common entity aliases built from a quick scan of the golden set prior to scoring runs. Examples:
- "fed" → "federal reserve"
- "u.s." → "united states"

The alias table must be documented and version-controlled as part of the evaluation artifacts. This ensures reproducibility and prevents scoring drift between runs.

**Rationale for alias normalization:** Without it, "Fed" and "Federal Reserve" would score as a mismatch even though they refer to the same entity. This would systematically penalize Flash for being more precise, not less accurate.

**Hallucination handling:** Extra entities returned by Flash that do not match Haiku's output count against precision. No additional penalty multiplier — precision already captures hallucination.

**Sample score:** F1 × 100 (0–100 scale)

**Sample-level regression flag:** F1 score < 0.85

**Threshold rationale:** 0.85 chosen as a pragmatic threshold balancing tolerance for minor phrasing variation against material degradation. Haiku self-consistency not measured in Sprint 16 — flagged for Sprint 17 as a methodology improvement.

---

### sentiment_analysis

**Score type:** Binary label match

**What is being measured:** Does Flash return the same sentiment classification as Haiku? (positive / negative / neutral)

**Match method:** Exact class match. No partial credit.

**Adjacency logging:** If Haiku returns neutral and Flash returns positive (or vice versa), this is logged as an adjacent-class mismatch for diagnostic purposes. It still scores 0. Adjacent mismatches are not used to soften the operation-level pass/fail decision.

**Confidence scores:** If present in output, flag samples where label matches but confidence diverges by >0.2. Logged as diagnostic signal only.

**Sample score:** 100 if label matches, 0 if not.

**Sample-level regression flag:** Any label mismatch (score = 0)

**Rationale for strict binary:** sentiment_analysis is a Tier 1 operation that feeds downstream decisions. neutral vs. negative is not a harmless difference. Introducing partial credit makes metrics look better and conclusions harder to defend. Score binary, analyze nuance separately.

---

### theme_extraction

**Score type:** Adjusted F1 (two-pass)

**What is being measured:**
- Pass 1 — normalized string match F1 (same as entity_extraction, no alias table)
- Pass 2 — token overlap check: tokenize both outputs; if ≥50% token overlap between a Flash theme and a Haiku theme, count as match even if strings differ

**Rationale for token overlap:** Themes are semantic, not discrete. "Rising inflation concerns" and "inflation is increasing" express the same idea but share no 3-word consecutive string. Token overlap at ≥50% captures paraphrases without adding infrastructure.

**Match method:** Normalized string (Pass 1) + 50% token overlap (Pass 2). Pass 2 adjusts the F1 score upward for near-matches. Score capped at 100.

**Sample score:** Adjusted F1 × 100 (0–100 scale)

**Sample-level regression flag:** Adjusted F1 < 0.80

**Rationale for lower threshold (0.80 vs 0.85):** Semantic variation in theme labeling is expected even between identical-quality models. A slightly more lenient threshold avoids penalizing Flash for legitimate paraphrase.

---

## Operation-Level Pass/Fail Gates

An operation is flagged for regression if **either** condition is met:

| Condition | Gate |
|---|---|
| Proportion of flagged samples | >5% of samples exceed sample-level regression threshold |
| Mean score delta vs. Haiku | Mean F1 / agreement drops by a material amount (TBD after baseline data — field required in all reporting) |

Both fields must appear in every comparison table. The mean delta field is required even if a threshold is not yet committed for it.

**Decision outcome vocabulary:**
- **SWAP** — Flash meets quality threshold, cost savings justify latency increase
- **STAY** — Flash does not meet quality threshold, or cost savings do not justify risk
- **CONDITIONAL** — Flash meets threshold under specific conditions (e.g., acceptable for batch processing, not real-time)

Decisions must emerge from data. No outcome is assumed in advance.

---

## Cost Metrics Format

All decision records (MSD-001 through MSD-003) must include cost metrics in the following format:

| Metric | Haiku | Flash | Delta |
|---|---|---|---|
| Cost / 1k tokens | $X.XX | $X.XX | -X% |
| Avg input tokens | N | N | |
| Avg output tokens | N | N | |
| Estimated cost / day @ current volume | $X.XX | $X.XX | |
| Estimated annual savings (if swapped) | — | ~$X,XXX | |

Latency must also be reported:

| Metric | Haiku | Flash | Delta |
|---|---|---|---|
| p50 latency (ms) | N | N | +X% |
| p95 latency (ms) | N | N | +X% |

---

## Failure Mode Taxonomy

Applied to worst 10 samples per operation after eval runs complete. Tagging is done before writing decision records. Tags are defined upfront to prevent inconsistent post-hoc labeling.

### entity_extraction
- `missed_entity` — Flash failed to extract an entity Haiku caught
- `extra_entity` — Flash returned an entity Haiku did not (hallucination)
- `alias_mismatch` — Flash used a different surface form for the same entity (not caught by alias table)
- `boundary_error` — Flash extracted a partial span (e.g., "Powell" vs. "Jerome Powell")

### sentiment_analysis
- `polarity_flip` — Flash returned opposite polarity (positive ↔ negative)
- `neutral_misclassification` — Flash returned neutral when Haiku returned positive or negative, or vice versa
- `low_confidence_divergence` — Labels match but confidence scores diverge by >0.2

### theme_extraction
- `semantic_miss` — Flash missed a theme entirely (no overlap even after token matching)
- `overgeneralized` — Flash returned a broader theme where Haiku was more specific
- `overly_specific` — Flash returned a narrower theme where Haiku was more general
- `phrasing_mismatch` — Same concept, different framing (below token overlap threshold)

---

## Reproducibility Requirements

- Golden set extraction query documented with date range and filters
- Same `trace_ids` used for all eval runs (Haiku baseline and Flash variant)
- Alias table version-controlled alongside scoring code
- Eval scripts must accept golden set path as input parameter (no hardcoded paths)
- All outputs written to dated output directory

---

## Evaluation Gate

**Nothing proceeds to Claude Code implementation until:**

- [x] Scoring definitions locked (this document)
- [x] Ground truth strategy locked (parity, explicitly stated)
- [x] Alias table approach defined (built from golden set scan)
- [x] Failure taxonomy defined
- [x] Pass/fail thresholds defined
- [x] Cost metric format defined
- [ ] Manual validation sample completed (10 per op, 30 total)
- [ ] Golden set extracted from MongoDB and reviewed
- [ ] Manual validation agreement rates reviewed and documented

---

## What This Contract Does Not Decide

- Whether to swap any operation to Flash (that is the job of MSD-001 through MSD-003, based on data)
- Tier 2 operation evaluation (deferred to Sprint 17)
- Production routing changes (deferred until after decision records approved)

---

## Related Artifacts

| Artifact | Purpose |
|---|---|
| EVAL-001-model-selection-flash-evaluations.md | Meta evaluation report — findings, methodology, interview narrative |
| MSD-001-entity_extraction.md | Per-operation decision record |
| MSD-002-sentiment_analysis.md | Per-operation decision record |
| MSD-003-theme_extraction.md | Per-operation decision record |
| FEATURE-053 ticket | Full feature spec and implementation notes |
| TASK-078 | Model Selection Rubric |
| TASK-079 | Operation Tier Mapping |