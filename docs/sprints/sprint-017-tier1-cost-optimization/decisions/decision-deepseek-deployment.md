---
id: DR-2026-05-001
date: 2026-04-30
decision: Deploy DeepSeek V4 Flash as primary LLM provider for all Tier 1 operations (entity extraction, sentiment analysis, theme extraction)
status: DECIDED
revisit: After Phase 1 (sentiment) reaches production stability and cost savings are validated (2026-06-15)
related_story: FEATURE-054, Sprint 17 & 18
---

# Decision Record: DeepSeek as Tier 1 Primary LLM Provider

## Context

**FEATURE-054 Phase 4 Cost Analysis** revealed that Backdrop's Phase 3 scoring used OpenRouter pricing, which applies 10-12x markups on DeepSeek. Direct DeepSeek API pricing is:

- **DeepSeek V4 Flash:** $0.14/M input, $0.28/M output
- **Claude Haiku:** $1.00/M input, $5.00/M output
- **Cost ratio:** DeepSeek is **7-18x cheaper** depending on token mix

Current Backdrop LLM spend (Haiku-only):
- Enrichment: ~$126/day (~$46k/year)
- Briefing generation: ~$36/day (~$13k/year)
- **Total: ~$59k/year**

**Projected DeepSeek spend:**
- Enrichment: ~$8.82/day (~$3.2k/year)
- Briefing generation: ~$2.52/day (~$0.9k/year)
- **Total: ~$4.1k/year**

**Potential annual savings: $54,925/year**

This is not an incremental optimization (save $2-3k/year). This is a fundamental cost structure change (90% reduction).

**Critical constraint:** FEATURE-054 Phase 4 also revealed two issues that prevent recommending this without caveats:

1. **Entity Extraction Haiku baseline is weak** (0.43 F1 vs 0.82 threshold). All challengers score 0.28-0.41 F1. This suggests the TASK-081 prompt fix didn't fully solve entity extraction. Deploying DeepSeek entity extraction when Haiku itself is suboptimal is a bet.

2. **Theme Extraction reference/prompt mismatch** (references include proper nouns, corrected prompt excludes them). Fair scoring requires reannotation. Theme extraction is not viable until this is fixed.

---

## The Decision

**Deploy DeepSeek V4 Flash as the primary Tier 1 LLM provider across all three operations, with phased rollout prioritizing sentiment (lowest risk) → entity (medium risk) → theme (conditional on reannotation).**

**Implementation plan (Sprint 18):**
1. Build `DeepSeekProvider` class (TASK-085, 3-4h)
2. Production validation via A/B testing (TASK-086, 3-4 weeks phased)
   - Phase 1: Sentiment 100% cutover (1 week A/B, highest confidence)
   - Phase 2: Entity parallel → conditional cutover (2 weeks A/B, medium confidence)
   - Phase 3: Theme conditional on reannotation (TASK-087, optional)
3. Monitor, log, rollback capability in place before each phase

**Why all three operations, not just sentiment?**

While sentiment has highest agreement with Haiku (85%, low risk), entity and theme have acceptable agreement rates (60%+ Jaccard) and the cost difference is substantial enough to justify the risk. The decision is to optimize for cost-per-operation, not to minimize risk per operation.

---

## Why This Over Alternatives?

### Option A: Stay Haiku-only (rejected)
- **Cost:** $59k/year
- **Risk:** Low
- **Tradeoff:** Leave $55k/year on the table indefinitely

### Option B: Flash through OpenRouter (partially rejected)
- Originally recommended in FEATURE-054 Phase 4
- **Cost:** Flash on sentiment only = ~$0.88/year (vs Haiku $8k on sentiment) = $7.1k/year savings
- **Risk:** Low
- **Tradeoff:** $47k+ in unrealized savings from entity/theme optimization

### Option C: DeepSeek direct API (CHOSEN)
- **Cost:** $4.1k/year
- **Risk:** Medium (behavioral consistency 60-85%, entity baseline weak, theme needs reannotation)
- **Tradeoff:** Accept medium operational risk for 90% cost reduction

**Why C over A+B?**

The Phase 4 cost discovery is too significant to ignore. $55k/year is a multi-year commitment. The behavioral consistency data (82-85% agreement on sentiment, 60%+ Jaccard on entity) is sufficient to justify a phased rollout with monitoring and rollback capability.

If we stay with Haiku-only or deploy Flash through expensive OpenRouter, we're choosing "safety" (lower risk) over "financial sense" (accepting manageable risk for massive savings). The phased approach lets us validate incrementally:
- Sentiment first (safest): proven 85% agreement
- Entity second (medium): proven 64% agreement (Flash), with validation
- Theme conditional (safest): only after reannotation

This is not reckless. It's intentionally sequenced risk.

---

## How We'll Know If We Got It Right

**Phase 1 (Sentiment) success metrics:**
- ✅ Agreement rate >= 80% sustained over 5+ days
- ✅ Latency acceptable (p95 < 3s)
- ✅ Cost tracking confirms $X/month savings
- ✅ No recurring errors or parse failures
- ✅ Zero quality complaints from users

**Phase 2 (Entity) success metrics:**
- ✅ Agreement rate >= 60% sustained
- ✅ Spot-check failures are fixable (parse errors, not quality gaps)
- ✅ Downstream analysis unaffected (narrative clustering still works)
- ✅ Cost savings confirmed

**Phase 3 (Theme) success metrics (if reannotation done):**
- ✅ Agreement rate >= 60% sustained
- ✅ F1 scores acceptable against reannotated references
- ✅ Briefing quality unchanged

**If we got it wrong:**
- ❌ Phase 1: Agreement drops below 75% → revert sentiment to Haiku, accept $7k/year savings instead
- ❌ Phase 2: Agreement drops below 55% OR spot-checks reveal quality gaps → revert entity to Haiku, accept $20k/year savings instead
- ❌ Phase 3: Entity F1 scores break downstream analysis → revert entity to Haiku

The phased rollout with clear rollback criteria means we never bet more than we can lose at once.

---

## Related Decisions

- **TASK-081 (Fix Tier 1 Prompts):** Prerequisite. Entity extraction baseline is weak partly because prompts aren't optimal yet.
- **TASK-087 (Reannotate Theme Extraction):** Prerequisite for Phase 3. Unblocks fair evaluation of theme extraction.
- **DR-2026-04-001 (Haiku-only LLM strategy):** This decision **supersedes** the previous Haiku-only LLM strategy.
- **Cost tracking & monitoring:** This decision depends on accurate cost logging and agreement monitoring. Critical path item.

---

## Caveats

### Known unknowns:
1. **Direct API latency not validated.** Phase 4 measured through OpenRouter. Direct DeepSeek API latency is unknown. Could be better (fewer hops) or worse (different infrastructure). **Mitigation:** Phase 1 A/B test will measure real latency; rollback capability in place.

2. **Entity extraction baseline quality issue.** Haiku 0.43 F1 is low. Deploying DeepSeek (0.28-0.41 F1) means accepting weak baselines. **Mitigation:** Phase 2 spot-checks will identify if DeepSeek failures are fixable or fundamental. Rollback available.

3. **Single provider dependency created.** Currently Anthropic-only → now Anthropic + DeepSeek. If DeepSeek API goes down or changes pricing, we're exposed. **Mitigation:** Maintain Haiku as fallback. Haiku provider still in place, easy to revert.

4. **Theme extraction reannotation required but not guaranteed to complete.** If TASK-087 slips, Phase 3 is blocked indefinitely. **Mitigation:** Phase 3 is "conditional"; phases 1-2 can stand alone.

### Assumptions that could break:
- DeepSeek API remains available and pricing stable through 2027
- Agreement rates don't degrade over time (data drift, model changes)
- Entity extraction F1 can reach 0.50+ with prompt tuning (if baseline improves, this is better)
- Latency on direct API is acceptable for async briefing generation
- Cost tracking calculations are accurate (token counts must match DeepSeek dashboard)

### If we got it wrong:
- **Phase 1 fails (sentiment agreement < 75%):** We've only lost time on sentiment. Revert to Haiku, save $7k/year, continue with entity/theme investigation.
- **Phase 2 fails (entity agreement < 55%):** We save $20k/year (sentiment + partial entity savings). Keep sentiment on DeepSeek, revert entity to Haiku.
- **Entity extraction drives downstream failures:** Narrative clustering breaks, briefing quality drops. Rollback to Haiku entity extraction immediately.

The phased rollout ensures we never lose the ability to revert.

---

## Decision Ownership

**Decided by:** Mike Chavez (product)
**Reviewed by:** None yet (seek feedback from ops/engineering)
**Responsibility:** Mike owns risk of deployment. Engineering owns implementation (TASK-085/086).
**Communication:** Update stakeholders before Phase 1 sentiment cutover. Share cost savings realizations monthly.

---

## Revisit Trigger

**Revisit this decision if:**
- [ ] Phase 1 (sentiment) agreement drops below 75% and doesn't recover
- [ ] DeepSeek API becomes unstable or pricing changes materially
- [ ] Entity extraction failures in Phase 2 exceed 10% rate
- [ ] Cost savings don't materialize (token counting errors, usage higher than projected)
- [ ] New LLM provider emerges that's significantly cheaper or better

**Revisit date:** 2026-06-15 (after Phase 1 sentiment reaches 2 weeks production stability)

---

*Decision record created 2026-04-30. Next review: 2026-06-15 (post-Phase 1 validation).*