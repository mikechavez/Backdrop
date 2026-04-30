# Model Selection Rubric
**Backdrop | Sprint 16 | Last updated: 2026-04-27**

> **How to use this document:** When adding a new operation or evaluating a model swap, work through Sections 1–3 in order. Section 4 handles exceptions. Section 5 is the condensed algorithm for quick reference.

---

## 1. Operation Classification (5 Types)

Every LLM operation in Backdrop falls into exactly one type. Classification is the first input to tier assignment.

| Type | Definition | Backdrop Examples |
|------|------------|-------------------|
| **Extraction** | Parse structured content; deterministic output expected | `entity_extraction`, `sentiment_analysis`, `theme_extraction`, `actor_tension_extract`, `relevance_scoring` |
| **Synthesis** | Generate new content from inputs; quality-sensitive | `narrative_generate`, `cluster_narrative_gen`, `insight_generation` |
| **Critique** | Evaluate and judge existing content; requires reasoning | `briefing_critique` |
| **Polish** | Refine existing content; minor transformations | `narrative_polish`, `briefing_refine`, `narrative_theme_extract` |
| **Agentic** | Multi-step reasoning with feedback loops or fallback logic | `briefing_generate`, `provider_fallback` |

**Key insight:** Classification is not decoration — it directly constrains tier assignment. Extraction operations are Tier 1 candidates by default. Agentic operations are Tier 3 by default. When classification is ambiguous, choose the higher-risk type.

---

## 2. Decision Dimensions (5 Axes)

After classifying an operation, evaluate it along five dimensions. No single dimension determines the tier — they combine.

| Dimension | Description | Scale |
|-----------|-------------|-------|
| **Quality Requirement** | How much does output quality affect user experience or downstream processing? | Critical → Nice-to-have |
| **Volume** | Approximate daily call volume at current Backdrop scale | High (100+/day) → Low (<10/day) |
| **Latency Sensitivity** | Does response time affect the user or pipeline? | Real-time required → Batch acceptable |
| **Determinism** | Is identical output expected for identical input? | Required → Optional |
| **Failure Cost** | What happens when the output is wrong? | User-facing degradation → Internal, invisible |

**Reading the dimensions together:**

- High volume + deterministic + low failure cost → **Tier 1 candidate** (aggressive Flash testing)
- Medium volume + generation + user-facing → **Tier 2 candidate** (cautious Flash testing)
- Low volume + reasoning required + high failure cost → **Tier 3** (no Flash testing; consider Sonnet upgrade)
- Any dimension flags critical failure cost → **do not test Flash regardless of other signals**

---

## 3. Tiering Rules

### Tier 0 — Rule-Replaceable
**Entrance criteria:**
- Can be fully solved with regex, schema validation, or simple heuristics
- LLM adds no value over a deterministic implementation

**Target model:** None — remove from LLM routing entirely

**Flash evaluation strategy:** N/A — refactor out of LLM layer

**Backdrop examples:** Input validation, basic parsing (none currently in `_OPERATION_ROUTING`; all 14 ops require LLM)

---

### Tier 1 — Structured Extraction
**Entrance criteria:**
- High volume (100+ calls/day)
- Deterministic output (same input should produce same output)
- Low failure cost (internal processing; user does not see raw output)
- Extracting or classifying existing information (not generating new content)

**Target model:** `claude-haiku-4-5-20251001` (current: Haiku on all ops)

**Flash evaluation strategy:** Aggressive
- Full golden set: 50–100 samples per operation
- Quality bar: exact match or high overlap (automated scoring acceptable)
- Regression threshold: flag any >5% quality drop
- Swap condition: cost savings >20% AND no quality regression → approve swap
- Decision record required (MSD-###)

**Backdrop operations in this tier:**
| Operation | Type | Rationale |
|-----------|------|-----------|
| `entity_extraction` | Extraction | High volume, deterministic, internal |
| `sentiment_analysis` | Extraction | High volume, deterministic, internal |
| `theme_extraction` | Extraction | High volume, deterministic, internal |
| `actor_tension_extract` | Extraction | High volume, deterministic, internal |
| `relevance_scoring` | Extraction | High volume, deterministic, internal |

**Sprint 16 scope note:** Flash evaluation in this sprint covers 3 of 5 Tier 1 operations (`entity_extraction`, `sentiment_analysis`, `theme_extraction`) due to time constraints. `actor_tension_extract` and `relevance_scoring` deferred to Sprint 17.

---

### Tier 2 — Structured Generation
**Entrance criteria:**
- Medium volume (10–50 calls/day)
- Generating new content (not pure extraction)
- User-facing or important to downstream processing
- Quality matters; some non-determinism is acceptable
- Not safety-critical

**Target model:** `claude-haiku-4-5-20251001` (current: Haiku on all ops)

**Flash evaluation strategy:** Cautious
- Smaller golden set: 30–50 samples
- Manual quality review required: 1–5 rating scale
- Regression threshold: no >10% quality drop (tighter bar than Tier 1 due to generation quality variance)
- Swap condition: cost savings >30% AND manual review approves → consider swap
- Decision record required (MSD-###)

**Backdrop operations in this tier:**
| Operation | Type | Rationale |
|-----------|------|-----------|
| `narrative_generate` | Synthesis | Medium volume; gated on cache investigation (TASK-075) |
| `narrative_theme_extract` | Polish | Medium volume; generation adjacent; downstream dependency |
| `cluster_narrative_gen` | Synthesis | Medium volume; generation; internal but quality-sensitive |
| `insight_generation` | Synthesis | Medium volume; generation; downstream dependency |
| `narrative_polish` | Polish | Low-medium volume; refinement; quality-sensitive |

**Sprint 16 scope note:** Tier 2 operations are explicitly out of Sprint 16 Flash evaluation scope. `narrative_generate` is additionally gated on TASK-075 (cache investigation). Tier 2 Flash evaluations deferred to Sprint 17.

---

### Tier 3 — Reasoning / Critique
**Entrance criteria:**
- Low volume (<10 calls/day)
- Requires multi-step reasoning, subjective judgment, or complex coordination
- Safety-critical or primary quality gate for user-facing output
- Correctness is non-negotiable; failure cost is high

**Target model:** `claude-3-5-sonnet` (current: `claude-haiku-4-5-20251001` — upgrade pending)

**Flash evaluation strategy:** None
- Do not test Flash on Tier 3 operations under any circumstances
- Rationale: failure cost too high; quality regression is not recoverable at this tier
- Upgrade path: evaluate Haiku → Sonnet before Flash is ever considered
- Decision record should document "stayed on premium — rationale: [operation] is Tier 3"

**Backdrop operations in this tier:**
| Operation | Type | Rationale |
|-----------|------|-----------|
| `briefing_generate` | Agentic | Primary user-facing output; low volume; correctness-critical |
| `briefing_critique` | Critique | Quality gate for briefings; reasoning required; low volume |
| `briefing_refine` | Polish | Operates on user-facing content post-critique; quality-critical |
| `provider_fallback` | Agentic | Fallback logic; failure here means no output at all |

**Note on current state:** All Tier 3 operations are currently routed to Haiku. This is a known gap. Sonnet upgrade is a separate decision and out of Sprint 16 scope.

---

## 4. Override Conditions

Even when an operation has been correctly classified and tiered, override the default if any of these apply:

| Condition | Action | Backdrop Example |
|-----------|--------|-----------------|
| Caching changes effective cost dramatically | Re-evaluate tier | `narrative_generate` cache fix (TASK-075) could drop cost 80% → re-tier as Tier 1 candidate |
| Quality regression detected in production | Move up one tier immediately | Flash swap causes >5% drop in `sentiment_analysis` → revert to Haiku; log MSD decision as STAY |
| New operation added | Default to Tier 2; classify explicitly before first deployment | Any new op starts cautious; do not assume Tier 1 without evaluation |
| Latency requirement tightens below 200ms | Move up tier | Extraction op becomes real-time requirement → Tier 2 minimum regardless of volume |
| Operation becomes user-facing after initial deployment | Re-evaluate immediately | Internal op promoted to briefing pipeline → reassess failure cost |

---

## 5. Model Selection Algorithm

For any new operation or model swap decision, apply in order:

```
1. CLASSIFY
   → What type is this operation?
      Extraction / Synthesis / Critique / Polish / Agentic

2. EVALUATE DIMENSIONS
   → Score each axis: Quality, Volume, Latency, Determinism, Failure Cost
   → Flag any dimension that indicates high failure cost → Tier 3 floor

3. ASSIGN TIER
   → Tier 0: Rule-replaceable (refactor out)
   → Tier 1: High volume + deterministic + low failure cost
   → Tier 2: Medium volume + generation + user-facing or downstream
   → Tier 3: Low volume + reasoning + high failure cost

4. SELECT MODEL
   → Tier 0: None
   → Tier 1: Haiku (aggressive Flash testing authorized)
   → Tier 2: Haiku (cautious Flash testing authorized)
   → Tier 3: Sonnet target (no Flash testing; Haiku is interim)

5. DOCUMENT DECISION
   → Write MSD-### decision record with:
      - Operation name
      - Classification + tier rationale
      - Model selected
      - Flash testing authorized? Y/N
      - If swap: data that justified it
      - If stay: rationale documented
```

**About Gemini Flash:** Flash evaluations test `gemini-2.5-flash` as a lower-cost alternative to `claude-haiku-4-5-20251001` on Tier 1 and Tier 2 operations. Flash is never tested on Tier 3 operations. Evaluation infrastructure uses deterministic MD5 bucketing via `RoutingStrategy` (BUG-090, TASK-076).

---

## All 14 Operations — Tier Summary

| Operation | Type | Tier | Flash Testing | Current Model | Target Model |
|-----------|------|------|---------------|---------------|--------------|
| `entity_extraction` | Extraction | 1 | Aggressive (Sprint 16) | Haiku | Haiku |
| `sentiment_analysis` | Extraction | 1 | Aggressive (Sprint 16) | Haiku | Haiku |
| `theme_extraction` | Extraction | 1 | Aggressive (Sprint 16) | Haiku | Haiku |
| `actor_tension_extract` | Extraction | 1 | Aggressive (Sprint 17) | Haiku | Haiku |
| `relevance_scoring` | Extraction | 1 | Aggressive (Sprint 17) | Haiku | Haiku |
| `narrative_generate` | Synthesis | 2 | Cautious (gated on TASK-075) | Haiku | Haiku |
| `narrative_theme_extract` | Polish | 2 | Cautious (Sprint 17) | Haiku | Haiku |
| `cluster_narrative_gen` | Synthesis | 2 | Cautious (Sprint 17) | Haiku | Haiku |
| `insight_generation` | Synthesis | 2 | Cautious (Sprint 17) | Haiku | Haiku |
| `narrative_polish` | Polish | 2 | Cautious (Sprint 17) | Haiku | Haiku |
| `briefing_generate` | Agentic | 3 | None | Haiku | Sonnet |
| `briefing_critique` | Critique | 3 | None | Haiku | Sonnet |
| `briefing_refine` | Polish | 3 | None | Haiku | Sonnet |
| `provider_fallback` | Agentic | 3 | None | Haiku | Sonnet |

---

*This document is the input to TASK-079 (operation tier mapping) and the framing reference for FEATURE-053 (Flash evaluations). Decision records produced by FEATURE-053 are filed as MSD-001+.*