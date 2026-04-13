---
id: TASK-070
type: task
status: backlog
priority: high
severity: medium
created: 2026-04-13
updated: 2026-04-13
---

# Investigate and Optimize narrative_generate LLM Costs

## Problem
`narrative_generate` operations are consuming 56% of daily LLM budget ($0.367 of $0.657 total spend on 2026-04-13), significantly constraining briefing generation capacity and forcing hard budget limits.

**Cost breakdown (2026-04-13, last 30 mins):**
- narrative_generate: $0.1363 (44 calls, $0.003097 avg cost) ← **EXPENSIVE**
- entity_extraction: $0.0125 (16 calls, $0.000781 avg cost) ← **Cheap**
- briefing_generate: $0.0095 (1 call) 
- briefing_refine: $0.0177 (2 calls)
- briefing_critique: $0.0118 (2 calls)

**Key observation:** narrative_generate is **3.5x more expensive per call** than entity_extraction, yet both use similar LLM-based extraction logic.

## Expected Behavior
narrative_generate should consume a proportionate share of daily budget (15-20% target), not dominate at 56%. This requires:
1. Understanding WHY narrative_generate is expensive
2. Evaluating model choice (currently Sonnet?)
3. Optimizing cache strategy and batch efficiency
4. Potentially reducing call volume through sampling or throttling

## Current Situation
- Hard limit: $0.60/day ($0.50 soft limit)
- Current spend rate: $0.657/day (9.5% over limit after 30 mins)
- narrative_generate dominates: $0.367/day burn with 117 calls
- Soft limit blocks refinement and critique
- Hard limit blocks background enrichment
- **Result:** Briefing generation is severely constrained

---

## Investigation Scope

### 1. Understand narrative_generate Cost Structure
**Questions to answer:**
- [ ] What model is being used? (Sonnet vs Haiku)
- [ ] What are typical input/output token counts?
- [ ] How many calls happen per briefing generation?
- [ ] Is there caching? What's the hit rate?
- [ ] How does this compare to entity_extraction costs?

**Action:**
- Query `llm_traces` to analyze narrative_generate calls
- Check cache hit rate in `llm_cache` collection
- Compare input/output token counts for similar operations

### 2. Evaluate Model Choice
**Current hypothesis:** narrative_generate uses Claude Sonnet (expensive)
- Sonnet: ~$0.003 per 1K tokens
- Haiku: ~$0.0008 per 1K tokens (3.75x cheaper)

**Actions:**
- [ ] Verify current model in use for narrative_generate
- [ ] Test if Haiku can produce similar quality narratives
- [ ] Run A/B test: Sonnet vs Haiku with confidence_score comparison
- [ ] If quality is acceptable, switch to Haiku (potential 3.5x cost reduction)

### 3. Optimize Cache Hit Rate
**Current data (2026-04-13):**
- entity_extraction cache: 99.1% hit rate (769 entries)
- narrative_generate cache: Unknown

**Actions:**
- [ ] Measure narrative_generate cache hit rate
- [ ] Identify cache miss patterns (are narratives unique per article?)
- [ ] Consider fingerprinting narratives by content hash
- [ ] Evaluate if broader cache scope could improve hit rates

### 4. Reduce Call Volume
**Options:**
- [ ] Sample narratives: Only generate for top N trending articles (vs all)
- [ ] Batch narrative generation: Process multiple articles in one call
- [ ] Defer non-critical narratives to off-peak hours
- [ ] Implement narrative reuse for similar articles

**Estimated impact:** Could reduce volume by 30-50% if selective sampling is acceptable

### 5. Refactor narrative_generate Logic
**Consider:**
- [ ] Consolidate narrative and entity extraction into single LLM call
- [ ] Use cheaper model (Haiku) for first pass, Sonnet for refinement only
- [ ] Implement streaming to reduce token waste
- [ ] Add token budgeting to stop generation early if costs exceed threshold

---

## Success Criteria

### Minimum (Get within budget)
- [ ] narrative_generate reduced to ≤25% of daily budget (~$0.15)
- [ ] Daily spend maintained at or below $0.60 hard limit
- [ ] No quality degradation (confidence_score remains >0.7)

### Target (Sustainable operations)
- [ ] narrative_generate reduced to ≤15% of daily budget (~$0.09)
- [ ] Soft limit can be raised to $0.70+ without hitting hard limit
- [ ] Cache hit rate >85% for narrative_generate
- [ ] Can process 100+ articles/day without budget concerns

### Stretch (Efficient platform)
- [ ] narrative_generate cost reduced by 50%+ through model/approach optimization
- [ ] Daily budget utilization: 70-80% (leaves 20-30% headroom for spikes)
- [ ] Can support 200+ articles/day or 2x current volume

---

## Implementation Phases

### Phase 1: Investigation & Analysis (1-2 days)
- Query cost data, identify root causes
- Test Haiku vs Sonnet on sample narratives
- Measure cache hit rates
- **Output:** Root cause analysis + recommendation

### Phase 2: Quick Win (If Haiku works)
- Switch narrative_generate to Haiku
- Monitor confidence scores and quality
- **Estimated savings:** 3.5x cost reduction = ~$0.10/day

### Phase 3: Advanced Optimization (If needed)
- Implement selective sampling or batching
- Refactor narrative generation logic
- **Estimated savings:** Additional 20-30% reduction

### Phase 4: Validation (72-hour burn-in)
- Run TASK-028 with optimized costs
- Verify no regressions
- Document final cost structure

---

## Resources & Dependencies
- Access to MongoDB (`llm_traces`, `llm_cache` collections)
- Current model configuration (config.py or environment vars)
- LLM response history for quality comparison
- Depends on: BUG-069 fix (briefing save) so we can accurately measure costs

---

## Acceptance Criteria
- [x] Root cause identified and documented
- [ ] Model choice evaluated (Haiku feasibility confirmed or rejected)
- [ ] Cache optimization strategy proposed
- [ ] Call volume reduction approach identified
- [ ] Cost projection updated (what can we realistically achieve?)
- [ ] Implementation plan with timeline provided
- [ ] At least one optimization deployed and verified

---

## Related Tickets
- **BUG-069:** Briefing save bug (blocking accurate cost measurement)
- **TASK-028:** 72-hour burn-in validation (will verify cost improvements)
- **BUG-065, BUG-067, BUG-068:** Cost tracking bugs (now fixed)

---

## Notes
- Started after session on 2026-04-13 identified narrative_generate as 56% of daily spend
- Current hard limit ($0.60) is too tight with narrative_generate consuming $0.367
- Increasing limit is temporary fix; need to optimize spend as permanent solution
- Quality matters: Any solution must maintain confidence_score >0.7 for briefing utility