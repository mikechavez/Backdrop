---
ticket_id: TASK-014
title: Pre-Launch Security Hardening (DDoS, Rate Limiting, Attack Surface)
status: IN_PROGRESS
date_created: 2026-02-24
date_updated: 2026-02-26
priority: HIGH
severity: HIGH
---

# TASK-014: Pre-Launch Security Hardening — Comprehensive Audit

**Current Date:** 2026-02-26
**Sprint:** 11 (48-Hour Launch Window)
**Deadline:** Before public Substack launch (TASK-001)

---

## Executive Summary

Backdrop is preparing for public launch via Substack article (TASK-010). The application will move from closed beta to open internet exposure. This audit confirms existing security posture and identifies 4 critical gaps requiring implementation before launch.

**Status:** ✅ Audit complete. Implementation plan below.

---

## PART 1: ✅ Existing Security Controls (VERIFIED)

### 1. API Key Authentication ✅
- **Header:** `X-API-Key`
- **Validation:** Implemented in `core/auth.py` with proper error responses
- **Admin Endpoints:** Protected (e.g., `/admin/api-costs/summary` requires API key)
- **Risk:** Low — frontend key is placeholder only, real auth server-side

### 2. CORS Configuration ✅
- **Location:** `main.py` line 145-152
- **Configuration:** Regex pattern allows only:
  - `http://localhost:*` (dev)
  - `http://127.0.0.1:*` (dev)
  - `https://*.vercel.app` (production)
- **Impact:** Prevents unauthorized cross-origin requests
- **Risk:** Low — no wildcard, properly scoped

### 3. Frontend Secrets ✅
- **No Anthropic/OpenAI keys in bundle**
- **No sensitive data in `.env.example`**
- **API key is placeholder:** `VITE_API_KEY=your_api_key_here`
- **Vite config:** No hardcoded secrets
- **Risk:** Low — secrets properly isolated at backend

### 4. MongoDB Connection Pooling ✅
- **Library:** Motor (async MongoDB driver)
- **Pool Configuration:** Configurable `maxPoolSize` from settings
- **Default:** Set in `config.py` with reasonable limits
- **M0 Tier Limits:** 500 max connections (documented)
- **Risk:** Low — pooling prevents connection exhaustion

### 5. Cost Protection (Partial) ✅
- **BUG-039:** Sonnet fallback cost leak FIXED ✅
- **Entity extraction:** Uses Haiku only (no silent Sonnet escalation)
- **Anthropic costs:** Logged and traceable
- **Risk:** Medium — monitoring alerts not yet configured

### 6. Debug Endpoints Disabled ✅
- **OpenAPI docs:** Enabled at `/docs` (acceptable for beta)
- **ReDoc:** Enabled at `/redoc` (acceptable for beta)
- **No verbose error stack traces:** Error responses use `detail` field only
- **Risk:** Low — standard FastAPI documentation exposure

---

## PART 2: ⚠️ Critical Gaps (MUST IMPLEMENT)

### GAP #1: API Rate Limiting ⚠️ CRITICAL

**Current Status:** ❌ Not implemented
**Location:** Backend needs middleware
**Impact:** Without rate limiting, malicious actors can:
- Exhaust MongoDB M0 connection pool (500 limit)
- Trigger high Anthropic API costs (especially OpenAI compatibility endpoint)
- Cause service degradation for legitimate users
- Test for injection vulnerabilities with unlimited attempts

**Requirements:**
1. Implement FastAPI rate limiting middleware (e.g., `slowapi` or custom)
2. Apply per-IP limits to public endpoints:
   - **GET `/api/v1/signals/trending`** → 10 req/min (high cost)
   - **GET `/api/v1/briefing/latest`** → 20 req/min (medium cost)
   - **GET `/api/v1/signals/{entity}/articles`** → 30 req/min
   - **POST `/v1/chat/completions`** → 5 req/min (cost protection)
   - **Health checks** → No limit
3. Return HTTP 429 (Too Many Requests) on limit exceeded
4. Include `Retry-After` header for client retry guidance
5. Log rate limit violations with IP and endpoint for abuse detection

**Implementation Effort:** 30-45 minutes

---

### GAP #2: DDoS / Traffic Spike Protection ⚠️ HIGH

**Current Status:** ⚠️ Partial (relies on platform defaults)
**Location:** Railway (backend) + Vercel (frontend)
**Risk:** If launch goes viral, infrastructure could fail

#### Railway Backend Protection
- **Current:** Railway's standard tier includes basic DDoS protection
- **Gap:** No documented limits or escalation plan
- **Needed:**
  1. Verify Railway's DDoS protection coverage
  2. Document threshold limits (bandwidth, request count)
  3. Set up Railway spend alerts (already in cost monitoring)
  4. Plan for traffic > 100 concurrent users
  5. Consider upgrading to Railway's higher tier if needed

#### Vercel Frontend Protection
- **Current:** Vercel's enterprise CDN handles most DDoS automatically
- **Gap:** No explicit verification
- **Needed:**
  1. Confirm Vercel's DDoS protection is active (it is by default)
  2. Monitor response times via Vercel analytics
  3. Set up alerts for elevated 5xx error rates

**Implementation Effort:** 15-20 minutes (verification + documentation)

---

### GAP #3: Cost Monitoring & Spend Alerts ⚠️ HIGH

**Current Status:** ⚠️ Partial (admin endpoint exists, no alerts)
**Location:** Anthropic platform + Railway dashboard
**Risk:** Malicious API calls could generate unexpected bills

**Anthropic API Cost Monitoring:**
- [ ] Set spend limit on Anthropic dashboard
- [ ] Enable email alerts for 50%, 75%, 90%, 100% of monthly budget
- [ ] Document current daily spend baseline (for comparison)
- [ ] Configure alerts to notify before overspend

**Railway Cost Monitoring:**
- [ ] Enable spend limit in Railway dashboard
- [ ] Set alert threshold (e.g., $50/month for M0 + small API usage)
- [ ] Enable email notifications for overspend warnings

**Backend Metrics:**
- [ ] Ensure `/admin/api-costs/summary` endpoint is working
- [ ] Verify cost logging for all LLM calls
- [ ] Add hourly cost spike detection (e.g., alert if 10x normal)

**Implementation Effort:** 15-20 minutes (mostly config clicks)

---

### GAP #4: MongoDB Atlas M0 Limits & Contingency ⚠️ MEDIUM

**Current Status:** ⚠️ Limits documented but no contingency plan
**Location:** MongoDB Atlas cluster + application config
**Risks:**
- M0 free tier has 500 max concurrent connections
- M0 throughput is limited (~100 ops/sec sustained)
- No automatic failover or scaling available on free tier

**Limits to Document:**
```
MongoDB Atlas M0 Tier Limits:
- Max connections: 500
- Shared resources with other Atlas users
- Limited throughput (no SLA)
- No sharding available
- Max 512 MB storage (current usage: ~100 MB)
```

**Current Pool Configuration:**
- `MONGODB_MAX_POOL_SIZE` (from config.py): Verify default value
- `MONGODB_MIN_POOL_SIZE`: Verify default value
- Connection timeout: Verify settings

**Contingency Plan (Document):**
1. **Monitor connection usage:**
   - Add logging for connection pool status
   - Alert if connections exceed 300 (60% of limit)
2. **If traffic spikes:**
   - Temporarily disable non-critical background tasks (RSS fetcher, price monitor)
   - Reduce worker pool size to free connections
   - Escalate to paid MongoDB tier if sustained high traffic
3. **Graceful degradation:**
   - Health check endpoint reports pool status
   - API returns 503 if no connections available
   - Frontend shows maintenance message

**Implementation Effort:** 20-30 minutes (logging + documentation)

---

## PART 3: OPTIONAL ENHANCEMENTS (Post-Launch)

### Optional #1: API Key Management
- Rotate API keys regularly
- Implement API key rate limits per key (not just IP)
- Track API key usage by client

### Optional #2: Request Signing
- Add HMAC signature requirement for admin endpoints
- Implement webhook signatures for external integrations

### Optional #3: Web Application Firewall (WAF)
- Deploy Cloudflare in front of Railway (adds DDoS protection)
- Enable WAF rules for SQL injection, XSS, etc.
- Cost: ~$20/month

### Optional #4: Load Testing
- Use tools like k6 or Locust to simulate 1000+ concurrent users
- Identify bottlenecks before traffic surge
- Measure response times at 100, 500, 1000 concurrent users

---

## PART 4: IMPLEMENTATION CHECKLIST

### Phase 1: Rate Limiting (CRITICAL) — 45 min
- [ ] Install `slowapi` package or implement custom middleware
- [ ] Add rate limit middleware to FastAPI app
- [ ] Configure per-endpoint limits (see Gap #1)
- [ ] Add logging for limit violations
- [ ] Test with `curl -X GET http://localhost:8000/api/v1/signals/trending` (10+ times quickly)
- [ ] Verify 429 response on limit exceeded
- [ ] Commit: `feat(security): Add API rate limiting middleware`

### Phase 2: Cost Monitoring & Alerts (HIGH) — 30 min
- [ ] Verify Anthropic spend limit exists in dashboard
- [ ] Set alert thresholds: 50%, 75%, 90%, 100%
- [ ] Verify Railway spend limit in dashboard
- [ ] Enable Railway email alerts
- [ ] Document current daily baseline spend
- [ ] Test `/admin/api-costs/summary` endpoint
- [ ] Commit: `docs(security): Document cost monitoring setup`

### Phase 3: DDoS & Traffic Protection (HIGH) — 20 min
- [ ] Document Railway's DDoS protection coverage
- [ ] Document Vercel's DDoS protection coverage
- [ ] Identify traffic spike thresholds
- [ ] Document escalation plan for > 100 concurrent users
- [ ] Commit: `docs(security): Document DDoS & traffic protection`

### Phase 4: MongoDB Contingency (MEDIUM) — 30 min
- [ ] Verify `MONGODB_MAX_POOL_SIZE` and `MONGODB_MIN_POOL_SIZE` defaults
- [ ] Add connection pool monitoring to health check
- [ ] Document M0 tier limits and risks
- [ ] Write contingency plan document
- [ ] Add alerts if pool usage > 60%
- [ ] Commit: `docs(security): MongoDB M0 limits & contingency plan`

### Phase 5: Documentation (MEDIUM) — 20 min
- [ ] Create `docs/SECURITY_HARDENING.md` with all findings
- [ ] Link from README.md
- [ ] Add to Sprint 11 completion notes
- [ ] Commit: `docs(security): Add comprehensive security hardening guide`

**Total Effort:** ~2.5 hours (mostly implementation + testing)

---

## PART 5: ACCEPTANCE CRITERIA

### Rate Limiting ✅
- [ ] All public endpoints return 429 on rate limit
- [ ] Per-IP limits logged with endpoint and timestamp
- [ ] Retry-After header present in 429 responses
- [ ] Test coverage: load test with >10 requests/sec

### Cost Monitoring ✅
- [ ] Anthropic spend alerts configured
- [ ] Railway spend limit configured
- [ ] Admin cost endpoint tested and working
- [ ] Daily spend baseline documented

### DDoS/Traffic Protection ✅
- [ ] Railway DDoS coverage verified and documented
- [ ] Vercel CDN protection verified and documented
- [ ] Traffic spike escalation plan documented
- [ ] Health check reports pool/resource status

### MongoDB Safety ✅
- [ ] M0 tier limits documented (500 connections, throughput)
- [ ] Contingency plan written with escalation steps
- [ ] Pool monitoring added to health check
- [ ] Alert threshold set at 60% pool usage

---

## PART 6: RELATED TICKETS

- ✅ **BUG-039** — Sonnet fallback cost leak (MERGED)
- ✅ **BUG-042** — useInfiniteQuery refetch storm (MERGED)
- ✅ **TASK-016** — Observability + logging (MERGED)
- ⏳ **TASK-001** — Wire Substack URLs (depends on TASK-014 ✅)
- ⏳ **TASK-010** — Launch execution (depends on TASK-014 ✅)

---

## VERIFICATION CHECKLIST

### Before Marking Complete
- [ ] Rate limiting implemented and tested
- [ ] Cost alerts configured on Anthropic + Railway
- [ ] DDoS/traffic protection documented
- [ ] MongoDB limits documented with contingency plan
- [ ] All 4 implementation phases committed to git
- [ ] Security audit document updated
- [ ] No regressions to existing functionality
- [ ] Frontend still builds: `npm run build` ✅
- [ ] Backend tests still pass: `pytest tests/` ✅

---

## Notes

**Deployment:** Railway (production) handles auto-deployment on main branch push.

**Timeline:** This work unblocks TASK-001 (Wire Substack URLs) and TASK-010 (Launch execution).

**Post-Launch Monitoring:**
- Monitor rate limit violations daily
- Check cost trends and alert thresholds
- Track connection pool usage
- Review DDoS protection effectiveness

---

## Appendix: Security by Design

### What We Got Right
1. ✅ Secrets NOT in frontend bundle
2. ✅ CORS properly restricted (no wildcard)
3. ✅ API key validation on protected endpoints
4. ✅ MongoDB connection pooling
5. ✅ Cost protection (Sonnet fallback fixed)
6. ✅ Async/concurrent request handling
7. ✅ Proper error responses (no stack traces)

### What We're Adding
1. ⚠️ → ✅ **Rate limiting** (by endpoint + IP)
2. ⚠️ → ✅ **Cost monitoring & alerts** (Anthropic + Railway)
3. ⚠️ → ✅ **DDoS/traffic documentation** (plan for spikes)
4. ⚠️ → ✅ **MongoDB M0 contingency** (graceful degradation)

### What We're Monitoring
- API response latencies (signals page, trending, briefing)
- Cache hit rates (entity articles, signals)
- Cost trends by operation (entity extraction, LLM calls)
- Error rates and types (4xx, 5xx)
- Connection pool usage and timeouts
- Rate limit violations by IP and endpoint
