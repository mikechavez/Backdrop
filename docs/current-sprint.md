# Sprint 14 — Infrastructure Stability + LLM Cost Monitoring

**Status:** Planning
**Target Start:** 2026-04-11 (today)
**Target End:** 2026-04-14
**Sprint Goal:** Restore all Backdrop services from Railway outage, understand + fix infrastructure costs, finalize LLM cost monitoring, resume production briefing generation.

---

## Critical Blocker: Railway Outage 🔴

**Current State:**
- All services DOWN: FastAPI backend, Celery worker, Redis, MongoDB
- Trigger: Railway plan exceeded $30 hard cap set by user
- Cost driver: Unknown (database? compute? Redis memory?)
- Impact: No briefings generated since ~2026-04-11 morning, no API availability

**Timeline to Resolution:**
- **T+0 (now):** Audit Railway bill, identify cost driver(s)
- **T+2h:** Decide: right-size existing Railway services OR migrate to cost-transparent provider
- **T+4h:** Execute migration/reconfiguration, restore services
- **T+6h:** Smoke test briefing generation, validate costs
- **Target:** Services restored by end of day 2026-04-11

---

## Sprint Order

| # | Ticket | Title | Status | Est | Impact |
|---|--------|-------|--------|-----|--------|
| 0 | **BUG-064** | **Memory Leak + Retry Storm (Max Retries, Op Name Mismatch)** | ✅ CODE COMPLETE | high | 0.5h | Critical path |
| 1 | **TASK-064** | **Railway Cost Audit — Identify Cost Driver(s)** | 🔲 TODO | high | 1.5h | Critical path |
| 2 | **TASK-065** | **Provider Migration Decision — Render vs Fly vs Self-Hosted** | 🔲 BLOCKED | high | 0.5h | Depends on TASK-064 |
| 3 | **TASK-066** | **Migrate Backend to New Provider** | 🔲 BLOCKED | high | 2h | Depends on TASK-065 |
| 4 | **TASK-067** | **Migrate Database/Cache to New Provider** | 🔲 BLOCKED | high | 2h | Depends on TASK-065 |
| 5 | **TASK-068** | **Restore Services + Smoke Test** | 🔲 BLOCKED | high | 1h | Depends on TASK-066/067 |
| 6 | **BUG-063** | **Merge Narrative Polish Gateway Fix** | 🔄 WAITING | critical | 0.5h | Unblocks LLM monitoring |
| 7 | **TASK-069** | **Deploy LLM Cost Dashboard + Slack Alerts** | 🔲 TODO | medium | 1.5h | Monitoring/observability |
| 8 | **TASK-070** | **Post-Optimization Burn-in (24hr)** | 🔲 TODO | medium | 0.25h | Validates cost targets |
| 9 | **TASK-071** | **Adjust Spend Thresholds for Sustainable Ops** | 🔲 TODO | low | 0.5h | Config + docs |

---

## Success Criteria

- [ ] Railway cost driver identified and documented
- [ ] All services restored to production (backend, worker, database, cache)
- [ ] New infrastructure provider selected with transparent, predictable costs
- [ ] Daily infrastructure cost ≤ $2/day (sustainable long-term)
- [ ] BUG-063 merged and narrative polish fully metered
- [ ] 24-hour burn-in validates LLM costs ≤ $0.70/day
- [ ] Slack alerts configured for soft/hard spend limits
- [ ] Briefing generation running normally with no outages

---

## Detailed Tasks

### TASK-064: Railway Cost Audit — Identify Cost Driver(s) 🔴 CRITICAL

**What to check:**
1. Log into Railway dashboard → select production project → view Billing page
2. For each service, note:
   - Compute hours billed (backend FastAPI, Celery worker)
   - Database storage (MongoDB) + ops charges
   - Redis memory tier + egress bandwidth
   - Any data transfer charges
3. Cross-reference with daily spend: is it constant or spiking?

**Likely culprits:**
- **MongoDB:** Always-on, charges per MB stored + per million ops
  - Typical for Backdrop: ~500MB–1GB storage + high query volume (article ingest, briefing gen)
  - Estimate: $5–15/day depending on ops
- **Redis:** Memory tier pricing (1GB tier ≈ $5–10/month, but Railway charges higher)
  - Backdrop uses Redis for: briefing locks, article cache, soft-limit tracking
  - Estimate: $0.50–2/day on Railway
- **FastAPI compute:** Always-on backend instance (e.g., 2GB RAM tier)
  - Railway charges by CPU+RAM time
  - Estimate: $10–20/day for 2GB instance
- **Celery worker:** Scheduled tasks (article ingest every 2h, briefing gen 2x/day)
  - If always-on: $10–20/day; if stopped: $0
  - Check: is worker running 24/7 or only during scheduled tasks?

**Output:**
- Document: `infrastructure-costs-audit.md` with:
  - Current Railway bill breakdown
  - Estimated daily cost for each service
  - Comparison to $30 hard cap (implies $30/day avg or $1/day if recent overage)
  - Recommendation for cost control

**Effort:** 1.5h (includes analysis + writeup)

---

### TASK-065: Provider Migration Decision — Render vs Fly vs Self-Hosted

**Options to evaluate:**

| Provider | FastAPI | MongoDB | Redis | Est. Cost | Pros | Cons |
|----------|---------|---------|-------|-----------|------|------|
| **Railway (current)** | $10–20/d | $5–15/d | $2–5/d | $20–40/d | Integrated | Opaque pricing, high cost |
| **Render** | $7–15/d* | $0.50–2/d** | $1–3/d** | $10–20/d | Simple deploys, good docs | Still managed |
| **Fly.io** | $2–5/d | $0.50–2/d** | $1–3/d** | $5–15/d | Cheapest compute, transparent | More config |
| **Self-hosted VPS** | $0.67–1/d | Included | Included | $1–2/d | Cheapest, full control | More ops burden |

*Render free tier doesn't support production; cheapest paid tier ~$7/month
**Using Atlas + Upstash (not provider-specific services)

**Decision Tree:**
1. If Railway cost driver is **database/cache** → switch to Atlas (MongoDB) + Upstash (Redis), keep backend on Railway
2. If **compute is the issue** → migrate backend to Fly.io or Render, keep services on respective platforms
3. If **total cost > $5/day and willing to self-host** → rent VPS ($20/mo) + run everything there

**Recommendation (pending TASK-064):**
- Likely scenario: Switch MongoDB to Atlas ($3–5/d), Redis to Upstash ($1–2/d), backend to Render ($7–10/d)
- Total: ~$12–17/d vs current $20–40/d
- Effort: 2–3h migration, 1h per service testing

**Effort:** 0.5h (analysis + decision doc)

---

### TASK-066: Migrate Backend to New Provider (Pending TASK-065)

**If migrating to Render:**
1. Create Render account, link GitHub repo
2. Create new Web Service from `mikechavez/backdrop` repo
3. Set environment variables (API keys, secrets, database URIs)
4. Deploy and verify `/health` endpoint responding
5. Switch production DNS/CDN to new Render service
6. Disable old Railway backend
7. Smoke test: `/admin/trigger-briefing?is_smoke=true`

**If migrating to Fly.io:**
1. Install `fly` CLI, `flyctl auth login`
2. Create `fly.toml` in repo root (see Fly docs for Python/FastAPI)
3. Set secrets: `flyctl secrets set API_KEYS=...`
4. Deploy: `flyctl deploy`
5. Allocate IP / set DNS
6. Smoke test

**Effort:** 2h (includes new account setup, environment config, testing)

---

### TASK-067: Migrate Database/Cache to New Provider (Pending TASK-065)

**MongoDB → Atlas:**
1. Create free MongoDB Atlas account or use existing
2. Create cluster in us-east-1 (same region as FastAPI for latency)
3. Generate connection string
4. Dump current MongoDB data from Railway: `mongodump --uri "mongodb://..."`
5. Restore to Atlas: `mongorestore --uri "mongodb+srv://..."`
6. Update `MONGODB_URI` env var in new backend
7. Verify article count, traces, briefings still present
8. Disable Railway MongoDB instance

**Redis → Upstash:**
1. Create Upstash account, create Redis database (us-east-1)
2. Get connection string (Redis URL)
3. Dump current Redis data (if critical): `redis-cli BGSAVE`, download RDB file
4. Update `REDIS_URL` env var in new backend
5. Verify Celery tasks queuing/processing normally
6. Disable Railway Redis

**Effort:** 2h (includes setup, migration, verification)

---

### TASK-068: Restore Services + Smoke Test

**Checklist:**
- [ ] FastAPI backend up and responding to `/health` → `"status": "ok"`
- [ ] Celery worker running and processing tasks (check logs)
- [ ] MongoDB connected: `db.articles.countDocuments()` > 0
- [ ] Redis connected: `redis-cli PING` → `PONG`
- [ ] Manual briefing trigger: `/admin/trigger-briefing?is_smoke=true` completes
- [ ] Briefing saved to MongoDB with traces
- [ ] No errors in backend logs or Sentry
- [ ] Daily cost tracking: Current spend < $2/day

**Output:**
- Smoke test log (timestamp, endpoint, response code, no errors)
- Cost validation: current daily run cost

**Effort:** 1h (testing, validation, debugging any issues)

---

### BUG-063: Merge Narrative Polish Gateway Fix (WAITING)

**Current State:** Code complete, 4 unit tests passing, awaiting manual smoke test

**Action:**
1. Manual smoke test on production: generate briefing, check logs for `narrative_polish` operation traces
2. Verify traces logged to MongoDB
3. Merge PR to main, deploy to production

**Expected impact:** Closes last ~$2/day unmetered spend, total LLM cost reduction -75%

**Effort:** 0.5h

---

### TASK-069: Deploy LLM Cost Dashboard + Slack Alerts

**Dashboard components:**
1. Daily LLM spend by operation (bar chart)
2. Cumulative spend this month (line chart)
3. Per-operation cost attribution table
4. Last 24h traces (sortable by cost/operation)

**Implementation:**
- Create `/admin/cost-dashboard` endpoint in FastAPI
- Query MongoDB `llm_traces` aggregation (from TASK-037)
- Format as HTML + embedded Chart.js or Plotly
- Display last 24 hours, last 7 days, this month tabs

**Slack alerts:**
- Soft limit alert: `⚠️ LLM spend $0.50/day, at 71% of daily limit`
- Hard limit alert: `🚨 LLM spend $1.00/day, BRIEFING GENERATION PAUSED`
- Daily digest: `📊 LLM spend today: $0.45, top operation: narrative_polish (65%)`

**Effort:** 1.5h (dashboard + Slack integration)

---

### TASK-070: Post-Optimization Burn-in (24hr)

**Timeline:**
- Run from T+48h to T+72h (24 hours of normal operation)
- Collect all traces: briefing_generate, briefing_critique, briefing_refine, narrative_detection, narrative_polish, enrichment, entity_extraction
- Generate cost attribution report

**Output:**
- Cost by operation (validate TASK-062, TASK-063 improvements)
- Cost by time of day (peak hours)
- Cost per briefing (should be ~$0.01–0.02 with Haiku)
- Daily total (should be $0.50–0.70)

**Success criteria:**
- Daily spend ≤ $0.70/day
- Narrative polish ≤ $0.10/day (not $1.50+)
- Enrichment ≤ $0.15/day
- Briefing gen ≤ $0.05/day

**Effort:** 0.25h (query + analysis)

---

### TASK-071: Adjust Spend Thresholds for Sustainable Ops

**Current config (from Sprint 13):**
```python
LLM_DAILY_SOFT_LIMIT = 0.25  # Pauses narrative enrichment
LLM_DAILY_HARD_LIMIT = 0.33  # Kills briefing generation
```

**Issue:** Thresholds are too tight now that optimization is complete. Need to adjust based on post-TASK-062/063 actual costs.

**New config (post-optimization):**
```python
LLM_DAILY_SOFT_LIMIT = 0.50   # Graceful degradation when approaching limit
LLM_DAILY_HARD_LIMIT = 1.00   # Hard stop (2-3x safety margin)
```

**Rationale:**
- Expected sustainable cost: $0.50–0.70/day
- Soft limit at $0.50 gives warning when approaching target
- Hard limit at $1.00 prevents runaway costs (2x upside buffer)

**Updates:**
- `src/crypto_news_aggregator/core/config.py` (lines 140–142)
- Documentation: add comment explaining rationale
- Verify no regression in existing tests

**Effort:** 0.5h (config update + testing)

---

## Block Diagram (Parallel Path)

```
T+0: TASK-064 (Railway audit) — BLOCKING
   ↓ (1.5h)
T+1.5h: TASK-065 (provider decision)
   ├─ Option A: Migrate MongoDB/Redis only
   │  ├─ TASK-066A (DB/cache only, no backend change)
   │  └─ TASK-068A (test backend + DB/cache together)
   │
   └─ Option B: Full migration (backend + DB + cache)
      ├─ TASK-066 (FastAPI) || TASK-067 (DB/cache) — parallel
      └─ TASK-068 (smoke test all 3 together)

T+4h–5h: Services restored ✅

Parallel (non-blocking):
   ├─ BUG-063 (merge, 0.5h)
   ├─ TASK-069 (dashboard, 1.5h)
   ├─ TASK-070 (burn-in, 0.25h)
   └─ TASK-071 (config, 0.5h)

T+48h–72h: TASK-070 (24h burn-in validates costs)
T+72h: Sprint 14 complete ✅
```

---

## Success Metrics

| Metric | Target | Current (Sprint 13) | Sprint 14 Goal |
|--------|--------|-------------------|-----------------|
| **Infrastructure Cost** | $2–5/day | $20–40/day (Railway) | ≤ $5/day |
| **LLM Cost** | $0.50–0.70/day | ~$2/day (burn-in pending) | $0.50–0.70/day |
| **Total Daily Cost** | ≤ $5.70/day | $22–42/day | ≤ $5.70/day |
| **Services Status** | ✅ All up | 🔴 DOWN (Railway cap) | ✅ All up |
| **Briefing Generation** | 2x/day | 🔴 Blocked | 2x/day |
| **Cost Visibility** | 100% | 100% (gateway complete) | 100% (dashboard live) |
| **Spend Alerts** | Slack notifications | None | Daily digest + breaches |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Migration takes longer than 4h | Medium | Briefings delayed 1–2 days | Start ASAP, have rollback plan |
| New provider has different latency | Low | Briefing gen slower | Test with dummy data first |
| Data loss in DB migration | Low | Lose articles/traces | Dump backup before migration, test restore |
| LLM costs not as low as projected | Medium | Still high bills | TASK-070 validates, can adjust if needed |

---

## Decisions Made

1. **Infrastructure cost is a blocking issue** — Sprint 14 prioritizes restoration + cost control
2. **Likely path: Database/cache migration** — Atlas + Upstash will be cheaper than Railway all-in-one
3. **LLM cost monitoring is now visible** — dashboard + alerts will prevent surprises
4. **Sustainable cost target: ≤ $5.70/day all-in** — infrastructure + LLM combined
5. **Spend limits will be relaxed** — post-optimization thresholds give more headroom

---

## Handoff to Sprint 15

If all Sprint 14 goals hit:
- ✅ Infrastructure costs $2–5/day (sustainable long-term)
- ✅ LLM costs $0.50–0.70/day (validated via burn-in)
- ✅ Full visibility: cost dashboard + alerts live
- ✅ No more outages due to cost overages

**Sprint 15 priorities:**
1. Continue Backdrop feature development (narrative refinement, briefing quality)
2. Monitor cost trends (validate assumptions, catch regressions)
3. Resume job search activities (infrastructure stability enables context to shift to career)

---

**Status: Ready for immediate start**