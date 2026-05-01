---
id: TASK-086
type: task
status: in-progress
priority: P1
complexity: medium
created: 2026-04-30
updated: 2026-05-01
---

# TASK-086: Deploy DeepSeek Article Enrichment Batch to Production

## Status Summary (2026-05-01, Updated)

**Current Phase:** Pre-production smoke testing (COMPLETE — Ready for Phase 1 Production Validation)

| Component | Status | Notes |
|-----------|--------|-------|
| Mocked validation | ✅ PASS (8/8) | Routing, request/response, rollback, cost all verified |
| Live smoke test | ✅ PASS | Both Anthropic and DeepSeek working; credentials verified; traces recorded |
| Anthropic enrichment | ✅ SUCCESS | 3 test articles enriched (relevance 0.95/0.90/0.85, sentiment 0.75/-0.60/0.65) |
| DeepSeek enrichment | ✅ SUCCESS | 3 test articles enriched (relevance 0.90/0.80/0.60, sentiment 0.80/-0.60/0.70) |
| Routing mechanism | ✅ VERIFIED | Both providers route correctly through LLMGateway |
| Rollback capability | ✅ VERIFIED | One-line switch back to Anthropic confirmed working |
| Production deployment | ✅ READY | All pre-production validation complete; ready to proceed to Phase 1 |

**What happened (2026-05-01):**
1. ✅ Added credits to DeepSeek account
2. ✅ Ran live smoke test with Anthropic and DeepSeek routing
3. ✅ Anthropic enriched 3 test articles: sentiment agreement on all 3 (0.75, -0.60, 0.65)
4. ✅ DeepSeek enriched 3 test articles: sentiment close to Anthropic (0.80, -0.60, 0.70)
5. ✅ llm_traces recorded both providers: Anthropic $0.000722 (346 tokens), DeepSeek routing active
6. ✅ Rollback routing verified (one-line switch to Anthropic confirmed working)

**Next step:** Begin Phase 1 production validation — deploy to production and monitor 5-7 days of live traffic for sentiment agreement, parse success, latency, and cost.

## Problem

TASK-085 adds DeepSeek support behind `LLMGateway` using provider-prefixed model routing (`anthropic:*`, `deepseek:*`). The next step is to validate DeepSeek in production with a minimal, reversible rollout.

Important architecture constraint: the current production enrichment path batches relevance, sentiment, and themes into a single `article_enrichment_batch` LLM call. Therefore Phase 1 is **not** a pure `sentiment_analysis` deployment. Sentiment remains the primary validation metric because FEATURE-054 showed the strongest DeepSeek/Haiku consistency there, but the production routing unit is `article_enrichment_batch`.

This task must preserve the ability to switch back to Anthropic with a routing change only.

## Proposed Solution

Deploy DeepSeek in phases, using the actual production call path:

1. **Phase 1 — Article Enrichment Batch Rollout**
   - Route `article_enrichment_batch` to `deepseek:deepseek-v4-flash` through `LLMGateway`.
   - Validate sentiment as the primary quality metric.
   - Monitor relevance score sanity, theme parse quality, latency, errors, and cost.
   - Roll back by changing the routed model back to `anthropic:claude-haiku-4-5-20251001`.

2. **Phase 2 — Entity Extraction Rollout**
   - Only after Phase 1 is stable.
   - Route `entity_extraction` to DeepSeek in controlled mode.
   - Validate entity quality, parse correctness, downstream impact, latency, and cost.

3. **Phase 3 — Optional Theme-Specific Work**
   - Do not block Phase 1 on theme reannotation.
   - Theme output is already included in `article_enrichment_batch`, so monitor it during Phase 1.
   - If theme quality becomes important enough to validate independently, create or use a separate reannotation ticket after Phase 1.

TASK-087, the gateway-owned reliability refactor, is intentionally **not a blocker** for this rollout. TASK-086 uses the minimal TASK-085 architecture first; TASK-087 makes provider switching safer afterward.

## User Story

As an operations engineer, I want to deploy DeepSeek through the existing gateway and routing layer so that I can safely realize cost savings while preserving fast rollback to Anthropic.

## Non-Goals

- Do not split the enrichment pipeline in this task.
- Do not bypass `LLMGateway`.
- Do not add direct DeepSeek calls inside `anthropic.py`, `optimized_anthropic.py`, RSS services, or enrichment call sites.
- Do not make `LLM_PROVIDER=deepseek` the production rollout mechanism.
- Do not implement provider-scoped circuit breaker or rate limiter keys in this task. That belongs to TASK-087.
- Do not require theme reannotation before Phase 1.

## Acceptance Criteria

### Phase 1: Article Enrichment Batch Deployment

#### Pre-Production Validation (2026-05-01) ✅ MOCKED TESTS PASS
- [x] `article_enrichment_batch` routes to `deepseek:deepseek-v4-flash` through `LLMGateway` ✓
- [x] Existing enrichment call sites continue using the same public methods ✓
- [x] No direct DeepSeek calls are added outside the gateway ✓
- [x] Rollback is verified by changing routing back to `anthropic:claude-haiku-4-5-20251001` ✓
- [x] Request/response formatting validated for both providers ✓
- [x] Cost savings confirmed: 88.2% (DeepSeek 0.12x Anthropic) ✓

#### Live Production Validation (PENDING)
- [ ] 5-7 day production validation completed (after credentials available + live tests pass)
- [ ] Sentiment is validated as the primary quality signal:
  - Agreement target: >= 80% versus Haiku baseline or shadow comparison.
  - Alert threshold: < 75% sustained agreement.
- [ ] Theme output monitored for:
  - JSON parse correctness.
  - Expected list format.
  - Obvious regressions, such as empty themes for most articles or entity/proper-noun-heavy output.
- [ ] Relevance score monitored for:
  - Numeric parse correctness.
  - Range validity: 0.0-1.0.
  - Obvious distribution shift versus recent Haiku baseline.
- [ ] Latency monitored:
  - Target p95: < 5s for batch call.
  - Investigate if p95 exceeds 8s for sustained periods.
- [ ] Cost tracking validated:
  - `llm_traces` records DeepSeek model refs.
  - Token counts are present.
  - Cost uses DeepSeek pricing, not Haiku pricing.
- [ ] Error monitoring completed:
  - No recurring 401/403 auth errors.
  - No recurring 400/422 request-format errors.
  - 429/5xx errors are visible in logs/traces.
- [ ] Decision recorded:
  - KEEP DeepSeek for `article_enrichment_batch`, or
  - ROLLBACK to Anthropic, or
  - EXTEND validation with a clearly stated reason.

### Phase 2: Entity Extraction Deployment

- [ ] Start only after Phase 1 is stable or explicitly accepted.
- [ ] Route `entity_extraction` to `deepseek:deepseek-v4-flash` through `LLMGateway`.
- [ ] Validate on production-like traffic or a representative replay set.
- [ ] Track agreement/Jaccard versus Haiku baseline:
  - Target: >= 60% Jaccard similarity.
  - Investigate: 55-60%.
  - Rollback/defer: < 55% or frequent parse errors.
- [ ] Spot-check 10-15 disagreements.
- [ ] Categorize failures:
  - parse error
  - missing primary entity
  - hallucinated entity
  - acceptable variance
  - reference/baseline issue
- [ ] Verify downstream briefing quality is not degraded.
- [ ] Rollback path verified by changing `entity_extraction` routing back to Anthropic.
- [ ] Decision recorded:
  - KEEP DeepSeek,
  - ROLLBACK to Anthropic, or
  - DEFER pending prompt/output validation changes.

### Phase 3: Optional Theme-Specific Follow-Up

- [ ] Do not start until Phase 1 results show whether theme quality is acceptable inside `article_enrichment_batch`.
- [ ] If theme quality is acceptable, no separate theme ticket is required.
- [ ] If theme quality is questionable, create a separate theme reannotation / validation ticket.
- [ ] If a future standalone `theme_extraction` route is deployed to DeepSeek, follow the same validation/rollback pattern as Phase 2.

### General Requirements

- [ ] All production DeepSeek calls go through `LLMGateway`.
- [ ] Provider switching remains centralized in `_OPERATION_ROUTING`.
- [ ] One-line rollback to Anthropic is preserved for each routed operation.
- [ ] `llm_traces` remains the source of truth for cost and latency monitoring.
- [ ] Existing operation-level circuit breaker and rate limiter behavior remains in place.
  - **Important:** Circuit breaker and rate limiter are per-operation, not per-provider. Both Anthropic and DeepSeek share the same limits for `article_enrichment_batch`.
  - **Provider-scoped enforcement** (separate limits per provider) is TASK-087, not a blocker for Phase 1.
- [ ] TASK-087 is documented as a follow-up reliability refactor, not a prerequisite.

## Production Environment Variables

Railway must define these environment variables (do not use local `.env` or Keychain):

| Variable | Purpose | Example |
|----------|---------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API authentication | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API (for rollback/fallback if keeping) | `sk-ant-...` |
| `DEEPSEEK_DEFAULT_MODEL` | Explicit model reference | `deepseek-v4-flash` |
| `MONGODB_URI` | MongoDB connection to crypto_news database | `mongodb+srv://...` |
| `REDIS_URL` | Redis connection for caching and rate limiting | `redis://...` |

**Critical:** Do not commit `.env` files with production credentials. Use Railway dashboard or environment configuration system.

## Dependencies

- TASK-085: Add DeepSeek Support to LLMGateway and Route Enrichment Batch — must complete first. ✅ COMPLETE
- TASK-087: Refactor Gateway-Owned Reliability Controls — follow-up, not required before Phase 1.
- FEATURE-054: Tier 1 Cost Optimization Evals — completed; provides rationale and baseline DeepSeek confidence. ✅ COMPLETE

## Implementation Notes

### Phase 1 Routing Change

The production switch should be a routing change, not a call-site change.

Expected routing shape:

```python
_OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
    "article_enrichment_batch",
    primary="deepseek:deepseek-v4-flash",
)
```

Rollback shape:

```python
_OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
    "article_enrichment_batch",
    primary="anthropic:claude-haiku-4-5-20251001",
)
```

If TASK-085 implemented config-driven routing overrides, use that mechanism instead of editing code directly. The rollback requirement is the same: restoring Anthropic must not require call-site changes.

### A/B / Shadow Validation Setup

Preferred validation is shadow comparison through gateway-compatible paths.

Do **not** implement this by calling a standalone `deepseek_provider.call(...)` directly.

Acceptable approaches:

1. Replay recent enrichment inputs through both routed models in a validation script.
2. Add a temporary validation job that calls `LLMGateway` twice with explicit routing/model refs and stores comparison results.
3. Use existing evaluation harness if it can call the gateway path and preserve production prompt/output parsing.

Comparison record shape:

```json
{
  "article_id": "...",
  "operation": "article_enrichment_batch",
  "haiku": {
    "model": "anthropic:claude-haiku-4-5-20251001",
    "sentiment_score": 0.1,
    "relevance_score": 0.8,
    "themes": ["regulation", "market structure"],
    "input_tokens": 1234,
    "output_tokens": 120,
    "cost": 0.00123,
    "latency_ms": 950
  },
  "deepseek": {
    "model": "deepseek:deepseek-v4-flash",
    "sentiment_score": 0.0,
    "relevance_score": 0.75,
    "themes": ["regulation", "market structure"],
    "input_tokens": 1234,
    "output_tokens": 115,
    "cost": 0.00021,
    "latency_ms": 820
  },
  "agreement": {
    "sentiment_label_match": true,
    "sentiment_delta": 0.1,
    "theme_parse_ok": true,
    "relevance_delta": 0.05
  },
  "created_at": "2026-04-30T00:00:00Z"
}
```

### Sentiment Agreement Definition

Convert sentiment scores into labels before comparing:

- Bullish: `score > 0.3`
- Neutral: `-0.3 <= score <= 0.3`
- Bearish: `score < -0.3`

Agreement = percentage of articles where DeepSeek label equals Haiku label.

Target: >= 80%.
Investigate: 75-80%.
Rollback/defer: < 75% sustained.

### Theme Monitoring Definition

Theme output is not the primary Phase 1 decision gate, but must be monitored.

Track:

- Parse success rate.
- Empty theme rate.
- Average number of themes per article.
- Proper noun/entity-heavy outputs from spot checks.
- Obvious malformed outputs.

Rollback is required if theme parsing failures materially break downstream enrichment or briefing behavior.

### Relevance Monitoring Definition

Track:

- Parse success rate.
- Out-of-range scores.
- Distribution shift versus recent Haiku baseline.

Rollback is required if relevance scores become malformed or obviously unstable.

### Rollback Plan

Rollback must be possible in under 5 minutes.

Rollback steps:

1. Change `article_enrichment_batch` route from `deepseek:deepseek-v4-flash` to `anthropic:claude-haiku-4-5-20251001`.
2. Deploy or apply config override.
3. Run one smoke test enrichment batch.
4. Verify `llm_traces.model` shows Anthropic model refs again.
5. Watch application logs for 15-30 minutes.
6. Record rollback decision and reason.

Rollback must not require:

- Editing enrichment call sites.
- Removing DeepSeek gateway code.
- Changing stored article schemas.
- Changing global `LLM_PROVIDER`.

## Monitoring & Observability

### Dashboard Requirements

Create or update a simple dashboard/report visible during Phase 1:

```text
DeepSeek Article Enrichment Batch Rollout

Routed Operation:      article_enrichment_batch
Current Model:         deepseek:deepseek-v4-flash
Rollback Model:        anthropic:claude-haiku-4-5-20251001
Sentiment Agreement:   82%       target >= 80%
Parse Success:         99%       target >= 98%
Latency p50:           0.95s
Latency p95:           2.4s      investigate > 5s, rollback/defer > 8s sustained
Daily Cost:            $X.XX     compare vs Haiku projection
Error Rate:            0.2%      investigate > 1%
Rollback Status:       READY
```

### Alerts / Investigation Triggers

Investigate immediately if:

- Sentiment agreement drops below 75% sustained.
- JSON parse failures exceed 2%.
- Error rate exceeds 1%.
- Latency p95 exceeds 5s for sustained periods.
- Cost is materially higher than DeepSeek projection.
- `llm_traces` shows Haiku pricing for DeepSeek model refs.

Rollback or defer if:

- Sentiment agreement remains < 75% after investigation.
- Parse failures break downstream enrichment.
- DeepSeek request errors are recurring and not transient.
- Rollback test fails.

### Required Logs / Collections

Use existing observability where possible.

Required:

- `llm_traces` for model, operation, token counts, cost, duration, errors.
- Application logs for request/parse/fallback errors.
- Validation output file or collection for Haiku/DeepSeek comparison records.

Suggested validation output:

```text
docs/sprints/sprint-017-tier1-cost-optimization/validation/TASK-086-phase1-deepseek-enrichment-rollout.md
```

## Testing Plan

### Pre-Production Smoke Tests

#### Mocked Validation (2026-05-01) ✅ COMPLETE
- [x] Routing mechanism: `article_enrichment_batch` → `deepseek:deepseek-v4-flash` ✓
- [x] Model string parsing: provider-aware format handling ✓
- [x] Provider URL resolution: DeepSeek and Anthropic endpoints ✓
- [x] Request payload building: per-provider request format ✓
- [x] Response parsing: token extraction and text handling ✓
- [x] llm_traces record shape: all required fields validated ✓
- [x] Rollback routing: one-line switch to Anthropic verified ✓
- [x] Cost calculation: 88.2% savings (DeepSeek 0.12x Anthropic) ✓

**Results:** See `docs/sprints/sprint-017-tier1-cost-optimization/validation/TASK-086-PHASE1-MOCKED-SMOKE-TEST-RESULTS.md`

#### Live Smoke Tests (✅ COMPLETE - 2026-05-01)

**What this is:** Single or few real API calls to verify credentials work, routes execute, and traces record correctly. Does NOT fulfill Phase 1 validation.

- [x] Verify environment variables present: ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, MONGODB_URI ✓
- [x] Run one `article_enrichment_batch` call routed to DeepSeek through `LLMGateway` ✓
- [x] Confirm returns valid enrichment JSON ✓ (3 test articles, all themes/sentiment/relevance valid)
- [x] Confirm `llm_traces` records correct model ref (`deepseek:deepseek-v4-flash`) ✓
- [x] Confirm cost recorded with DeepSeek pricing ✓
- [x] Confirm rollback route restores Anthropic ✓
- [x] Run one `article_enrichment_batch` call routed to Anthropic (if account has credits) ✓
- [x] Document live test results ✓ (See `TASK-086-phase1-smoke-test-results.json`)

**Results:** Both Anthropic and DeepSeek working correctly. Live baseline available for Phase 1 validation.

**Prerequisites:** See `docs/sprints/sprint-017-tier1-cost-optimization/TASK-086-PHASE1-CREDENTIALS-CHECKLIST.md`

**Next:** Proceed to Phase 1 production validation. Live tests passed with baseline available.

### Phase 1 Validation

- [ ] Run validation on at least 50 representative articles, or production traffic for 5-7 days if volume is sufficient.
- [ ] Record sentiment agreement.
- [ ] Record parse success.
- [ ] Record latency p50/p95.
- [ ] Record cost per call and estimated daily cost.
- [ ] Spot-check at least 10 article outputs.
- [ ] Write decision record or validation report.

### Phase 2 Validation

- [ ] Run entity extraction comparison on representative articles.
- [ ] Calculate Jaccard agreement.
- [ ] Spot-check disagreements.
- [ ] Confirm downstream briefing quality remains acceptable.
- [ ] Write decision record or validation report.

## Decision Criteria

### Phase 1 KEEP DeepSeek

Keep DeepSeek for `article_enrichment_batch` if:

- Sentiment agreement >= 80%.
- Parse success >= 98%.
- No recurring request-format/auth errors.
- Latency is acceptable.
- Cost savings are visible in `llm_traces`.
- No obvious downstream briefing degradation.

### Phase 1 EXTEND Validation

Extend validation if:

- Sentiment agreement is 75-80%.
- Theme/relevance outputs are mostly valid but need more spot checks.
- Latency is higher than expected but not breaking production.
- Errors appear transient.

### Phase 1 ROLLBACK

Rollback to Anthropic if:

- Sentiment agreement < 75% sustained.
- Parse failures break enrichment.
- Request errors recur after obvious configuration fixes.
- Latency is unacceptable.
- Cost tracking is wrong and cannot be fixed quickly.

## Timeline & Effort

- **Phase 1:** 5-7 days validation + decision.
- **Phase 2:** 7-10 days validation after Phase 1 is accepted.
- **Phase 3:** Optional follow-up only if theme-specific quality requires it.

## Success Criteria

- [ ] Phase 1 complete: `article_enrichment_batch` safely validated on DeepSeek or rolled back with clear evidence.
- [ ] Rollback to Anthropic verified.
- [ ] Provider switchability preserved through `_OPERATION_ROUTING`.
- [ ] Cost savings documented from `llm_traces`.
- [ ] No direct DeepSeek call sites added outside gateway.
- [ ] TASK-087 remains queued as post-integration reliability refactor.
- [ ] Phase 2 decision made: proceed to entity rollout, defer, or stop.

## Completion Summary

*Fill in after completion.*

---

*Related: TASK-085 (DeepSeek gateway integration), TASK-087 (gateway-owned reliability refactor), FEATURE-054 (cost analysis).*
