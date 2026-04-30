---
id: TASK-086
type: task
status: backlog
priority: P1
complexity: medium
created: 2026-04-30
updated: 2026-04-30
---

# TASK-086: Deploy DeepSeek to Production (Phased Rollout)

## Problem

TASK-085 builds DeepSeek provider integration in isolation. This task validates and deploys it to production with phased rollout strategy, monitoring, and rollback capability.

## Proposed Solution

Three-phase production deployment:
1. **Phase 1 (Sentiment):** Full cutover on sentiment_analysis (lowest risk, highest consistency)
2. **Phase 2 (Entity):** Parallel run + validation on entity_extraction, then cutover
3. **Phase 3 (Theme):** After reannotation (TASK-087); optional depending on TASK-087 timeline

## User Story

As an operations engineer, I want to deploy DeepSeek to production with validation and rollback capability so that I can safely realize $54k/year cost savings while maintaining quality.

## Acceptance Criteria

### Phase 1: Sentiment Analysis Deployment
- [ ] DeepSeek routed to sentiment_analysis operation in production
- [ ] A/B test for 5-7 days: parallel Haiku + DeepSeek calls
  - Track: agreement rate (target >= 80%), latency, cost
  - Verify: no degradation vs Haiku baseline
- [ ] Rollback plan defined and tested (revert sentiment to Haiku in 5 min)
- [ ] Monitoring dashboard created: sentiment agreement, latency p50/p95, daily cost
- [ ] Decision: SWAP to 100% DeepSeek or STAY on Haiku

### Phase 2: Entity Extraction Deployment
- [ ] DeepSeek routed to entity_extraction in production (parallel mode)
- [ ] A/B test for 7-10 days: parallel Haiku + DeepSeek
  - Track: agreement rate (target >= 60%), latency, cost
  - Validate: F1 scores acceptable for downstream analysis
  - Flag: any parse errors, extraction quality issues
- [ ] Spot-check 10-15 failed entity extractions from DeepSeek
  - Categorize: parse error | legitimate quality gap | acceptable variance
  - Decision: proceed with cutover or defer
- [ ] Rollback plan defined and tested (revert entity to Haiku in 5 min)
- [ ] Decision: SWAP to 100% DeepSeek, CONDITIONAL (with validation), or STAY

### Phase 3: Theme Extraction Deployment
- [ ] Depends on TASK-087 completion (reannotation)
- [ ] If TASK-087 done: follow same A/B test pattern as Phase 2
- [ ] If TASK-087 deferred: skip Phase 3 for now

### General Requirements (All Phases)
- [ ] Cost tracking validated: verify DeepSeek costs match projected savings
- [ ] Error handling tested: verify fallback to Haiku on DeepSeek errors
- [ ] Rate limiting tested: verify no unexpected throttling from DeepSeek
- [ ] Production logs monitored: no recurring errors, no performance regressions
- [ ] Stakeholder review: approval before each phase cutover

## Dependencies

- TASK-085: Build DeepSeek Provider Integration (must complete first)
- TASK-087: Re-annotate Theme Extraction Samples (optional, before Phase 3)

## Implementation Notes

### Phase 1: Sentiment Analysis (Lowest Risk)

**Timeline:** 1 week A/B test, then cutover

**Metrics to track:**
- Agreement rate: % of articles where DeepSeek label == Haiku label (target >= 80%)
- Latency: p50, p95 per article (target < 3s p95)
- Cost: verify $X/day actual matches $X/day projected
- Errors: count, type, rate

**A/B Test Setup:**
```python
# In enrichment pipeline
haiku_sentiment = await haiku_provider.call(sentiment_prompt)
deepseek_sentiment = await deepseek_provider.call(sentiment_prompt)

# Log both results
store_enrichment(article_id, {
    "haiku_sentiment": haiku_sentiment,
    "deepseek_sentiment": deepseek_sentiment,
    "agreement": haiku_sentiment.label == deepseek_sentiment.label
})

# Store in MongoDB for analysis
```

**Decision Criteria:**
- ✅ SWAP (cutover to 100% DeepSeek) if:
  - Agreement >= 80% sustained over 5+ days
  - Latency acceptable (p95 < 3s)
  - No recurring errors
  - Cost aligns with projections
  
- ⚠️ CONDITIONAL (conditional cutover) if:
  - Agreement 75-80% (acceptable minor variance)
  - Latency acceptable
  - Cost wins override minor quality variance
  
- ❌ STAY (revert to Haiku) if:
  - Agreement < 75%
  - Latency issues (p95 > 5s)
  - Recurring errors

**Rollback Plan:**
- Config: one-line switch `SENTIMENT_ANALYSIS_PROVIDER=haiku` vs `deepseek`
- Execution: 5-minute switchover, no data loss
- Monitoring: immediately verify agreement rate drops to 100% (now comparing Haiku to itself)

### Phase 2: Entity Extraction (Medium Risk)

**Timeline:** 7-10 day A/B test

**Metrics to track:**
- Agreement (Jaccard similarity): % of entity lists that overlap (target >= 60%)
- F1 scores: validate extracted entities still useful downstream
- Latency: p50, p95 (target < 5s p95)
- Parse errors: count, rate (should be near zero)
- Cost savings: verify vs Phase 1 sentiment baseline

**A/B Test Setup:**
```python
# Parallel extraction
haiku_entities = await haiku_provider.call(entity_prompt)
deepseek_entities = await deepseek_provider.call(entity_prompt)

# Calculate agreement
jaccard = len(intersection) / len(union)

# Log for analysis
store_enrichment(article_id, {
    "haiku_entities": haiku_entities,
    "deepseek_entities": deepseek_entities,
    "jaccard_similarity": jaccard,
})
```

**Spot-Check Protocol:**
- Day 3: Review 5 disagreements, categorize failure mode
- Day 7: Review 10 disagreements, look for patterns
- Before cutover: Final 10 spot-checks from latest batch

**Decision Criteria:**
- ✅ SWAP if:
  - Agreement >= 60% sustained
  - Spot-check failures are parse errors (fixable), not quality gaps
  - Latency acceptable
  - No performance degradation downstream
  
- ⚠️ CONDITIONAL if:
  - Agreement 55-60%
  - Failures are legitimate quality gaps but don't block analysis
  - Require output validation layer (confidence filtering)
  - Proceed with caution
  
- ❌ STAY if:
  - Agreement < 55%
  - Frequent parse errors
  - Spot-checks reveal quality unacceptable

**Rollback Plan:**
- Same as Phase 1: config switch + 5-minute revert
- Extra: maintain both Haiku + DeepSeek outputs in DB for 1 week (reverting keeps history)

### Phase 3: Theme Extraction (Conditional)

**Prerequisites:** TASK-087 (reannotation) must be complete

**Timeline:** 7-10 day A/B test

**Metrics:**
- Agreement (Jaccard similarity): % themes that match
- F1 vs reannotated references
- Latency, errors, cost

**Decision:** Follow same framework as Phase 2

---

## Monitoring & Observability

### Dashboard Requirements

Create a Grafana/metrics dashboard visible during all phases:

```
┌─────────────────────────────────────────────────────┐
│ DeepSeek Deployment Metrics (Phase 1: Sentiment)   │
├─────────────────────────────────────────────────────┤
│ Agreement Rate:        82% (target: >= 80%)         │
│ Latency p50:           0.95s                        │
│ Latency p95:           2.4s                         │
│ Daily Cost:            $2.50 (vs $3.40 Haiku)      │
│ Errors (24h):          0 (0%)                       │
│ Rollback Status:       READY (config switch)        │
└─────────────────────────────────────────────────────┘
```

### Alerting

Set up alerts for:
- Agreement rate drops below 75% (investigate immediately)
- Latency p95 > 5s for 5+ min (check DeepSeek API status)
- Error rate > 1% (investigate error logs)
- Cost significantly higher than projected (verify token counting)

### Logging

All DeepSeek calls logged to:
- `llm_traces` collection (standard, for cost tracking)
- `enrichment_log` (with agreement/variance details for analysis)
- Application logs (errors, warnings)

---

## Open Questions

- [ ] Is a 5-7 day A/B test sufficient for Phase 1, or should we extend to 2 weeks?
- [ ] Phase 2 agreement threshold: is 60% Jaccard enough, or should it be higher?
- [ ] Should we implement continuous A/B testing after cutover (e.g., 10% of traffic still goes to Haiku)?
- [ ] Rollback threshold: auto-revert if agreement drops below X%, or manual decision?

## Timeline & Effort

- **Phase 1 (Sentiment):** 1 week (5 days A/B + 2 days decision/cutover)
- **Phase 2 (Entity):** 2 weeks (7-10 days A/B + 3-5 days decision/cutover)
- **Phase 3 (Theme):** Depends on TASK-087 timeline
- **Total (all three):** 3-4 weeks

## Success Criteria

- [ ] Phase 1 complete: DeepSeek live on sentiment, monitoring stable, cost savings realized
- [ ] Phase 2 complete (optional): DeepSeek live on entity, validation done, decision made
- [ ] Phase 3 complete (optional): DeepSeek live on theme, reannotation validated
- [ ] Annual cost savings documented: $X realized from each phase
- [ ] Monitoring & rollback capability verified
- [ ] Team trained on deployment, monitoring, rollback

## Completion Summary

*Fill in after completion*

---

*Related: TASK-085 (provider build), TASK-087 (theme reannotation), FEATURE-054 (cost analysis)*