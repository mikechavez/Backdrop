---
id: TASK-086-PRODUCTION-DEPLOY
type: checklist
status: ready-for-deployment
created: 2026-05-01
---

# TASK-086 Phase 1: Production Deployment Checklist

## Pre-Deployment Status

✅ **Pre-production validation:** COMPLETE
- Mocked validation: 8/8 tests pass
- Live smoke tests: Both Anthropic and DeepSeek working
- Routing verified: Both providers route through LLMGateway
- Rollback verified: One-line switch to Anthropic confirmed
- Cost tracking: DeepSeek pricing defined, cost calculation verified

✅ **Code changes:** Ready to deploy
- DeepSeek gateway integration (TASK-085): ✅ Complete
- Cost tracking fix for DeepSeek: ✅ Complete
- Tracing capability: ✅ Complete

---

## Production Environment Setup

### 1. Railway Environment Variables

Set these in Railway dashboard before deployment:

| Variable | Value | Purpose |
|----------|-------|---------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Fallback/rollback provider |
| `DEEPSEEK_API_KEY` | `sk-...` | Primary provider for Phase 1 |
| `MONGODB_URI` | `mongodb+srv://...` | **MUST be write-capable user** for llm_traces |
| `REDIS_URL` | `redis://...` | Caching and rate limiting |
| `DEEPSEEK_DEFAULT_MODEL` | `deepseek-v4-flash` | Explicit model reference |

**Critical:** Use the write-capable MongoDB user (not read-only agent user) so llm_traces can be recorded.

### 2. Verify Deployment Variables

Before deploying, confirm in Railway dashboard:
- [ ] `ANTHROPIC_API_KEY` is set
- [ ] `DEEPSEEK_API_KEY` is set
- [ ] `MONGODB_URI` uses write-capable credentials
- [ ] `REDIS_URL` is set
- [ ] All secrets are hidden in dashboard (not visible in logs)

---

## Deployment Steps

### Step 1: Merge to Main

```bash
# Create PR (if not already open)
git push origin feat/task-085-deepseek-gateway

# In GitHub: Create PR against main
# Title: "feat(task-085): Add DeepSeek support via LLMGateway"
# Base: main
```

Requirements before merge:
- [ ] All tests pass (CI/CD green)
- [ ] Code review approved
- [ ] Changes match TASK-085 acceptance criteria
- [ ] Changes match TASK-086 acceptance criteria

### Step 2: Update Production Routing

The routing is already in place from TASK-085. Confirm in production code:

**File:** `src/crypto_news_aggregator/llm/gateway.py` (lines ~150-153)

```python
_OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
    "article_enrichment_batch",
    primary="deepseek:deepseek-v4-flash",  # <-- Confirm this is set
)
```

If still pointing to Anthropic, update to:
```python
_OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
    "article_enrichment_batch",
    primary="deepseek:deepseek-v4-flash",  # <-- Change to DeepSeek
)
```

**Verification:** This should already be set from TASK-085. If not, create a fix commit.

### Step 3: Deploy to Production

```bash
# Push merged main to Railway
git push origin main

# Railway auto-deploys or manually trigger in Railway dashboard
# Monitor deployment logs: Railway → Deployments → [latest]
```

Expected output in logs:
- ✅ Application starts successfully
- ✅ No authentication errors
- ✅ No database connection errors
- ✅ No missing environment variable errors

### Step 4: Run Post-Deployment Smoke Test

Once deployed, run one quick smoke test against production:

```bash
# From production environment (or via Railway shell)
poetry run python scripts/task_086_phase1_smoke_test.py
```

Expected results:
- ✅ Anthropic enrichment works (baseline available)
- ✅ DeepSeek enrichment works (primary provider active)
- ✅ Both write traces to production llm_traces
- ✅ Cost shows DeepSeek pricing
- ✅ Rollback routing verified

---

## Phase 1 Monitoring (5-7 Days)

### Monitoring Metrics

Track these in production llm_traces collection:

**Sentiment Agreement (PRIMARY METRIC)**
- Target: ≥ 80% agreement with Haiku baseline
- Track: Percentage of articles where sentiment label matches (Bullish/Neutral/Bearish)
- Alert if: < 75% sustained agreement
- Action if triggered: Investigate and potentially rollback

**Parse Success**
- Target: ≥ 98% successful parsing
- Track: JSON parse success, relevance score range, themes list format
- Alert if: > 2% parse failures
- Action if triggered: Investigate format issues, potentially rollback

**Latency**
- Target: p95 < 5 seconds
- Track: `duration_ms` from llm_traces
- Investigate if: p95 exceeds 5s sustained
- Rollback if: p95 exceeds 8s sustained

**Cost**
- Expected: ~88% savings vs Haiku (DeepSeek ~$0.00021 per call vs Haiku ~$0.00072)
- Track: Sum of `cost` from llm_traces per day
- Verify: Cost uses DeepSeek pricing, not Haiku pricing (from cost_tracker fix)
- Alert if: Cost materially higher than expected

**Error Rate**
- Target: < 1% error rate
- Track: Records with non-null `error` field
- Alert if: > 1% sustained
- Action: Investigate error messages, check API status

### Daily Monitoring Checklist

Day 1-7, run daily:

```bash
# Example: Query llm_traces for today
db.llm_traces.aggregate([
  {
    $match: {
      operation: "article_enrichment_batch",
      model: "deepseek:deepseek-v4-flash",
      timestamp: {
        $gte: new Date(ISODate().getTime() - 86400000) // last 24h
      }
    }
  },
  {
    $group: {
      _id: null,
      count: { $sum: 1 },
      avg_cost: { $avg: "$cost" },
      total_cost: { $sum: "$cost" },
      avg_duration: { $avg: "$duration_ms" },
      errors: { $sum: { $cond: ["$error", 1, 0] } }
    }
  }
])
```

Expected output:
- `count`: Number of calls
- `avg_cost`: ~$0.00021 (DeepSeek pricing)
- `total_cost`: Daily cost estimate
- `avg_duration`: Typical latency
- `errors`: Count of failed calls (should be low)

### Decision Record Template

After 5-7 days, record the Phase 1 decision in TASK-086:

```markdown
## Phase 1 Decision (DATE)

**Validation Period:** 2026-05-01 to 2026-05-XX (X days)

**Metrics:**
- Sentiment Agreement: X%
- Parse Success: Y%
- Latency p95: Zms
- Daily Cost: $XXX
- Error Rate: A%

**Decision:** KEEP / ROLLBACK / EXTEND

**Rationale:** [Explain decision based on metrics]

**Next Step:** [Proceed to Phase 2 / Investigate X / Extend for Y days]
```

---

## Rollback Plan (< 5 Minutes)

If Phase 1 validation shows problems, rollback with these steps:

### Step 1: Change Routing

Edit `src/crypto_news_aggregator/llm/gateway.py` line ~150:

From:
```python
primary="deepseek:deepseek-v4-flash",
```

To:
```python
primary="anthropic:claude-haiku-4-5-20251001",
```

### Step 2: Deploy Rollback

```bash
git add src/crypto_news_aggregator/llm/gateway.py
git commit -m "fix(task-086): Rollback article_enrichment_batch to Anthropic"
git push origin main

# Railway auto-deploys or manually trigger
```

### Step 3: Verify Rollback

Run smoke test to confirm routing is back to Anthropic:

```bash
poetry run python scripts/task_086_phase1_smoke_test.py
```

Expected:
- ✅ llm_traces shows `model: "anthropic:claude-haiku-4-5-20251001"`
- ✅ Cost reflects Haiku pricing
- ✅ No errors

### Step 4: Document Rollback

Record in TASK-086:

```markdown
## Rollback (DATE)

**Reason:** [e.g., Sentiment agreement < 75%, Parse failures exceeded 2%, etc.]

**Time to rollback:** X minutes

**Verification:** Smoke test passed, Anthropic routing confirmed

**Next Steps:** [Investigate root cause, schedule Phase 2 or defer]
```

---

## Phase 2 Preparation (After Phase 1 Decision)

### If Phase 1 is KEEP or EXTEND:

Proceed to Phase 2 when Phase 1 is stable:

```markdown
## Phase 2: Entity Extraction Rollout

1. Update routing: `entity_extraction` → `deepseek:deepseek-v4-flash`
2. Monitor for 5-7 days
3. Track Jaccard agreement vs Haiku baseline
4. Validate downstream briefing quality
5. Make KEEP/ROLLBACK decision
```

See TASK-086 Phase 2 section for full details.

### If Phase 1 is ROLLBACK:

Document findings and decide:
- **Fix and retry:** Adjust prompts/output parsing, re-test
- **Defer:** Investigate issues, schedule retry for later
- **Cancel:** Mark Phase 1 as not ready, remain on Anthropic

---

## Success Criteria

Phase 1 production deployment is **successful** if:

- ✅ All environment variables set in Railway
- ✅ Post-deployment smoke test passes
- ✅ 5-7 days of monitoring completed
- ✅ Sentiment agreement ≥ 80% (or decision made to investigate)
- ✅ Parse success ≥ 98%
- ✅ Latency p95 < 5s
- ✅ Error rate < 1%
- ✅ Cost savings verified (~88% vs Haiku)
- ✅ Rollback capability verified (tested during validation)
- ✅ Phase 1 decision recorded (KEEP/ROLLBACK/EXTEND)

---

## Contacts & Escalation

If issues arise during deployment or monitoring:

1. **Deployment issues:** Check Railway logs, verify environment variables
2. **API credential issues:** Verify keys in Railway dashboard, check provider status
3. **Database issues:** Verify MongoDB URI uses write-capable user, check Atlas dashboard
4. **Quality issues:** See Decision Criteria section, record decision, decide on rollback

---

**Status:** Ready to deploy once main branch is updated and Railway environment variables are configured.
