---
id: TASK-086-PRODUCTION-DEPLOY
type: checklist
status: deployed-monitoring
created: 2026-05-01
updated: 2026-05-01
---

# TASK-086 Phase 1: Post-Deployment Monitoring Checklist

## Status

✅ **Production deployment:** COMPLETE  
DeepSeek-backed `article_enrichment_batch` is now live in production.

TASK-086 is now in **Phase 1 production validation**.

---

## Objective

Validate DeepSeek in production using real traffic and decide:

- KEEP DeepSeek
- ROLLBACK to Anthropic
- EXTEND validation

Validation window: **5–7 days or sufficient production volume**

---

## Immediate Post-Deploy Checklist

Run these **now (once)** after deployment:

- [ ] Confirm Railway deployment completed successfully
- [ ] Check Railway logs for:
  - missing env vars
  - auth errors (401/403)
  - request errors (400/422)
  - DB connection errors
  - Redis errors
- [ ] Confirm routing is active:
  - `article_enrichment_batch → deepseek:deepseek-v4-flash`
- [ ] Run one production smoke enrichment

### Validate Smoke Output

- [ ] Relevance score is numeric (0.0–1.0)
- [ ] Sentiment score is numeric
- [ ] Themes are valid list output
- [ ] No parsing errors

### Validate Traces Immediately

- [ ] `llm_traces` has new records
- [ ] `model` shows `deepseek:deepseek-v4-flash`
- [ ] `provider` is correct
- [ ] `input_tokens` and `output_tokens` present
- [ ] `cost` reflects DeepSeek pricing (NOT Haiku)
- [ ] `duration_ms` populated
- [ ] `cached` behavior looks correct

### Validate Error Surface

- [ ] No recurring 401/403 errors
- [ ] No recurring 400/422 errors
- [ ] No spikes in 429 or 5xx errors

---

## Rollback Readiness (CRITICAL)

Ensure rollback is ready **before monitoring continues**:

**Rollback route:**
```python
primary="anthropic:claude-haiku-4-5-20251001"
```

- [ ] Rollback path confirmed (no code changes required outside routing)
- [ ] Rollback can be deployed in < 5 minutes
- [ ] Smoke test after rollback is known and ready

---

## Daily Monitoring Checklist (Days 1–7)

Run this **once per day**:

### Volume & Cost

- [ ] Count of DeepSeek calls (last 24h)
- [ ] Average cost per call
- [ ] Total daily cost
- [ ] Cost matches expected DeepSeek range (~0.12x Haiku)

### Latency

- [ ] Average latency
- [ ] p95 latency
  - Investigate if > 5s
  - Rollback if sustained > 8s

### Errors

- [ ] Total error count
- [ ] Error rate
  - Investigate if > 1%
- [ ] Inspect recent error messages

### Parse & Output Quality

- [ ] JSON parse success rate
  - Target ≥ 98%
- [ ] No malformed outputs
- [ ] Themes format correct
- [ ] No empty or broken responses

### Spot Check Outputs (VERY IMPORTANT)

Check at least a few real outputs:

- [ ] Relevance scores look reasonable
- [ ] Sentiment feels directionally correct
- [ ] Themes are coherent (not garbage or entities-only)
- [ ] No obvious degradation in briefing quality

---

## Phase 1 Decision Criteria

After 5–7 days (or enough traffic), make a decision:

---

### ✅ KEEP DeepSeek

Keep if ALL are true:

- Sentiment agreement ≥ 80%
- Parse success ≥ 98%
- Error rate < 1%
- Latency acceptable
- Cost savings confirmed
- No noticeable degradation in output quality

---

### ❌ ROLLBACK to Anthropic

Rollback if ANY are true:

- Sentiment agreement < 75% sustained
- Parse failures break enrichment
- Repeated provider/API errors
- Latency unacceptable
- Cost tracking incorrect
- Output quality degrades noticeably

---

### ⏳ EXTEND Validation

Extend if:

- Results are borderline (75–80%)
- Not enough traffic yet
- Minor issues need more observation
- Errors appear transient

---

## Decision Record Template

```md
## Phase 1 Decision (DATE)

**Validation Period:** YYYY-MM-DD → YYYY-MM-DD

**Metrics:**
- Sentiment Agreement: X%
- Parse Success: X%
- Latency p95: X ms
- Daily Cost: $X
- Error Rate: X%

**Decision:** KEEP / ROLLBACK / EXTEND

**Rationale:**
[Explain reasoning]

**Next Step:**
[Proceed to Phase 2 / Investigate / Extend]
```
