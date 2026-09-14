# BUG-108: Operator Staging Validation Checklist

**Date:** 2026-09-14  
**Target:** Staging environment validation before production deployment  
**Duration:** ~45 minutes  
**Approver:** Operator only (no automated validation)

---

## Pre-Validation: Code Review

Operator should review the complete diff before staging:

```bash
# See full diff
git diff docs/bug-108-investigation

# Files changed (6 code files + 1 test file + docs):
#   context-owl-ui/src/pages/Signals.tsx              (UI: +4 lines)
#   src/crypto_news_aggregator/api/v1/endpoints/signals.py (+8 lines)
#   src/crypto_news_aggregator/background/rss_fetcher.py (+17 lines, fixed 2nd query)
#   src/crypto_news_aggregator/core/config.py        (+12 lines, new settings)
#   src/crypto_news_aggregator/db/mongodb.py         (+5 lines, null guard)
#   src/crypto_news_aggregator/db/operations/articles.py (+88 lines, dup handling restructured)
```

**Accept if:**
- ✅ No secrets (URIs, API keys, credentials) in diff
- ✅ Changes match ticket requirements (BUG-108 §1–4)
- ✅ Tests look reasonable (28 tests provided)

---

## Stage 1: Staging Deployment (5 min)

### 1.1 Deploy to Staging Environment

```bash
# On staging infrastructure
git fetch origin
git checkout docs/bug-108-investigation
git log -1 --oneline  # Verify commit

# Deploy (using your normal staging deployment process)
# Example (adjust for your CI/CD):
# make deploy-staging
# or
# ./scripts/deploy.sh staging
```

### 1.2 Verify Deployment Successful

```bash
# Health check
curl https://staging-api.yoursite.com/api/v1/health

Expected response (HTTP 200):
{
  "status": "ok",
  "database": "ok",
  "redis": "ok" or "degraded"
}

If not 200, STOP and investigate. Do not proceed.
```

---

## Stage 2: Unit and Integration Tests (10 min)

### 2.1 Run All BUG-108 Tests

```bash
poetry run pytest \
  tests/api/test_signals_timeframe_alignment.py \
  tests/db/test_mongodb_client_lifecycle.py \
  tests/background/test_enrichment_query_bounds.py \
  tests/db/test_article_duplicate_handling.py \
  -v

Expected output:
  28 passed, 62 warnings
```

**If tests fail:**
- Check if tests pass individually (rate limiting in batch runs)
- If any fail individually, STOP and investigate
- If only batch failures → rate limiting → proceed

### 2.2 Frontend Type Checking

```bash
cd context-owl-ui
npm run type-check

Expected: 0 errors
```

**If errors:** STOP and investigate. Do not proceed.

---

## Stage 3: Fresh Article → Signal Flow (15 min)

### 3.1 Verify Articles Being Ingested (Last 24 Hours)

Use MongoDB staging database (read-only queries only).

### 3.2 Verify Entity Mentions Created

Check for primary mentions in entity_mentions collection within 24h.

### 3.3 API Returns 24h Signals

```bash
curl -s "https://staging-api.yoursite.com/api/v1/signals/trending?timeframe=24h&limit=5" | jq '.'
```

Expected: count > 0, timeframe = 24h in filters

---

## Stage 4: Cache Behavior (10 min)

Verify 60-second cache TTL:
1. First request → computed_at = T0, cached = false
2. 5 seconds later → computed_at = T0, cached = true (hit)
3. 65 seconds later → computed_at = T1, cached = false (expired)

---

## Stage 5: Timeframe Alignment (5 min)

Verify:
- Default timeframe is 24h (no parameter → 24h)
- All three timeframes work: 24h, 7d, 30d

---

## Stage 6: MongoDB Client Health (5 min)

Check logs:
- 0 occurrences of "MongoClient after close"
- 0 occurrences of "database is None"
- Enrichment task logs present (recent extraction complete messages)

---

## Pass/Fail Criteria

**PASS** if all checks succeed:
- Tests: 28/28 passing
- Deployment: Health ok
- Data: Articles/mentions/signals present in 24h
- Timeframe: 24h default, 7d/30d working
- Cache: 60-second TTL verified
- Logs: No lifecycle errors

**FAIL** if any check fails:
- Stop staging validation
- Investigate root cause
- Retry after fix

---

## Operator Sign-Off

```
Staging validation PASSED:  [ ] YES  [ ] NO

Approved by: ________________  Date: ________________  Time: ________________
```

If YES, proceed to production deployment.  
If NO, investigate and retry.

---

**Ready for production deployment upon operator approval.**
