# Operation Tier Mapping
**Backdrop | Sprint 16 | Last updated: 2026-04-27**

> **How to use this document:** This is the tier assignment for all 14 LLM operations using the Model Selection Rubric (TASK-078). Use the summary tables below to determine Flash evaluation scope (FEATURE-053) and prioritization. Tier 3 operations are out of Flash scope; Tier 1/2 operations are candidates depending on volume and risk profile.

---

## All 14 Operations — Tier Assignment Summary

| Operation | Type | Tier | Quality | Volume | Latency | Determinism | Failure Cost | Flash Testing | Priority |
|-----------|------|------|---------|--------|---------|-------------|--------------|---------------|----------|
| `entity_extraction` | Extraction | 1 | Medium | High (100+/day) | No | High | Low | YES (Sprint 16) | 1st |
| `sentiment_analysis` | Extraction | 1 | Medium | High (150+/day) | No | High | Low | YES (Sprint 16) | 1st |
| `theme_extraction` | Extraction | 1 | Medium | High (120+/day) | No | High | Low | YES (Sprint 16) | 1st |
| `actor_tension_extract` | Extraction | 1 | Medium | High (80+/day) | No | High | Low | YES (Sprint 17) | 2nd |
| `relevance_scoring` | Extraction | 1 | Medium | High (200+/day) | No | High | Low | YES (Sprint 17) | 2nd |
| `narrative_generate` | Synthesis | 2 | High | Medium (20-30/day) | No | Low | High | PENDING (gated on TASK-075) | 2nd (if cache miss) |
| `narrative_theme_extract` | Polish | 2 | High | Medium (30-40/day) | No | Low | Medium | YES (Sprint 17) | 3rd |
| `cluster_narrative_gen` | Synthesis | 2 | High | Medium (15-20/day) | No | Low | Medium | YES (Sprint 17) | 3rd |
| `insight_generation` | Synthesis | 2 | High | Medium (10-15/day) | No | Low | High | YES (Sprint 17) | 4th |
| `narrative_polish` | Polish | 2 | Medium | Medium (30-40/day) | No | Medium | Medium | YES (Sprint 17) | 4th |
| `briefing_generate` | Agentic | 3 | Critical | Low (5-10/day) | No | Low | Critical | NO | — |
| `briefing_critique` | Critique | 3 | Critical | Low (2-3/day) | No | Low | Critical | NO | — |
| `briefing_refine` | Polish | 3 | Critical | Low (3-5/day) | No | Low | Critical | NO | — |
| `provider_fallback` | Agentic | 3 | Critical | Low (0-5/day) | Yes | Low | Critical | NO | — |

---

## Tier 1 — Structured Extraction (5 operations)

**Tier 1 Criteria (from Rubric):**
- High volume (100+ calls/day)
- Deterministic output (same input = same output)
- Low failure cost (internal processing; user does not see raw output)
- Extracting or classifying existing information (not generating new content)

**Flash Evaluation Strategy:** Aggressive
- Full golden set: 50–100 samples per operation
- Quality bar: exact match or high overlap (automated scoring acceptable)
- Regression threshold: flag any >5% quality drop
- Swap condition: cost savings >20% AND no quality regression → approve swap

### Tier 1 Operations

#### 1. `entity_extraction` — Extraction
- **Volume:** 100+ calls/day (feeds all downstream entity pipelines)
- **Determinism:** High (entity names + types deterministic from content)
- **Failure Cost:** Low (internal; used for signal clustering, not user-visible)
- **Quality Requirement:** Medium (accuracy matters for clustering but not critical)
- **Rationale:** Highest priority Tier 1 candidate. Pure extraction, high volume, low risk. Cost driver: ~$0.15/day.
- **Flash Testing:** YES (Sprint 16 Phase 1)
- **Priority:** 1st (parallel)

#### 2. `sentiment_analysis` — Extraction
- **Volume:** 150+ calls/day (sentiment on all articles + narratives)
- **Determinism:** High (sentiment labels deterministic)
- **Failure Cost:** Low (internal; used for narrative context, not user-facing)
- **Quality Requirement:** Medium (directional accuracy sufficient)
- **Rationale:** Highest volume Tier 1 operation. Deterministic labeling. Excellent Flash candidate due to volume.
- **Flash Testing:** YES (Sprint 16 Phase 1)
- **Priority:** 1st (parallel)

#### 3. `theme_extraction` — Extraction
- **Volume:** 120+ calls/day (themes from articles + narratives)
- **Determinism:** High (theme names deterministic from content)
- **Failure Cost:** Low (internal; used for signal enrichment)
- **Quality Requirement:** Medium (accuracy improves clustering but not critical)
- **Rationale:** High volume, deterministic, internal use only. Part of Sprint 16 core eval scope.
- **Flash Testing:** YES (Sprint 16 Phase 1)
- **Priority:** 1st (parallel)

#### 4. `actor_tension_extract` — Extraction
- **Volume:** 80+ calls/day (tension relationships from articles)
- **Determinism:** High (relationships deterministic from text)
- **Failure Cost:** Low (internal signal enrichment)
- **Quality Requirement:** Medium (relationship detection accuracy matters but not critical)
- **Rationale:** Tier 1 by criteria. Deferred from Sprint 16 to Sprint 17 due to scope (5 Tier 1 ops, 3-op sprint limit).
- **Flash Testing:** YES (Sprint 17 Phase 1b)
- **Priority:** 2nd

#### 5. `relevance_scoring` — Extraction
- **Volume:** 200+ calls/day (highest volume operation; relevance on all articles)
- **Determinism:** High (relevance scores deterministic)
- **Failure Cost:** Low (internal; used for article ranking, not user-facing)
- **Quality Requirement:** Medium (directional scoring sufficient)
- **Rationale:** Highest call volume of any operation. Deterministic scoring. Cost driver opportunity. Deferred to Sprint 17 due to scope.
- **Flash Testing:** YES (Sprint 17 Phase 1b)
- **Priority:** 2nd

**Sprint 16 Tier 1 Scope:** 3 of 5 operations (entity_extraction, sentiment_analysis, theme_extraction) due to time constraints. actor_tension_extract and relevance_scoring deferred to Sprint 17.

---

## Tier 2 — Structured Generation (5 operations)

**Tier 2 Criteria (from Rubric):**
- Medium volume (10–50 calls/day)
- Generating new content (not pure extraction)
- User-facing or important to downstream processing
- Quality matters; some non-determinism is acceptable
- Not safety-critical

**Flash Evaluation Strategy:** Cautious
- Smaller golden set: 30–50 samples
- Manual quality review required: 1–5 rating scale
- Regression threshold: no >10% quality drop (tighter bar than Tier 1 due to generation quality variance)
- Swap condition: cost savings >30% AND manual review approves → consider swap

### Tier 2 Operations

#### 1. `narrative_generate` — Synthesis
- **Volume:** 20–30 calls/day (depends on clustering activity)
- **Determinism:** Low (generation; same input may produce different valid outputs)
- **Failure Cost:** High (generated narrative is key briefing component; bad output affects user experience)
- **Quality Requirement:** High (user-facing; briefing quality depends on narrative quality)
- **Rationale:** Core briefing component; high quality requirement. **PENDING TASK-075 decision:** If cache hit rate improves substantially (>50%), cost model changes and may drop to Tier 1. If cache miss confirmed, is cost + quality-sensitive Tier 2 candidate.
- **Flash Testing:** PENDING (gated on TASK-075 cache investigation)
- **Priority:** 2nd (if cache miss confirmed in TASK-075)
- **Decision Gate:** TASK-075 determines whether to include in Phase 2

#### 2. `narrative_theme_extract` — Polish
- **Volume:** 30–40 calls/day (theme narratives for each cluster)
- **Determinism:** Low (generation-adjacent; extracts themes from narratives, minor variability)
- **Failure Cost:** Medium (feeds into briefing; poor extraction affects narrative quality)
- **Quality Requirement:** High (theme summaries are user-visible in briefings)
- **Rationale:** Downstream of narrative_generate; quality matters for user experience. Generation-adjacent makes it Tier 2.
- **Flash Testing:** YES (Sprint 17 Phase 2)
- **Priority:** 3rd

#### 3. `cluster_narrative_gen` — Synthesis
- **Volume:** 15–20 calls/day (narrative per cluster)
- **Determinism:** Low (generation; multiple valid narratives per cluster)
- **Failure Cost:** Medium (internal narrative creation; impacts quality but not user-facing)
- **Quality Requirement:** High (narrative quality affects downstream briefing quality)
- **Rationale:** Narrative generation from cluster signals. Quality-sensitive, medium volume. Tier 2 by criteria.
- **Flash Testing:** YES (Sprint 17 Phase 2)
- **Priority:** 3rd

#### 4. `insight_generation` — Synthesis
- **Volume:** 10–15 calls/day (insights from trending narratives)
- **Determinism:** Low (generation; novel insights vary per input)
- **Failure Cost:** High (user-facing insights in briefing; poor insights reduce briefing value)
- **Quality Requirement:** High (user expects novel, actionable insights)
- **Rationale:** Low volume but high quality requirement and user-facing. Tier 2 by criteria.
- **Flash Testing:** YES (Sprint 17 Phase 2)
- **Priority:** 4th

#### 5. `narrative_polish` — Polish
- **Volume:** 30–40 calls/day (polish narratives before briefing)
- **Determinism:** Medium (refinement has some variability but constrained by input)
- **Failure Cost:** Medium (user-facing narrative quality matters)
- **Quality Requirement:** Medium (refinement helps but not critical to core narrative)
- **Rationale:** Medium volume, medium quality requirement. Polish operations are Tier 2 by type classification.
- **Flash Testing:** YES (Sprint 17 Phase 2)
- **Priority:** 4th

**Sprint 16 Tier 2 Scope:** Out of scope. TASK-075 (narrative_generate cache) runs in parallel and determines Sprint 17 Tier 2 evaluation priority.

---

## Tier 3 — Reasoning / Critique (4 operations)

**Tier 3 Criteria (from Rubric):**
- Low volume (<10 calls/day)
- Requires multi-step reasoning, subjective judgment, or complex coordination
- Safety-critical or primary quality gate for user-facing output
- Correctness is non-negotiable; failure cost is high

**Flash Evaluation Strategy:** None
- Do not test Flash on Tier 3 operations under any circumstances
- Rationale: failure cost too high; quality regression is not recoverable at this tier
- Upgrade path: evaluate Haiku → Sonnet before Flash is ever considered
- Decision record should document "stayed on premium — rationale: [operation] is Tier 3"

### Tier 3 Operations

#### 1. `briefing_generate` — Agentic
- **Volume:** 5–10 calls/day (briefing generation, 2× daily)
- **Determinism:** Low (multi-step orchestration; varies based on input narratives)
- **Failure Cost:** Critical (primary user-facing deliverable; bad briefing causes user-visible degradation)
- **Quality Requirement:** Critical (entire briefing value depends on this step)
- **Rationale:** Core user deliverable. Requires multi-step reasoning and fallback coordination. Correctness non-negotiable. Never test Flash.
- **Flash Testing:** NO
- **Note:** Consider Sonnet upgrade (separate decision, out of Sprint 16 scope)

#### 2. `briefing_critique` — Critique
- **Volume:** 2–3 calls/day (critique each briefing after generation)
- **Determinism:** Low (subjective quality judgment)
- **Failure Cost:** Critical (quality gate; if critique fails, bad briefing reaches users)
- **Quality Requirement:** Critical (serves as final validation before delivery)
- **Rationale:** Quality gate operation. Requires subjective judgment and multi-step reasoning. Failure means bad briefing reaches users. Too critical to test.
- **Flash Testing:** NO
- **Note:** Consider Sonnet upgrade for better reasoning

#### 3. `briefing_refine` — Polish
- **Volume:** 3–5 calls/day (refinement after critique)
- **Determinism:** Low (subjective refinement decisions)
- **Failure Cost:** Critical (operates on user-facing content post-critique)
- **Quality Requirement:** Critical (final user-facing output)
- **Rationale:** Operates on user-facing content after quality gates. Any degradation visible to users. Tier 3 by failure cost alone.
- **Flash Testing:** NO
- **Note:** Consider Sonnet upgrade

#### 4. `provider_fallback` — Agentic
- **Volume:** 0–5 calls/day (fallback when Anthropic fails)
- **Determinism:** Low (fallback logic is conditional)
- **Failure Cost:** Critical (fallback failure means no briefing at all)
- **Quality Requirement:** Critical (correctness of fallback logic prevents outages)
- **Rationale:** Safety fallback. If this fails, system has no output. Too critical to test. Latency-sensitive (real-time fallback required).
- **Flash Testing:** NO
- **Note:** Requires reliability-first approach, not cost optimization

**Sprint 16 Tier 3 Scope:** Explicitly out of scope for Flash evaluation. Document rationale for staying on current model (Haiku is interim; Sonnet upgrade is separate decision).

---

## Decision Gate: TASK-075 (narrative_generate Cache Investigation)

**Impact on Tier 2 Scope:**

The classification of `narrative_generate` depends on TASK-075 findings:

### Scenario A: Cache Issue is Fixable
- **Finding:** Input hashing bug, normalized caching, or similar → implement fix
- **Decision:** Remove `narrative_generate` from Phase 2 evaluation
- **Rationale:** Cost model changes if cache hit rate improves to 50%+; may drop to Tier 1 candidate
- **Phase 2 Scope:** 4 ops instead of 5 (narrative_theme_extract, cluster_narrative_gen, insight_generation, narrative_polish)
- **Timeline:** Phase 2 completes in 4-5 days instead of 5-6 days

### Scenario B: Cache Issue is Unfixable
- **Finding:** Unique inputs per narrative, session-specific generation → accept as-is
- **Decision:** Include `narrative_generate` in Phase 2 as highest-priority Tier 2 operation
- **Rationale:** Cache miss is ongoing cost driver; if Flash provides 30%+ savings, may be strongest Tier 2 swap candidate
- **Phase 2 Scope:** 5 ops including `narrative_generate` as 2nd priority
- **Timeline:** Phase 2 completes in 5-6 days

### Scenario C: Working as Intended
- **Finding:** Design uses fresh generations intentionally for quality → document why
- **Decision:** Include in Phase 2 with notation that cache misses are by design
- **Rationale:** Quality + cost tradeoff documented; Flash swap justified by cost savings alone
- **Phase 2 Scope:** 5 ops with explicit "cache miss is intentional" notation
- **Timeline:** Phase 2 completes in 5-6 days

**TASK-075 Timeline:** Run in parallel with TASK-078/079; results ready before FEATURE-053 Phase 2 starts.

---

## Flash Evaluation Execution Order (FEATURE-053)

### Phase 1: Tier 1 Operations (Sprint 16 ONLY)

**Scope:** 3 of 5 Tier 1 operations (time constraint)

| Priority | Operation | Volume | Est. Cost Swing | Golden Set Size | Quality Bar | Timeline |
|----------|-----------|--------|-----------------|-----------------|-------------|----------|
| 1st | `entity_extraction` | 100+/day | $0.05-0.10/day | 50–100 samples | Exact match / >90% overlap | Day 1-2 |
| 1st | `sentiment_analysis` | 150+/day | $0.08-0.15/day | 50–100 samples | Exact match / >90% overlap | Day 1-2 |
| 1st | `theme_extraction` | 120+/day | $0.06-0.12/day | 50–100 samples | Exact match / >90% overlap | Day 1-2 |

**Phase 1 Success Criteria:**
- [ ] Golden set extracted: 50–100 samples per operation
- [ ] Haiku baseline collected: latency, cost, quality metrics
- [ ] Flash variant run: same metrics
- [ ] Comparison table built: Model | Quality | Cost/1k | p50ms | p95ms
- [ ] Quality regression detected if >5%
- [ ] 1–3 decision records written (MSD-001, MSD-002, MSD-003)

**Deferred to Sprint 17:**
- `actor_tension_extract` (Tier 1, 2nd priority)
- `relevance_scoring` (Tier 1, 2nd priority)

### Phase 2: Tier 2 Operations (Sprint 17+, Pending TASK-075)

**Scope:** 4–5 Tier 2 operations (depends on TASK-075 decision)

| Priority | Operation | Volume | Est. Cost Swing | Golden Set Size | Quality Bar | Timeline | Dependency |
|----------|-----------|--------|-----------------|-----------------|-------------|----------|------------|
| 2nd | `narrative_generate` (if cache miss) | 20–30/day | $0.05–0.10/day | 30–50 samples | Manual 1–5 review, <10% regression | Day 3-4 | TASK-075 |
| 3rd | `narrative_theme_extract` | 30–40/day | $0.03–0.08/day | 30–50 samples | Manual 1–5 review, <10% regression | Day 4-5 | Phase 1 complete |
| 3rd | `cluster_narrative_gen` | 15–20/day | $0.02–0.05/day | 30–50 samples | Manual 1–5 review, <10% regression | Day 4-5 | Phase 1 complete |
| 4th | `insight_generation` | 10–15/day | $0.01–0.03/day | 30–50 samples | Manual 1–5 review, <10% regression | Day 5-6 | Phase 1 complete |
| 4th | `narrative_polish` | 30–40/day | $0.02–0.06/day | 30–50 samples | Manual 1–5 review, <10% regression | Day 5-6 | Phase 1 complete |

### Phase 3: Tier 3 Operations (No Testing)

**Scope:** Do not evaluate

| Operation | Reason | Alternative |
|-----------|--------|-------------|
| `briefing_generate` | Safety-critical primary deliverable | Consider Sonnet upgrade (separate decision) |
| `briefing_critique` | Quality gate; failure cost critical | Consider Sonnet upgrade (separate decision) |
| `briefing_refine` | User-facing; failure cost critical | Consider Sonnet upgrade (separate decision) |
| `provider_fallback` | Safety fallback; failure = no output | Consider Sonnet upgrade (separate decision) |

---

## Interview Positioning

This tier mapping demonstrates:
- **Systematic thinking** — operations classified by risk profile (volume, determinism, failure cost), not gut feel
- **Risk stratification** — Tier 1 (high volume, low risk) get aggressive testing; Tier 3 (low volume, high risk) get premium model
- **Cost-quality awareness** — Flash evaluated on operations where cost savings are material and quality risk is low
- **Reproducibility** — anyone can follow the rubric and arrive at the same tier assignments

**Talking point:**
> "We classify operations by criticality and volume. Tier 1 (high-volume extraction) gets aggressive Flash testing because quality variance is low and cost is high. Tier 3 (low-volume reasoning) stays on premium because failure cost is non-negotiable. Tier 2 sits in the middle — generation operations where quality matters but manual review makes cost-quality tradeoffs explicit."

---

*This document inputs operation tier assignments to FEATURE-053 (Flash evaluations). Decision records produced by FEATURE-053 are filed as MSD-001+.*
