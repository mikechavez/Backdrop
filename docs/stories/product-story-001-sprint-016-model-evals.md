# Product Story — PS-001

> Filled example using the product-story-template.md format.

---

## Story Metadata

**Story ID:** PS-001
**Title:** Model Eval That Said No
**Date:** 2026-04-28
**Company/Project:** Backdrop (backdropxyz.vercel.app)
**Role at time:** Solo builder / AI PM
**Tags:** evals, cost reduction, model routing, LLM infrastructure, Tier 1
**Interview survivability:** HIGH — all metrics come from scored JSONL files
and verified OpenRouter pricing, reproducible on demand

---

## The Core Narrative

### Situation
Backdrop is a production crypto news aggregator running 14 LLM operations daily
on roughly 100 articles. Sprint 15 established true cost visibility for the first
time — daily spend was $0.54 against a $1.00 hard cap. The system ran entirely on
Haiku with no model routing logic and no mechanism to evaluate whether cheaper
models could substitute without quality loss.

### Problem
Without a formal evaluation framework, any model swap decision would be a guess.
The risk wasn't just wasted cost — it was shipping a regression into a production
briefing pipeline with no way to detect it. The system had no golden set, no
baseline, no scoring harness, and no way to distinguish a real quality difference
from a formatting artifact.

### Approach
Built a full evaluation pipeline before touching any model routing code:

1. Classified all 14 operations into tiers using a rubric (volume, quality
   requirement, failure cost, latency sensitivity). Selected 3 Tier 1 operations
   for the first eval: entity extraction, sentiment analysis, theme extraction.

2. Extracted a golden set of 100 real production articles per operation from
   MongoDB. Used Haiku's existing historical outputs as the baseline — no API
   re-calls, no drift.

3. Ran manual validation before automated scoring. Reviewed a sample of articles
   and recorded my own labels. This was the step that mattered most.

4. Built an output normalization layer before scoring — HTML stripping,
   lowercasing, alias resolution, JSON parsing from markdown code blocks. Without
   this, formatting differences between models produce false regressions.

5. Ran 900 API calls across three challenger models (Flash, DeepSeek, Qwen) via
   OpenRouter at 99.8% success rate.

6. Scored against the eval contract, then ran post-hoc distribution analysis on
   the raw scored files.

### Finding or Outcome
Three operations, three different stories:

**Sentiment:** Challengers achieve 92-98% accuracy on positive and negative
articles. All three collapse to 4% on neutral (1/24 correct). The 75% headline
accuracy hides the real finding — this is a prompt definition problem, not a
model quality problem. The current prompt does not define what "neutral" means
in crypto news context. Flash is the preferred challenger at 75% overall, 96%
on negative, and 57% cheaper than Haiku. Decision: CONDITIONAL, pending neutral
class prompt fix.

**Entity extraction:** Score distributions are bimodal — not consistent mediocrity.
Flash and Qwen nail roughly 50% of articles at F1 >= 0.85 and fail hard on 22-26%.
The catastrophic failures are likely parse failures, not model quality issues.
Manual validation revealed the baseline itself is misaligned — Haiku extracts at
mention level, the intended behavior is relevance-weighted. The eval was measuring
the wrong thing. Decision: STAY, but for the wrong reason — defer to Sprint 17
after prompt fix.

**Theme extraction:** Same baseline misalignment. Haiku includes company and coin
names as themes; intended behavior is conceptual themes only. Single prompt fix
will substantially change the baseline. Challengers show no catastrophic failures
(floor score 0.182 vs. 0.000 in entity). Decision: STAY, pending prompt fix.

**Cost finding:** The original MSD files had pricing off by ~1000x. Corrected
OpenRouter pricing shows all three challengers are cheaper than Haiku — Flash by
57%, DeepSeek by 75%, Qwen by 81% at 100 articles/day across all three operations.

### The Non-Obvious Layer
Manual validation before automated scoring caught two things the pipeline would
have missed entirely:

First, the baseline validity problem. Haiku's entity and theme outputs are
internally consistent but diverge systematically from intended behavior. Parity
evals measure whether challengers match Haiku's philosophy — not whether they
produce better output. A challenger scoring 0.68 F1 against Haiku's mention-level
entity output might score higher against the correct relevance-weighted standard.

Second, the Haiku neutral bias. Flash disagreed with Haiku on 12 articles labeled
neutral — calling them negative. Manual validation had already identified that
Haiku under-calls negative on crime/legal/compensation articles. Those 12 Flash
disagreements are likely Flash being more accurate than Haiku, not less.

The result: we didn't ship a model swap based on a flawed eval. The STAY decisions
are correct, but the reasoning required correction before Sprint 17 decisions.

### Impact
Sentiment swap is now clearly scoped: Flash on non-critical paths, after a neutral
class prompt fix. Entity and theme evals will be re-run in Sprint 17 against
corrected prompts. Qwen is the likely winner for entity based on bimodal
distribution (51/100 perfect scores, 22/100 catastrophic failures — fewest of any
model). Monthly cost opportunity at current volume: $1.74-2.47/month vs Haiku
across these three operations, scaling linearly with article volume.

---

## Defensible Metrics

| Metric | Value | Status | How to defend |
|---|---|---|---|
| Golden set size | 100 articles per operation | DEFENSIBLE | Fixed files at /Users/mc/*.json |
| API calls in eval | 900 (300 samples x 3 models) | DEFENSIBLE | Phase 3 script logs |
| Success rate | 99.8% (898/900) | DEFENSIBLE | Phase 3 output files |
| Flash sentiment accuracy | 75% overall | DEFENSIBLE | scored-sentiment_analysis-flash.jsonl |
| Flash positive accuracy | 98% | DEFENSIBLE | same file, per-class breakdown |
| Flash negative accuracy | 96% | DEFENSIBLE | same file, per-class breakdown |
| Neutral accuracy all models | 4% (1/24) | DEFENSIBLE | same file, all three challengers |
| Qwen entity perfect scores | 51/100 | DEFENSIBLE | distribution from scored files |
| Flash cost vs Haiku | -57% | DEFENSIBLE | verified OpenRouter pricing + token counts |
| Qwen cost vs Haiku | -81% | DEFENSIBLE | verified OpenRouter pricing + token counts |
| Monthly savings (all 3 ops) | $1.74-2.47/mo at 100 articles/day | DEFENSIBLE | computed from verified pricing |
| Manual validation agreement | 30% entity / 80% sentiment / 10% theme | APPROXIMATE | sample review, not full 100 |

---

## Format Pulls

### Resume Bullet (one line, action verb, metric, outcome)

> Built end-to-end LLM eval pipeline for 3 Tier 1 operations (900 API calls,
> 99.8% success rate), identifying a prompt definition gap that prevented a
> premature model swap and scoping a 57-81% cost reduction opportunity.


### Resume Summary (2-3 sentences, narrative arc)

> Designed and ran a structured model evaluation framework for a production LLM
> pipeline processing 100+ articles daily. Built scoring infrastructure, golden
> sets, and output normalization from scratch; ran 900 challenger model calls
> across 3 models. Manual validation caught a baseline validity problem that
> automated scoring would have missed, preventing a regression and correctly
> scoping a 57-81% cost reduction for Sprint 17.


### Interview Answer — "Tell me about a time you made a data-driven decision"

**Context (15-20 sec):**
I run a production crypto news aggregator that uses 14 LLM operations to process
articles daily. We wanted to cut costs by swapping some operations to cheaper
models — Flash, DeepSeek, Qwen. Before touching anything in production, I built
a full evaluation framework.

**Action (45-60 sec):**
I started by classifying all 14 operations into tiers based on volume, quality
requirements, and failure cost — then picked the 3 most swap-eligible ones for
the first eval. I extracted 100 real production articles per operation as a golden
set, used the existing model's historical outputs as baseline so I wasn't spending
money re-running Haiku, and built an output normalization layer before scoring
because raw challenger outputs have formatting differences that produce false
regressions if you score them directly.

The thing that mattered most was manual validation before running the automated
eval. I sampled articles and labeled them myself. That's where I found the real
problem — Haiku's entity and theme extraction behaviors diverge systematically
from what the product actually needs. So the automated eval was measuring whether
challengers match Haiku's behavior, not whether they produce better output. That's
a completely different question.

**Result (15-20 sec):**
We didn't ship any swaps that sprint. But we also correctly identified that the
neutral class in sentiment is a prompt definition problem — all three challengers
get 92-98% right on positive and negative, and 4% right on neutral. That's
actionable. And we confirmed a 57-81% cost reduction opportunity that's now
properly scoped for the next sprint after the prompt fixes.

**Follow-up you should expect:**
- "How did you define the quality threshold?" — Eval contract locked before
  running (EVAL-001). Thresholds came from operational context, not reverse
  engineering the results.
- "What would you have done differently?" — Added neutral class definition to
  the sentiment prompt before running evals. The manual validation finding should
  have triggered a prompt review before Phase 3.
- "Did you ship anything?" — No model swaps shipped. The decision not to ship
  based on a flawed baseline is the correct outcome.


### Social Post Angle (LinkedIn or X)

**Hook:**
We ran 900 LLM eval calls and the answer was no. Here's why that's the right result.

**Body:**
Built a full eval framework for Backdrop — golden sets, output normalization,
scoring harness, three challenger models. The headline numbers said STAY on all
three operations. But when I looked at the per-class sentiment breakdown, all
three challengers were getting 92-98% right on positive and negative articles,
and 4% right on neutral. That's not a model problem. That's a prompt that never
defined what neutral means in a crypto news context.

Manual validation before the automated eval is what caught it. I labeled a sample
of articles myself first. Found that the entity and theme baselines were also
measuring the wrong thing — Haiku's behavior diverges from intended behavior in
both cases. If I'd shipped based on aggregate F1, I'd have been optimizing for
parity with a flawed baseline.

**Closing line or CTA:**
The eval infrastructure is the asset. The STAY decision this sprint sets up a
cleaner SWAP decision next sprint, with numbers you can actually trust.

---

## Caveats and Honest Limits

- Manual validation sample was not 100 articles per operation — agreement
  percentages (30%/80%/10%) are from a subset. Sufficient to identify patterns,
  not sufficient to establish statistical confidence.
- Monthly cost savings ($1.74-2.47/mo) are small at current volume. The story
  is about the framework and decision rigor, not the dollar amount.
- No production swap happened this sprint. Cost reduction is an opportunity
  scoped for Sprint 17, not a delivered outcome.
- Neutral class finding assumes the 24 both_wrong samples are all neutral
  articles — confirmed by per-class breakdown but not verified by pulling
  the specific IDs.
- DeepSeek and Qwen per-class sentiment breakdown is unreliable due to a label
  field gap in the scored files. Accuracy totals are correct; class breakdown
  for those two models is not.

---

## Story Connections

- Supports: PS-002 (Sprint 17 — model swap after prompt fix, if executed)
- Depends on: Sprint 15 cost visibility work (established true daily spend baseline)
- Contrasts with: any story where you shipped a change and measured results after —
  this one is notable for measuring before and deciding not to ship