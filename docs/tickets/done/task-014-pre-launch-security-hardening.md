---
ticket_id: TASK-014
title: Pre-Launch Security Hardening (DDoS, Rate Limiting, Attack Surface)
priority: HIGH
severity: HIGH
status: OPEN
date_created: 2026-02-24
branch: 
effort_estimate: 2-4 hours (audit + implementation)
---

# TASK-014: Pre-Launch Security Hardening (DDoS, Rate Limiting, Attack Surface)

## Problem Statement

Backdrop is preparing for public launch via Substack article. Once live, the app will be exposed to the open internet and potentially hostile traffic. Currently there is no DDoS protection, rate limiting, or security hardening in place. A Substack launch with links to the live app could attract both legitimate traffic spikes and malicious actors.

---

## Task

Audit and harden the application against common attack vectors before public launch. This covers:

### 1. DDoS / Traffic Spike Protection
- [ ] Evaluate Railway's built-in DDoS protection (what's included on current plan?)
- [ ] Evaluate Vercel's built-in DDoS protection for frontend
- [ ] Determine if Cloudflare or similar CDN/proxy is needed
- [ ] Load test: can the app handle 100+ concurrent users?

### 2. API Rate Limiting
- [ ] Implement rate limiting on public API endpoints (FastAPI middleware or nginx)
- [ ] Set per-IP limits for `/api/v1/signals/trending`, `/api/v1/briefing/latest`, etc.
- [ ] Rate limit the LLM-calling endpoints more aggressively (cost protection)
- [ ] Consider API key requirement for non-frontend consumers

### 3. MongoDB Atlas M0 Limits
- [ ] Document Atlas M0 connection limits (max 500 connections)
- [ ] Document Atlas M0 throughput limits
- [ ] Ensure connection pooling is configured correctly
- [ ] Plan for what happens if traffic exceeds free tier limits

### 4. Attack Surface Audit
- [ ] Verify no API keys or secrets exposed in frontend bundle
- [ ] Verify CORS is configured correctly (not wildcard)
- [ ] Verify admin endpoints are properly authenticated
- [ ] Check for any open debug endpoints or verbose error responses
- [ ] Verify MongoDB connection string is not exposed anywhere (post GitGuardian incident)

### 5. Cost Protection
- [ ] Set Anthropic API spend alerts/limits
- [ ] Ensure Sonnet fallback fix (BUG-039) is deployed — prevents cost amplification
- [ ] Set Railway spend limits
- [ ] Monitor for abuse patterns that could spike LLM costs

---

## Verification

- [ ] Rate limiting returns 429 on excessive requests
- [ ] Admin endpoints reject unauthenticated requests
- [ ] CORS only allows frontend origin
- [ ] No secrets in frontend build output
- [ ] Load test passes at expected launch traffic levels
- [ ] Cost monitoring alerts configured

---

## Acceptance Criteria

- [ ] Rate limiting implemented on all public API endpoints
- [ ] Attack surface audit complete with no critical findings (or findings fixed)
- [ ] Atlas M0 limits documented with contingency plan
- [ ] Cost protection mechanisms in place
- [ ] App survives simulated traffic spike (load test)

---

## Impact

Without this work, a successful launch could result in:
- Service outage from traffic spikes
- Runaway LLM costs from malicious API calls
- Data exposure from unsecured endpoints
- MongoDB Atlas M0 connection exhaustion

---

## Related Tickets

- BUG-039 (Sonnet fallback cost leak) — cost protection prerequisite ✅ MERGED
- TASK-001 through TASK-010 — Substack launch sequence (blocked by this)