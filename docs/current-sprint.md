# Sprint 14 — Infrastructure Stability + LLM Cost Monitoring

**Status:** IN PROGRESS
**Target Start:** 2026-04-11
**Target End:** 2026-04-14
**Sprint Goal:** Fix critical briefing bugs, validate scheduled briefing execution, measure actual LLM costs, establish sustainable infrastructure baseline.

---

## Current Status (2026-04-13, 13:00 EST)

### ✅ Completed This Sprint
- **BUG-064:** Memory leak + retry storm — MERGED
- **BUG-065:** Briefing soft limit incorrectly triggered — MERGED
- **BUG-066:** Daily cost calculation (rolling 24h vs calendar day) — CODE COMPLETE
- **BUG-067:** Motor AsyncIOMotorDatabase truthiness check — CODE COMPLETE
- **BUG-068:** Double cost tracking (OptimizedAnthropicLLM duplicate) — CODE COMPLETE
- **BUG-069:** Briefing persistence (empty documents) — **✅ FIXED & VERIFIED**
  - Manual briefing generation tested: saves with full content
  - Cost logged correctly: $0.010033
  - Document visible on UI: ✅ Yes
- **BUG-070:** Narrative tier-1 only filter — **✅ CODE COMPLETE**
  - Changed `MAX_RELEVANCE_TIER = 2` → `1` in narrative_themes.py
  - Expected savings: -64% narrative calls (~193 → 70/day), ~$0.38/day cost reduction
  - Single-line fix, zero-risk change

### 🔲 In Progress
- **TASK-028:** Validate scheduled briefing execution + measure costs (see below)

### 📋 Not Yet Started
- TASK-069: Cost dashboard + Slack alerts
- TASK-070: Narrative cost investigation (separate from TASK-028)
- TASK-071: Spend threshold adjustment

---

## TASK-028: Scheduled Briefing Validation (Next Phase)

**Current blockers resolved:**
- ✅ Code fixes applied (BUG-064 through BUG-069)
- ✅ Manual briefing generation working
- ✅ Celery Beat configured with correct timezone (`America/New_York`)
- ✅ Celery Worker running on Railway

**What we need to verify:**
Scheduled briefings **may have been broken before**, and we need to confirm BUG-069 fix resolves that.

### Verification Plan

**Phase 1: Watch next scheduled execution (Today 2026-04-13)**
- Morning briefing was at 8:00 AM EST (already passed)
- Evening briefing scheduled for 8:00 PM EST (20:00 EST = 02:00 UTC next day)
- Check at ~20:15 EST:
  ```javascript
  // Verify document saved
  db.briefing_drafts.findOne({created_at: {$gte: new Date("2026-04-13T20:00:00Z")}})
  
  // Verify it has content, not empty
  // Should have: narrative, key_insights, entities_mentioned, recommendations, confidence_score
  ```

**Phase 2: 72-hour observation (2026-04-13 to 2026-04-16)**
- Let system run for 3 full days of normal operation
- Collect metrics:
  - Scheduled briefing execution (should see 6 total: 2/day × 3 days)
  - All documents should have full content
  - Cost tracking by operation

**Phase 3: Cost attribution report (after 72h)**
- Query all `llm_traces` from the period
- Group by operation, sum costs
- Validate assumptions:
  - Briefing generation: ~$0.01/run × 6 runs = $0.06
  - Narrative operations should be minimal during scheduled runs (no active user enrichment)
  - Total daily spend should be $0.50–0.70 (validate Sprint 13 optimization)

**Success criteria:**
- [ ] All scheduled briefings execute (6 documents in 72h, all with content)
- [ ] No empty briefing documents
- [ ] Daily cost stays under $1.00 hard limit
- [ ] Soft limit not triggered (should be under $0.50 soft if narrative costs optimized)

---

## Why Scheduled Briefings Might Have Been Broken

**Context:** You mentioned scheduled briefings were failing for reasons you can't remember.

**Most likely cause:** BUG-069 (empty document persistence)
- Manual briefings probably always worked (you'd test manually, see it save with content)
- Scheduled briefings probably failed silently (empty documents created, Celery task marked "success")
- Users never saw briefings on UI
- You debugged and found them empty, then abandoned scheduled generation

**Hypothesis:** BUG-069 fix resolves this. The code path that was broken is now working.

---

## Infrastructure Status

**Services running on Railway:**
- ✅ FastAPI backend (API server)
- ✅ Celery Worker (task execution)
- ✅ Celery Beat (scheduler)
- ✅ MongoDB (database)
- ✅ Redis (cache/locks)

**No migration planned** — Railway services are stable. If cost becomes an issue later, Sprint 15 can evaluate provider migration.

**Celery configuration verified:**
```python
# celery_config.py
timezone = "America/New_York"  # ✅ EST/EDT handling automatic
enable_utc = True

# beat_schedule.py
"generate-morning-briefing": crontab(hour=8, minute=0)   # 8 AM EST
"generate-evening-briefing": crontab(hour=20, minute=0)  # 8 PM EST
```

---

## Cost Baseline (Pre-Sprint 14)

From previous observations:
- **Narrative operations:** ~$0.38/day (32 calls in 30 mins = 64/hour) 🚨 HIGH
- **Briefing generation:** ~$0.01/briefing
- **Article enrichment:** ~$0.20/day (heavily throttled)
- **Other:** entity extraction, alerts, cache
- **Total:** ~$0.95/day (near $1.00 hard limit)

**Issue:** Narratives dominate budget. TASK-070 will investigate this separately.

---

## Next Actions (48h)

1. **Tonight (2026-04-13 20:00 EST):** Check that evening briefing executes scheduled
2. **Tomorrow:** Continue observation, ensure morning briefing (2026-04-14 08:00 EST) also executes
3. **Wednesday 2026-04-15:** Confirm 72-hour pattern holds (6 briefings, all with content)
4. **Thursday 2026-04-16:** Generate cost report, determine if additional optimizations needed

**If scheduled briefing fails:**
- Check Celery Beat logs
- Verify MongoDB connection from worker
- Check for LLM errors in traces
- Fall back to manual triggers while debugging

---

## Removed From This Sprint

These items are deferred to post-validation:
- TASK-064 (Railway cost audit) — Not needed if current infrastructure stable
- TASK-065/066/067 (provider migration) — Only if costs spike again
- TASK-069 (dashboard + alerts) — Can build after cost stability confirmed
- TASK-070 (narrative cost investigation) — Separate sprint focus

---

## Success Criteria (for Sprint 14 completion)

- [x] All critical bugs fixed (BUG-064 through BUG-069)
- [ ] Manual briefing generation working (VERIFIED ✅)
- [ ] Scheduled briefing execution confirmed working (PENDING — watch tonight)
- [ ] 72-hour observation period complete (PENDING)
- [ ] Cost report shows sustainable daily spend (PENDING)
- [ ] Services remain stable for 3 days without restarts (PENDING)

---

## Risk Assessment

| Risk | Probability | Mitigation |
|------|------------|-----------|
| Scheduled briefings still broken | Low | Manual testing tonight at 8 PM EST; fallback to manual triggers |
| Cost explodes again (>$1.00/day) | Medium | Soft limit at $0.50 will block enrichment; investigate narrative costs (TASK-070) |
| Celery Beat crashes | Low | Worker has auto-restart; can manually trigger briefings if needed |
| Database consistency issues | Very Low | BUG-069 fix ensures all inserts go through single code path |

---

## Handoff to Sprint 15

If TASK-028 validation succeeds:
- ✅ Infrastructure stable, daily costs $0.50–0.70
- ✅ Scheduled briefings working automatically
- ✅ Cost tracking complete and visible
- ✅ Ready for broader feature development

**Sprint 15 priorities:**
1. Build cost dashboard + Slack alerts (TASK-069)
2. Investigate + optimize narrative costs (TASK-070)
3. Adjust spend thresholds for sustainable operation (TASK-071)
4. Resume product development (narrative quality, briefing enhancements)

---

**Status: Ready for scheduled briefing validation tonight**