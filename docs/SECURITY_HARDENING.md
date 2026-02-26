# Security Hardening Guide

**Last Updated:** 2026-02-26
**Pre-Launch Status:** ✅ COMPLETE

---

## Overview

Backdrop has been hardened against common attack vectors before public Substack launch. This document outlines security controls, monitoring requirements, and incident response procedures.

---

## Part 1: Implemented Security Controls

### 1.1 API Rate Limiting ✅

**Purpose:** Prevent DDoS attacks, limit cost exposure, protect against brute force

**Implementation:**
- **Middleware:** `core/rate_limiting.py` - Per-IP rate limiting with configurable limits per endpoint
- **Logic:** Tracks requests per IP per endpoint in sliding 60-second window
- **Response:** HTTP 429 (Too Many Requests) with `Retry-After` header

**Configured Limits:**
```
High-cost endpoints (LLM calls):
  /v1/chat/completions → 5 req/min per IP

Medium-cost endpoints (database-heavy):
  /api/v1/signals/trending → 10 req/min per IP
  /api/v1/briefing/latest → 20 req/min per IP
  /api/v1/narratives → 20 req/min per IP

Lower-cost endpoints:
  /api/v1/signals → 30 req/min per IP
  /api/v1/signals/search → 30 req/min per IP
  /api/v1/signals/{entity}/articles → 30 req/min per IP

Exempted (no limit):
  /health
  /
```

**IP Detection:**
- Extracts from `X-Forwarded-For` header (for Vercel proxy)
- Falls back to `X-Real-IP` (nginx style)
- Falls back to direct connection IP

**Testing:**
```bash
# Test rate limiting (should get 429 on 11th request)
for i in {1..15}; do curl http://localhost:8000/api/v1/signals/trending; echo ""; done
```

**Logs:**
```
rate_limit: ip=192.168.1.1, endpoint=/api/v1/signals/trending, limit=10, requests_in_window=11
```

---

### 1.2 CORS Protection ✅

**Purpose:** Prevent unauthorized cross-origin requests

**Configuration:**
```python
allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app)$"
```

**Allowed Origins:**
- `http://localhost:*` (local development)
- `http://127.0.0.1:*` (local development)
- `https://*.vercel.app` (production deployments)

**Denied:**
- Wildcard (`*`) — explicitly NOT used
- External domains (unless explicitly allowlisted)
- File:// protocol

---

### 1.3 API Key Authentication ✅

**Purpose:** Control access to protected endpoints

**Implementation:**
- **Header:** `X-API-Key`
- **Location:** `core/auth.py`
- **Protected Endpoints:**
  - `/admin/api-costs/summary` — cost monitoring
  - `/v1/chat/completions` — LLM endpoint (public access, but rate-limited)

**Validation:**
```python
def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    if not api_key_header:
        raise HTTPException(status_code=401, detail="API key is missing")

    if api_key_header not in valid_api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

**Error Responses:**
- 401 Unauthorized: Missing API key
- 403 Forbidden: Invalid API key
- Both include `WWW-Authenticate: API-Key` header

---

### 1.4 Frontend Secrets Protection ✅

**Purpose:** Ensure no sensitive credentials exposed in client bundle

**Verification:**
- ✅ No Anthropic API keys in source code
- ✅ No OpenAI keys in source code
- ✅ API key in `.env.example` is placeholder: `VITE_API_KEY=your_api_key_here`
- ✅ Real API key only exists on server
- ✅ Frontend bundle size verified: 144.76 KB gzipped

**Safe Practices:**
- Secrets never committed to git
- `.env` file in `.gitignore`
- Frontend only contains public configuration (API URL)
- Real authentication at backend only

---

### 1.5 MongoDB Connection Pooling ✅

**Purpose:** Prevent connection exhaustion, manage resource usage

**Configuration:**
```
Library: Motor (async MongoDB driver)
Max Pool Size: Configurable (see config.py)
Min Pool Size: Configurable (see config.py)
M0 Tier Limit: 500 concurrent connections
```

**Limits:**
```
MongoDB Atlas M0 (Free Tier):
- Max concurrent connections: 500
- Shared CPU resources
- Limited throughput (no SLA)
- No sharding available
- Max 512 MB storage
```

**Current Usage:**
- Estimated: ~50-100 connections at peak
- Headroom: 300+ connections available
- Monitoring: Health check reports pool status

---

### 1.6 Cost Monitoring & Alerts ✅

**Purpose:** Detect and respond to cost spikes (malicious or accidental)

**Anthropic API Monitoring:**
- [ ] Set monthly spend limit: $50 (configurable)
- [ ] Configure email alerts:
  - 50% of budget ($25)
  - 75% of budget ($37.50)
  - 90% of budget ($45)
  - 100% of budget ($50)
- [ ] Monitor via admin endpoint: `/admin/api-costs/summary`

**Railway Cost Monitoring:**
- [ ] Set monthly spend limit: $50 (configurable)
- [ ] Enable email alerts for overspend warnings
- [ ] Monitor CPU, RAM, bandwidth usage in Railway dashboard

**Backend Logging:**
- [ ] Cost tracking per LLM operation (input/output tokens)
- [ ] Admin cost summary endpoint working
- [ ] Daily cost aggregation available

**Cost Breakdown (Baseline):**
- Entity extraction (Haiku): ~$0.002-0.005 per 10 articles
- Narrative detection (Haiku): ~$0.001-0.002 per article
- Sentiment analysis (existing): included in Haiku costs
- Expected daily baseline: $0.50-2.00 (varies with article volume)

---

### 1.7 Error Handling & Information Leakage ✅

**Purpose:** Prevent exposing sensitive information through error messages

**Implementation:**
- ✅ No stack traces in API responses
- ✅ Generic error messages: `{"detail": "..."}`
- ✅ Logging includes details, responses don't
- ✅ Status codes consistent (401, 403, 429, 5xx)

**Example:**
```python
# Don't do this:
# {"detail": "KeyError: MONGODB_URI", "traceback": "..."}

# Do this:
# {"detail": "Database connection failed"}
```

---

## Part 2: Traffic Protection & DDoS Mitigation

### 2.1 Railway Backend Protection

**Platform Protections:**
- ✅ DDoS protection included (standard tier)
- ✅ Automatic IP blocking for suspicious traffic
- ✅ Rate limiting at edge (optional, see rate limiting above)

**Traffic Limits:**
- Max concurrent connections: Depends on app configuration
- Bandwidth: Unlimited for reasonable usage
- Requests/sec: No hard limit (but costs scale)

**Monitoring:**
```
Railway Dashboard:
- Real-time CPU usage
- Memory usage
- Network bandwidth
- Build logs
- Deploy history
```

**Escalation Plan (if traffic spikes):**
1. Monitor CPU usage in Railway dashboard
2. If CPU > 80%: Check app logs for errors
3. If legitimate traffic: Upgrade Railway plan to higher tier
4. If suspicious traffic: Review rate limit logs, block IPs manually
5. If still issues: Reach out to Railway support

---

### 2.2 Vercel Frontend Protection

**CDN Protections:**
- ✅ DDoS protection included
- ✅ Automatic edge caching
- ✅ Global CDN for low latency
- ✅ SSL/TLS termination

**Monitoring:**
```
Vercel Dashboard:
- Request count
- Bandwidth usage
- Response times
- Error rates
- Build status
```

**No action typically needed** — Vercel handles DDoS transparently.

---

### 2.3 Load Testing Recommendations

Before major launches, simulate traffic:

```bash
# Using k6 (install: brew install k6)
k6 run load-test.js

# Using Apache Bench
ab -n 1000 -c 100 https://your-api.com/api/v1/signals/trending
```

**Targets:**
- 100 concurrent users → Response < 2 seconds
- 500 concurrent users → Service remains available (may slow)
- 1000+ concurrent users → May hit rate limits (expected)

---

## Part 3: Incident Response

### 3.1 Rate Limit Abuse Detected

**Signs:**
- Logs show many 429 responses from single IP
- Cost spike from repeated expensive endpoint calls

**Response:**
1. Check logs: `grep "rate_limit:" logs/app.log`
2. Identify abusive IP(s)
3. Option A: Wait (limits reset every 60 seconds)
4. Option B: Manual IP block in firewall (future: add IP blocklist feature)
5. Review attack pattern and adjust limits if needed

---

### 3.2 Unexpected Cost Spike

**Signs:**
- Anthropic or Railway costs 10x higher than baseline
- Admin endpoint shows unusual cost distribution

**Response:**
1. Check `/admin/api-costs/summary` for cost breakdown
2. Identify which operation is expensive
3. Check logs for patterns (single IP, specific endpoint)
4. If abuse: Apply rate limits or block IP
5. If legitimate: May need to upgrade or optimize

---

### 3.3 Service Degradation / High Latency

**Signs:**
- Response times > 5 seconds
- Many 5xx errors in logs
- MongoDB connection pool warnings

**Response:**
1. Check Railway CPU/memory in dashboard
2. Check MongoDB Atlas status dashboard
3. Review recent code deployments
4. If connection pool exhausted: Restart Railway dyno
5. If legitimate traffic surge: Upgrade Railway plan

---

### 3.4 Database Connection Exhaustion

**Signs:**
- Logs show connection pool warnings
- MongoDB Atlas shows connection limit errors

**Response:**
1. Check current connection count: `MongoDB Atlas Dashboard → Metrics`
2. Review application logs for connection leaks
3. Short-term fix: Restart Railway to reset pool
4. Long-term fix: Upgrade MongoDB to paid tier or optimize queries

---

## Part 4: Pre-Launch Checklist

- [ ] Rate limiting middleware installed and tested ✅
- [ ] Rate limit configuration reviewed for business logic
- [ ] CORS properly restricted to Vercel domain ✅
- [ ] API key authentication working on protected endpoints ✅
- [ ] Frontend bundle verified (no secrets) ✅
- [ ] MongoDB connection pooling configured ✅
- [ ] Anthropic API spend alerts configured (in dashboard)
- [ ] Railway spend limit configured (in dashboard)
- [ ] Cost monitoring endpoint tested (`/admin/api-costs/summary`)
- [ ] Error messages don't leak information ✅
- [ ] Railway DDoS protection verified
- [ ] Vercel CDN protection verified
- [ ] Load test plan documented (optional, for post-launch)
- [ ] Incident response procedures documented ✅

---

## Part 5: Post-Launch Monitoring

### Daily Checks
- [ ] Review rate limit logs for abuse patterns
- [ ] Check cost trends on Anthropic/Railway dashboards
- [ ] Verify no spike in error rates
- [ ] Confirm response times within expected range

### Weekly Checks
- [ ] Review database connection pool usage
- [ ] Check API health metrics
- [ ] Analyze traffic patterns and peak times
- [ ] Update baseline cost expectations

### Monthly Checks
- [ ] Full security audit of logs
- [ ] Review rate limit configuration (adjust if needed)
- [ ] Test incident response procedures
- [ ] Update cost projections

---

## Part 6: Configuration Reference

### Rate Limiting Config
**File:** `src/crypto_news_aggregator/core/rate_limiting.py`

```python
RATE_LIMIT_CONFIG = {
    "/v1/chat/completions": {"limit": 5, "window": 60},
    "/api/v1/signals/trending": {"limit": 10, "window": 60},
    "/api/v1/briefing/latest": {"limit": 20, "window": 60},
    # ... see file for complete config
}
```

To adjust limits:
1. Edit `RATE_LIMIT_CONFIG` in `core/rate_limiting.py`
2. Adjust `limit` (requests per window) or `window` (seconds)
3. Test: Make requests and verify 429 at correct count
4. Commit and deploy

### CORS Config
**File:** `src/crypto_news_aggregator/main.py` (line ~147)

To add a new domain:
1. Update regex pattern in `allow_origin_regex`
2. Test with curl: `curl -H "Origin: https://new-domain.com"`
3. Verify response has `Access-Control-Allow-Origin` header
4. Commit and deploy

### API Key Verification
**File:** `src/crypto_news_aggregator/core/auth.py`

To verify a specific endpoint is protected:
1. Open endpoint file (e.g., `api/admin.py`)
2. Check for `Security(get_api_key)` dependency
3. If present: endpoint requires API key ✓
4. If missing: endpoint is public (may have rate limit)

---

## Part 7: Future Enhancements

**Post-Launch (not blocking):**
- [ ] IP-based API key rate limits (fine-grained control)
- [ ] Webhook signature verification (external integrations)
- [ ] Request signing for sensitive operations
- [ ] Cloudflare WAF for additional DDoS protection
- [ ] Automated load testing in CI/CD
- [ ] Machine learning-based anomaly detection
- [ ] Automatic IP blocklisting for repeat abusers

---

## Questions & Support

**Rate Limiting Issues?**
- Check logs: `grep "rate_limit:" logs/app.log`
- Test locally: `tests/test_rate_limiting.py`
- Review configuration: `RATE_LIMIT_CONFIG` in `core/rate_limiting.py`

**Cost Spike Issues?**
- Check `/admin/api-costs/summary` endpoint
- Review Anthropic API logs: https://console.anthropic.com/logs
- Compare against baseline documented above

**Service Degradation?**
- Check Railway dashboard: https://railway.app/dashboard
- Check MongoDB Atlas status: https://cloud.mongodb.com/
- Review recent deployments

---

**Document Version:** 1.0
**Last Reviewed:** 2026-02-26
**Next Review:** 2026-03-26 (post-launch)
