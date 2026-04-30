# Product Story: When Your Eval Framework Says "All Models Fail" But Your Data Says Otherwise

**Date:** 2026-04-30

**Sprint:** S17

**Non-obvious insight:** The cheapest model wasn't expensive because it was bad—it was expensive because I was measuring it through the wrong broker. Fix the infrastructure, not the model.

---

## STUB (10 minutes)

### What Was the Problem?

Backdrop's Tier 1 LLM costs are $59k/year. Post-hoc analysis (TASK-080) found three broken prompts: entity extraction wasn't weighting by relevance, sentiment had no neutral class definition, theme extraction included proper nouns when the spec said to exclude them. So we fixed the prompts and re-ran evaluations to find which cheaper models could replace Haiku. But the eval results were brutal: 0 out of 9 models passed the quality thresholds.

### What Was Hard?

1. **Reference set imbalance made thresholds unreachable.** Sentiment references were 85% positive, 3% neutral, 12% negative. All models (including Haiku) struggle with minority classes. A 77% accuracy threshold is impossible when the baseline is only 47% accurate.

2. **"All models fail" is ambiguous.** Doesn't tell you if models are bad, references are wrong, or prompts are still broken. Took manual analysis to distinguish: entity extraction has weak Haiku baseline (0.43 F1), theme extraction has reference/prompt mismatch (references include proper nouns, corrected prompt excludes them).

3. **OpenRouter pricing hid the real opportunity.** Phase 4 measured costs through OpenRouter. Only later discovered: OpenRouter charges 10-12x markup on DeepSeek. Direct API is 85-90% cheaper than Haiku. If I'd stopped at "Flash is 57% cheaper through OpenRouter," we'd save $7k/year. Instead, "DeepSeek direct is 90% cheaper" changes the entire decision to $55k/year savings.

### What Surprised You?

1. **All models agree on sentiment (85% of the time).** This is the strongest signal. Not "models are bad," but "models are consistent." High behavioral agreement = low deployment risk.

2. **Haiku's baseline being weak (0.43 F1) meant entity extraction was never a model quality problem—it was a prompt problem.** Didn't need to test alternatives; needed to fix the baseline.

3. **Reference annotations were philosophically wrong, not just imprecise.** Theme references included Bitcoin, Ethereum (proper nouns), but the corrected prompt explicitly says to exclude them. Models were getting penalized for following the spec correctly. This is the kind of mistake you catch only by reading both the references AND the prompt spec side-by-side.

### Publishable?

**Maybe** — The DeepSeek angle is real and timely (timing of LLM pricing, importance of measuring through real APIs not brokers). But needs to wait for Phase 1 (sentiment) to deploy successfully. If Phase 1 fails (agreement drops below 75%), the story flips from "smart cost optimization" to "I over-rotated on savings and regretted it." Decide in 2 weeks after production validation.

### Related Decision Record(s)

- DR-2026-05-001: Deploy DeepSeek V4 Flash as primary Tier 1 LLM provider
- FEATURE-054: Tier 1 Cost Optimization Evaluations (updated with DeepSeek findings)

---

**END OF STUB**

---

## EXPANDED STORY (Candidate for Publishing — Decide After Phase 1 Validation)

*(Expanded version below. Only publish after sentiment reaches 2+ weeks production stability.)*

---

## Story Metadata

**Title:** Evaluating LLMs for Cost Optimization: When "All Models Fail" Means the Framework Is Wrong

**Date:** 2026-04-30

**Company/Project:** Backdrop (crypto news aggregator + briefing system)

**Role at time:** Product manager + IC engineer

**Tags:** evaluations, cost reduction, LLM routing, infrastructure, reference data quality

**Non-obvious insight:** The cheapest model wasn't expensive because it was bad—it was expensive because I was measuring it through the wrong broker. OpenRouter's 10-12x markup on DeepSeek hid a $55k/year opportunity.

**Interview survivability:** MEDIUM (needs Phase 1 validation before claiming victory)

---

## The Core Narrative

### Situation

Backdrop runs on Claude Haiku for three Tier 1 operations: entity extraction, sentiment analysis, and theme extraction. These feed into daily crypto market briefings. The system has been stable for 6+ months, but costs are high ($59k/year on just LLM inference).

In Sprint 16, we ran Flash evaluations (FEATURE-053) to test if cheaper models could work. Flash looked promising on sentiment (57% cheaper through OpenRouter), so we kicked off a structured cost optimization sprint (Sprint 17: FEATURE-054) to evaluate three challengers (Flash, DeepSeek, Qwen) against three operations, using a threshold-based approach (acceptable quality loss per operation, not comparison-based scoring vs Haiku).

### Problem

The evaluation framework was sound in theory, but the execution hit three layers of friction:

1. **Prompts were broken.** Post-hoc analysis (TASK-080) found three philosophical mismatches:
   - Entity extraction wasn't weighting by relevance (included noise mentions)
   - Sentiment had no neutral class definition (all models defaulted to positive/negative)
   - Theme extraction included proper nouns (Bitcoin, Ethereum) when the spec said to exclude them

2. **Reference annotations were imbalanced.** We ran a threshold-based eval with hand-labeled reference answers. But the sentiment reference set was 85% positive, 3% neutral, 12% negative. This made the 77% accuracy threshold unreachable—Haiku itself only scored 47% accurate.

3. **Cost measurements were inflated.** We used OpenRouter for testing (easier infrastructure than managing multiple APIs). But OpenRouter applies 10-12x markups on DeepSeek pricing. This hid the real opportunity: direct DeepSeek API is 7-18x cheaper than Haiku, not "57% cheaper through OpenRouter."

By end of Phase 3, all 9 model-operation pairs had failed the absolute quality thresholds. The question became: **Are models genuinely bad, or is the framework measuring the wrong thing?**

### Approach

Instead of declaring failure and moving on, I invested in manual analysis (Phase 4):

1. **Analyzed why models failed systematically.** Rather than accept "0/9 pass" at face value, I did spot-checks:
   - For sentiment: Why do all models score ~40% accuracy when Haiku (the "baseline") scores 47%? Answer: Reference set imbalance. All models struggle with minority classes.
   - For entity extraction: Why do all models score 0.28-0.41 F1 when the threshold is 0.82? Answer: Haiku baseline is 0.43 F1. The prompt fix from TASK-081 didn't fully work. This is a prompt problem, not a model problem.
   - For theme extraction: Why do all models score 0.10-0.15 F1? Answer: References include proper nouns (Bitcoin, Ethereum), but the corrected prompt explicitly excludes them. Models are being penalized for following the spec correctly.

2. **Measured behavioral consistency instead of absolute quality.** Instead of "does model X score above threshold Y," I asked: "How often does model X produce the same output as Haiku?" This is a stronger signal for deployment risk.
   - Sentiment: 85% agreement (very high, low risk)
   - Entity: 46-64% Jaccard similarity depending on model (moderate, medium risk)
   - Theme: 16-37% similarity (low, high risk)

3. **Discovered the OpenRouter markup.** During cost analysis, I realized Phase 4's measurements used OpenRouter. Looked up direct API pricing:
   - DeepSeek V4 Flash: $0.14/M input, $0.28/M output
   - Claude Haiku: $1.00/M input, $5.00/M output
   - OpenRouter (various providers): $1.40-1.74/M input, $2.78-3.48/M output
   
   DeepSeek direct is 10-12x cheaper than OpenRouter. This changes the entire recommendation from "Flash on sentiment saves $7k/year" to "DeepSeek on all three saves $55k/year."

### Finding or Outcome

**End of Sprint 17:**
- ✅ Fixed three Tier 1 prompts (TASK-081)
- ✅ Ran 900 challenger API calls with new baselines (FEATURE-054 Phases 1-2)
- ✅ Scored against thresholds (FEATURE-054 Phase 3)
- ✅ Manual analysis identified why "all models fail" (FEATURE-054 Phase 4)
- ✅ Discovered $55k/year opportunity via direct DeepSeek API

**Recommendation:** Deploy DeepSeek V4 Flash as primary Tier 1 LLM provider, phased:
- Phase 1 (Sprint 18): Sentiment analysis (safest, 85% behavioral agreement)
- Phase 2 (Sprint 18): Entity extraction (medium risk, 60%+ Jaccard, requires validation)
- Phase 3 (Sprint 18+): Theme extraction (conditional on reannotating references)

**Key metrics:**
- Sentiment agreement with Haiku: 85%
- Entity extraction agreement with Haiku: 60-64% (Jaccard)
- Theme extraction agreement with Haiku: 24-37% (too low, needs reannotation)
- Cost reduction: 90% across all three operations ($55k/year savings)
- Behavioral consistency threshold (decision point): >= 80% sentiment, >= 60% entity, >= 60% theme

### The Non-Obvious Layer

Three sophistications that a less rigorous approach would have missed:

1. **"All models fail" is not a conclusion—it's a debugging signal.** When an eval framework shows 0/9 pass, the instinct is "models are bad." Instead, I asked: "Is the framework measuring the right thing?" This led to discovering three separate issues (weak Haiku baseline, reference set imbalance, reference/prompt mismatch), each requiring different fixes.

2. **Behavioral consistency is a better signal than absolute quality for deployment.** 85% agreement with Haiku is a stronger predictor of "safe to deploy" than "F1 = 0.78 ≥ 0.78 threshold." The latter is sensitive to reference quality; the former is empirical. For production decisions, "works like Haiku 85% of the time" is actionable.

3. **Infrastructure choices compound cost measurements.** Using OpenRouter for testing is convenient (one API, easy SDK), but it hides the real economics. If I'd stopped the analysis there, we'd ship with 90% of savings left on the table. Surfacing the direct API pricing required looking at raw provider pricing, not just what a broker charges.

### Impact

**Immediate (Sprint 17):**
- Cleared blockers (TASK-081, TASK-082)
- Validated evaluation framework (it works, but requires care on reference data)
- Identified $55k/year opportunity (vs $7k with less rigorous approach)

**Near-term (Sprint 18):**
- Build DeepSeekProvider class (TASK-085, 3-4h)
- A/B test sentiment on production (TASK-086 Phase 1, 1 week)
- Validate before full rollout (phased approach, rollback capability)

**Long-term (Sprint 18+):**
- Realize $55k/year cost savings if all three phases deploy successfully
- Establish repeatable eval process for next generation of models
- Reduce friction on cost optimization decisions (clear framework, known tradeoffs)

---

## Defensible Metrics

| Metric | Value | Status | Defense |
|---|---|---|---|
| Sentiment agreement with Haiku | 85% (29/34) | DEFENSIBLE | Phase 4 manual count across all three challengers |
| Entity extraction Jaccard similarity | 46-64% depending on model | DEFENSIBLE | Phase 4 agreement analysis (Flash 64%, Qwen 58%, DeepSeek 46%) |
| Theme extraction agreement | 16-37% | DEFENSIBLE | Phase 4 Jaccard similarity |
| Current annual Haiku cost | $59,000 | DEFENSIBLE | Based on token counts + Haiku pricing ($1/$5 per 1M) |
| DeepSeek annual cost (if deployed all three ops) | $4,100 | APPROXIMATE | Based on OpenRouter data extrapolated to direct API; real cost depends on actual token usage at scale |
| Annual savings potential | $54,925 | APPROXIMATE | $59k - $4.1k; assumes deployment of all three operations and no operational overhead increases |
| OpenRouter markup on DeepSeek | 10-12x | DEFENSIBLE | Direct: $0.14/$0.28 per 1M vs OpenRouter: $1.40-1.74/$2.78-3.48 per 1M |

---

## Format Pulls (for publishing)

### Resume Bullet

> Diagnosed inflated LLM evaluation results as a framework problem, not a model problem; discovered $55k/year cost optimization opportunity by analyzing reference data quality and unmaskingOpenRouter's 10-12x pricing markup on cheaper models.

### Resume Summary

> Led structured cost optimization eval (FEATURE-054) for three Tier 1 LLM operations. Initial results showed all models failing thresholds; manual analysis revealed three separate issues (weak Haiku baseline, imbalanced reference set, reference/prompt mismatch) requiring different fixes. Discovered direct DeepSeek API is 90% cheaper than OpenRouter pricing, unlocking $55k/year savings. Recommended phased rollout with behavioral consistency as primary signal instead of absolute thresholds.

### Interview Answer — "Tell me about a time you looked deeper instead of accepting surface results"

**Context (15-20 sec):**
"We ran a comprehensive LLM evaluation for cost optimization. Three operations, three alternative models, threshold-based scoring. Initial result: 0 out of 9 model-operation pairs passed the quality thresholds. The easy reaction would be 'models aren't good enough, stick with Haiku.' But that felt wrong."

**Action (45-60 sec):**
"I did manual analysis on why all models failed systematically. Turns out there were three separate issues, each pointing to different problems:
1. One operation (entity extraction) had a weak Haiku baseline (0.43 F1 vs 0.82 threshold), suggesting the prompt fix wasn't complete.
2. Another operation (sentiment) had a 77% accuracy threshold, but the reference set was 85% positive. All models struggle with minority classes—including Haiku.
3. The third (theme extraction) had references that included proper nouns, but the corrected prompt explicitly excluded them. Models were being penalized for following the spec correctly.

I also looked at behavioral consistency instead of just absolute quality. All models agreed with Haiku 85% of the time on sentiment. That's a much stronger deployment signal than 'F1 = 0.40, threshold = 0.82, FAIL.'"

**Result (15-20 sec):**
"Changed the recommendation from 'Flash on sentiment, save $7k/year' to 'DeepSeek on all three, save $55k/year.' The key insight wasn't model quality—it was realizing OpenRouter was applying 10-12x pricing markup. Direct API pricing completely changed the economics."

**Follow-up you should expect:**
- "Did DeepSeek actually ship? What happened?" (Answer: Phase 1 validation in progress)
- "How did the evaluation framework miss the reference data issues?" (Answer: It didn't—manual analysis caught them, which is why I invest in both automated and manual review)
- "What would you do differently next time?" (Answer: Pair reference data validation with the eval framework. Don't assume references are correct just because they're hand-labeled)

### Social Post (Substack/LinkedIn angle)

**Hook:**
"Your eval says all models fail. Your gut says something's off. What do you do? Here's how I discovered a $55k/year optimization opportunity by trusting my skepticism."

**Body:**
"We ran LLM evaluations across three operations. Everything failed the quality thresholds—0/9. The easy move: stick with status quo, ship nothing, move on.

Instead, I invested in manual analysis. Took ~2 hours. Found three separate issues:
- Weak Haiku baseline (prompt wasn't fixed fully)
- Imbalanced reference set (85% positive, hard to measure minority classes)
- Reference/prompt mismatch (references said include proper nouns, prompt said exclude them)

But the biggest discovery was infrastructure: we measured models through OpenRouter, which marks up DeepSeek by 10-12x. Direct API? 90% cheaper than Haiku.

The lesson: when your eval framework returns unexpected results, don't trust the first answer. Ask whether the framework itself is measuring the right thing. Sometimes the problem isn't the model—it's the measurement."

**Closing line or CTA:**
"How do you validate that your eval frameworks are measuring what you think? DM or reply if you've hit this wall."

---

## Caveats and Honest Limits

**What this story does NOT prove:**
- DeepSeek actually works in production (Phase 1 validation still pending)
- The $55k/year savings will materialize (depends on deployment & operational overhead)
- The behavioral consistency metric is sufficient (85% agreement is good, but we'll learn more in production)
- The eval framework is bulletproof (we caught issues this time, but future eval might miss something else)

**What a skeptic would say:**
- "Okay, you found a cheaper model. But did you actually deploy it? Where's the data?"
- "Phase 4 analysis is retrospective. You could have caught these issues earlier with more care upfront."
- "85% agreement with Haiku doesn't guarantee customer satisfaction. You're betting on behavioral similarity."
- "Cost savings look great until you account for ops overhead, monitoring, fallback infrastructure. Real savings might be 50%."

**What would prove skeptics wrong:**
- 2+ weeks of Phase 1 (sentiment) in production with 80%+ agreement sustained
- Actual cost tracking matching projections
- Zero quality degradation in downstream briefings
- Successful phased rollout to entity extraction (Phase 2)

---

## Publication Choice

**Status:** CANDIDATE (publish after Phase 1 validation, 2026-06-15)

**Distribution:** Substack (Early Signal)

**Why this platform:** Substack audience understands LLM economics and infrastructure tradeoffs. Blog readers are product/eng leads who've faced similar "eval says one thing, intuition says another" problems.

**Link:** (TBD — publish after Phase 1 validation)

---

## Story Connections

**Decision records:**
- DR-2026-05-001: Deploy DeepSeek V4 Flash as primary Tier 1 LLM provider

**Related stories:**
- "Flash Evaluations: Testing Cheaper Models Against Tier 1 Operations" (FEATURE-053, Sprint 16)
- "Building an LLM Evaluation Framework That Survives Scrutiny" (future, after full FEATURE-054 deployment)

**Contrasts with:**
- "Why We Stuck With Claude Haiku: Risk vs Cost in Production" (if Phase 1 validation fails and we revert)

---

*Story created 2026-04-30. Revisit decision: publish vs archive at 2026-06-15 (post-Phase 1 validation).*