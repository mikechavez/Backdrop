---
ticket_id: TASK-078
title: Model Selection Rubric — Write Decision Framework Document
priority: high
severity: medium
status: OPEN
date_created: 2026-04-27
effort_estimate: 2-3 hours
---

# TASK-078: Model Selection Rubric — Write Decision Framework Document

## Problem Statement

We need a generalizable framework for selecting models for any operation. This becomes both interview material and a template for future model decisions. The rubric must be written BEFORE operation tier mapping, so tier classifications can reference rubric dimensions.

---

## Task

### Deliverable

Create `docs/model-selection-rubric.md` with the following structure:

---

## 1. Operation Classification (5 Types)

Define what each type means, with examples from Backdrop:

| Type | Definition | Example |
|------|-----------|---------|
| **Extraction** | Parse structured content; deterministic output | entity_extraction, sentiment_analysis |
| **Synthesis** | Generate new content from inputs; quality-sensitive | narrative_generate, briefing_generate |
| **Critique** | Evaluate and judge; requires reasoning | briefing_critique, relevance_scoring |
| **Polish** | Refine existing content; minor transformations | narrative_polish, briefing_refine |
| **Agentic** | Multi-step reasoning with feedback loops | provider_fallback, cluster_narrative_gen |

### Key Insight
Classification drives tier assignment (see section 3 below).

---

## 2. Decision Dimensions (5 Axes)

For each operation, evaluate along these dimensions:

| Dimension | Description | High → Low |
|-----------|-------------|-----------|
| **Quality Requirement** | How critical is output quality to user experience? | Critical (briefing_generate) → Nice-to-have (relevance_scoring) |
| **Volume** | Call volume per day | High (sentiment_analysis: 100+) → Low (briefing_generate: 5-10) |
| **Latency Sensitivity** | Does response time matter? | Yes (real-time) → No (batch) |
| **Determinism** | Same input = same output? | Required (extraction) → Optional (synthesis) |
| **Failure Cost** | Cost of incorrect output | High (user-facing) → Low (internal) |

**How to use:**
- High quality requirement + user-facing → likely Tier 2 or 3
- High volume + deterministic → likely Tier 1 (candidate for Flash)
- Low quality requirement + high volume → likely Tier 1

---

## 3. Tiering Rules (4 Tiers)

### Tier 0: Rule-Replaceable
**Criteria:**
- Can be solved with regex, schema validation, or simple heuristics
- No LLM needed

**Model:** None (remove from LLM routing)

**Example:** Input validation, basic parsing

**Action:** Refactor to non-LLM implementation (out of scope for Sprint 16)

---

### Tier 1: Structured Extraction
**Criteria:**
- High volume (100+ calls/day)
- Deterministic output (same input = same output)
- Low failure cost (internal, non-critical)
- Extracting information from content (not generating new)

**Current Model:** claude-haiku-4-5-20251001

**Flash Evaluation Strategy:** Aggressive testing
- Full golden set evaluation
- Tight quality bar (exact match or high overlap)
- If cost savings > 20% AND no quality regression → approve swap

**Examples:** entity_extraction, sentiment_analysis, theme_extraction

---

### Tier 2: Structured Generation
**Criteria:**
- Medium volume (10-50 calls/day)
- Generation of new content (not pure extraction)
- User-facing or important to downstream processing
- Quality matters, but not safety-critical
- Some non-determinism acceptable (different valid outputs for same input)

**Current Model:** claude-haiku-4-5-20251001

**Flash Evaluation Strategy:** Cautious testing
- Smaller golden set (30-50 samples)
- Manual quality review (1-5 rating scale)
- Higher regression threshold (no >10% quality drops)
- If cost savings > 30% AND manual review approves → consider swap

**Examples:** narrative_generate (if cache miss, per TASK-075), narrative_theme_extract, cluster_narrative_gen

---

### Tier 3: Reasoning / Critique
**Criteria:**
- Low volume (< 10 calls/day)
- Requires multi-step reasoning or subjective judgment
- Safety-critical or user-facing quality gate
- Correctness is non-negotiable

**Current Model:** claude-haiku-4-5-20251001 (likely should upgrade to Sonnet in future)

**Flash Evaluation Strategy:** None (stay on premium)
- Do not test Flash for Tier 3 operations
- Document rationale: "Too critical for experimentation"
- Consider upgrading to claude-3-5-sonnet for quality

**Examples:** briefing_generate, briefing_critique, briefing_refine, provider_fallback

---

## 4. Override Conditions (When to Break Default Tier)

Even if an operation fits a tier, override if:

| Condition | Action | Example |
|-----------|--------|---------|
| Caching changes operation cost dramatically | Re-tier | narrative_generate + cache fix → cost drops 80% → Tier 1 candidate |
| Latency floor changes (< 100ms required) | Move up tier | Fast extraction becomes time-sensitive → Tier 2 minimum |
| Quality regression observed in prod | Move up tier | Flash swap caused 5% drop → revert to Haiku + log decision |
| New operation added | Classify then tier | New operation → starts at Tier 2 (conservative) |

---

## 5. Model Selection Algorithm

For any new operation, apply in order:

```
1. Classify operation type (extraction/synthesis/critique/polish/agentic)
2. Evaluate decision dimensions (quality, volume, latency, determinism, cost)
3. Assign tier (0, 1, 2, or 3)
4. Select default model:
   - Tier 0: None (non-LLM)
   - Tier 1: Haiku (aggressive Flash testing)
   - Tier 2: Haiku (cautious Flash testing)
   - Tier 3: Haiku (no testing, consider Sonnet upgrade)
5. Document decision rationale (becomes decision record input)
```

---

## 6. Interview / Positioning Notes

This rubric demonstrates:
- **Systematic thinking** about model selection (not ad-hoc)
- **Cost-quality tradeoff awareness** (knowing when to test vs. when not to)
- **Risk stratification** (Tier 3 ops have different rules than Tier 1)
- **Reproducibility** (anyone can follow this process for new operations)

Use this as talking points in interviews:
> "We classify operations by criticality and volume, then test Flash on low-risk high-volume operations. Tier 3 operations stay on premium because the failure cost is too high."

---

## Testing / Verification

- [ ] Rubric document is readable (one-page reference + tables)
- [ ] All 5 decision dimensions are clearly defined
- [ ] All 4 tiers have clear entrance criteria + Flash strategy
- [ ] At least 2 examples per tier (from real Backdrop operations)
- [ ] Override conditions are actionable (not vague)

---

## Acceptance Criteria

- [ ] docs/model-selection-rubric.md exists and is complete
- [ ] Rubric is one-pager + tables (printable / shareable)
- [ ] All 14 operations can be classified using this rubric
- [ ] Clear guidance on which tiers get Flash testing vs. not
- [ ] Ready for interview reference or Substack post (with light editing)

---

## Impact

- Provides framework for operation tier mapping (TASK-079)
- Becomes decision-making template for future model changes
- Interview material (demonstrates systematic thinking)
- Potential Substack content (model selection strategy)

---

## Related Tickets

- TASK-079 (Operation Tier Mapping uses this rubric)
- FEATURE-053 (Flash evaluations follow Tier 1/2 strategy)