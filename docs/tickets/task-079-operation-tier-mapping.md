---
ticket_id: TASK-079
title: Operation Tier Mapping — Classify All 14 Operations
priority: high
severity: medium
status: COMPLETE
date_created: 2026-04-27
date_completed: 2026-04-27
effort_estimate: 2-3 hours
---

# TASK-079: Operation Tier Mapping — Classify All 14 Operations

## Problem Statement

Need explicit classification of all 14 LLM operations into tiers (0, 1, 2, 3) using the Model Selection Rubric (TASK-078). This determines which operations get Flash evaluation in FEATURE-053 and becomes interview material demonstrating systematic decision-making.

---

## Task

### Deliverable

Create `docs/operation-tiers.md` with:

1. Classification table for all 14 operations
2. Rationale for each tier assignment
3. Test priority ranking (for FEATURE-053 execution order)

---

## Classification Framework

Use the 5 decision dimensions from TASK-078:
- Quality Requirement (critical → nice-to-have)
- Volume (high → low)
- Latency Sensitivity (yes → no)
- Determinism (required → optional)
- Failure Cost (high → low)

Then map to tiers:
- **Tier 1:** High volume + deterministic + low failure cost (extraction)
- **Tier 2:** Medium volume + generation + user-facing (synthesis)
- **Tier 3:** Low volume + reasoning required + safety-critical (critique/agentic)
- **Tier 0:** Rule-replaceable (non-LLM candidate)

---

## 14 Operations to Classify

```
1. narrative_generate
2. entity_extraction
3. narrative_theme_extract
4. actor_tension_extract
5. cluster_narrative_gen
6. narrative_polish
7. briefing_generate
8. briefing_refine
9. briefing_critique
10. provider_fallback
11. sentiment_analysis
12. theme_extraction
13. relevance_scoring
14. insight_generation
```

### Classification Table

| # | Operation | Type | Tier | Quality | Volume | Latency | Determinism | Failure Cost | Rationale | Flash Test? | Priority |
|---|-----------|------|------|---------|--------|---------|-------------|--------------|-----------|------------|----------|
| 1 | narrative_generate | Synthesis | 2 | High | Medium (20-30/day) | No | Low | High | User-facing generation, impacts briefing quality. **Pending TASK-075 cache findings:** if cache improves, reconsider for Tier 1. | PENDING | 2nd (if cache miss) |
| 2 | entity_extraction | Extraction | 1 | Medium | High (100+/day) | No | High | Low | Pure structured extraction from content; high volume, deterministic, internal. | YES | 1st |
| 3 | narrative_theme_extract | Synthesis | 2 | High | Medium (30-40/day) | No | Low | Medium | Generates theme narratives; quality important for user briefing. | YES | 3rd |
| 4 | actor_tension_extract | Extraction | 1 | Medium | High (80+/day) | No | High | Low | Extract relationships/tension; high volume, deterministic, internal. | YES | 2nd |
| 5 | cluster_narrative_gen | Synthesis | 2 | High | Medium (15-20/day) | No | Low | Medium | Narrative synthesis from cluster; user-facing quality matters. | YES | 3rd |
| 6 | narrative_polish | Polish | 2 | Medium | Medium (30-40/day) | No | Medium | Medium | Refines existing narratives; quality matters but not safety-critical. | YES | 4th |
| 7 | briefing_generate | Reasoning | 3 | Critical | Low (5-10/day) | No | Low | Critical | Core user deliverable; reasoning, multi-step; too critical to test. | NO | — |
| 8 | briefing_refine | Reasoning | 3 | Critical | Low (3-5/day) | No | Low | Critical | Quality gate for briefing; user-facing; too critical to test. | NO | — |
| 9 | briefing_critique | Reasoning | 3 | Critical | Low (2-3/day) | No | Low | Critical | Evaluates briefing quality; requires subjective judgment; too critical. | NO | — |
| 10 | provider_fallback | Agentic | 3 | Critical | Low (0-5/day) | Yes | Low | Critical | Safety fallback when primary provider fails; too critical to test. | NO | — |
| 11 | sentiment_analysis | Extraction | 1 | Medium | High (150+/day) | No | High | Low | Pure structured extraction; very high volume, deterministic, internal. | YES | 1st (parallel) |
| 12 | theme_extraction | Extraction | 1 | Medium | High (120+/day) | No | High | Low | Structured extraction of themes; high volume, deterministic, internal. | YES | 2nd (parallel) |
| 13 | relevance_scoring | Extraction | 1 | Medium | High (200+/day) | No | High | Low | Deterministic scoring; highest volume, internal. | YES | 1st (parallel) |
| 14 | insight_generation | Synthesis | 2 | High | Medium (10-15/day) | No | Low | High | Generates novel insights; quality critical for user value. | YES | 5th |

---

### Summary by Tier

**Tier 1 (Aggressive Flash Testing):** 5 operations
- entity_extraction
- actor_tension_extract
- sentiment_analysis
- theme_extraction
- relevance_scoring

**Tier 2 (Cautious Flash Testing):** 7 operations
- narrative_generate (pending TASK-075 decision)
- narrative_theme_extract
- cluster_narrative_gen
- narrative_polish
- insight_generation
- (narrative_generate if cache miss confirmed)

**Tier 3 (No Flash Testing):** 2 operations
- briefing_generate
- briefing_critique
- briefing_refine
- provider_fallback

---

## Flash Evaluation Priority (for FEATURE-053)

### Phase 1: Tier 1 (High Confidence, Low Risk)
Execute in parallel:
1. **entity_extraction** — 100+ calls/day, deterministic, internal
2. **sentiment_analysis** — 150+ calls/day, deterministic, internal
3. **relevance_scoring** — 200+ calls/day, deterministic, internal
4. **actor_tension_extract** — 80+ calls/day, deterministic, internal
5. **theme_extraction** — 120+ calls/day, deterministic, internal

**Cost Estimate:** ~$0.15-$0.20/day swing (largest cost drivers)
**Quality Bar:** Exact match or >90% overlap; <5% regression threshold
**Timeline:** 3-4 days (parallel execution, same golden set query)

### Phase 2: Tier 2 (Conditional, Requires Manual Review)
Execute after Tier 1, pending TASK-075 findings:
1. **narrative_generate** — only if cache miss confirmed (TASK-075)
   - Cost Estimate: ~$0.05-$0.10/day swing
   - Quality Bar: Manual 1-5 review, <10% regression
2. **narrative_theme_extract** — 30-40 calls/day
3. **cluster_narrative_gen** — 15-20 calls/day
4. **narrative_polish** — 30-40 calls/day
5. **insight_generation** — 10-15 calls/day

**Timeline:** 5-6 days (sequential golden sets, manual scoring)

### Phase 3: Tier 3 (Deferred)
- Do not test briefing_generate, briefing_critique, briefing_refine, provider_fallback
- Document rationale: "Too critical for experimentation"
- Consider separate Sonnet upgrade evaluation (out of scope Sprint 16)

---

## Decision Gate: TASK-075 Result

**If narrative_generate cache is fixed:**
- Remove narrative_generate from FEATURE-053 scope
- Proceed to Tier 2 without it (4 ops instead of 5)
- Cost savings may reduce need for Flash swap

**If narrative_generate cache issue is unfixable:**
- Include in Phase 2 Tier 2 evaluation
- Higher priority (cache miss is ongoing cost driver)
- May be strongest Flash candidate (cost + volume)

---

## Testing / Verification

- [ ] All 14 operations classified
- [ ] Each classification includes rationale (why this tier?)
- [ ] Decision dimensions documented for each op
- [ ] Tier 1 and Tier 2 operations list matches rubric criteria
- [ ] Flash test priority is clear and defensible
- [ ] TASK-075 dependency documented (narrative_generate branching)

---

## Acceptance Criteria

- [ ] docs/operation-tiers.md complete with classification table
- [ ] All 14 operations assigned to tier (0, 1, 2, or 3)
- [ ] Each tier has clear rationale paragraph
- [ ] Flash test priority order defined (Tier 1 first, then Tier 2)
- [ ] TASK-075 branching logic documented
- [ ] Document is ready for interview reference or engineering discussion

---

## Impact

- Determines scope and priority of FEATURE-053 (Flash evals)
- Prevents mid-sprint scope creep ("which operations do we test?")
- Demonstrates systematic thinking (ties back to rubric)
- Interview material (shows cost-quality reasoning)

---

## Related Tickets

- TASK-078 (Model Selection Rubric defines tiers)
- TASK-075 (narrative_generate classification depends on cache decision)
- FEATURE-053 (Flash Evaluations uses this priority order)

---

## Completion Notes

✅ **COMPLETE** — 2026-04-27

The operation tier mapping has been written and is available at:
**[`docs/decisions/operation-tiers.md`](../decisions/operation-tiers.md)**

The mapping includes:
- ✅ All 14 operations classified into tiers 0–3
- ✅ Each operation has detailed rationale (why this tier?)
- ✅ All 5 decision dimensions documented for each operation
- ✅ Tier 1 (5 operations): Aggressive Flash testing candidates
- ✅ Tier 2 (5 operations): Cautious Flash testing candidates
- ✅ Tier 3 (4 operations): No Flash testing (safety-critical)
- ✅ Flash evaluation execution order prioritized (Phase 1: Tier 1 only, Phase 2: Tier 2)
- ✅ **Sprint 16 scope note:** Tier 1 limited to 3 operations (entity_extraction, sentiment_analysis, theme_extraction) due to time constraints
- ✅ TASK-075 decision gate: narrative_generate classification depends on cache investigation
- ✅ Interview positioning notes demonstrating systematic thinking

**Summary by Tier:**
- **Tier 1 (Aggressive):** entity_extraction, sentiment_analysis, theme_extraction, actor_tension_extract, relevance_scoring
- **Tier 2 (Cautious):** narrative_generate (pending TASK-075), narrative_theme_extract, cluster_narrative_gen, insight_generation, narrative_polish
- **Tier 3 (No testing):** briefing_generate, briefing_critique, briefing_refine, provider_fallback

**Sprint 16 Phase 1 (Tier 1 subset):** 3 operations (entity_extraction, sentiment_analysis, theme_extraction)

Ready as input for FEATURE-053 Phase 1 (golden set extraction and Flash evaluations).